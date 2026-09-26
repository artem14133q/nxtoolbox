// nxtest - runs Python scripts on the Switch: from an on-console menu or over the network.
//
// Screen: menu with .py files from /switch/nxtest/scripts (VIEW_MENU) and script output (VIEW_LOG).
//
// Protocol (version 2), all numbers are big-endian:
//   1. Switch -> client: "NXPY" + version byte + 16 random bytes (nonce)
//   2. client -> Switch: HMAC-SHA256(password, nonce) (32 bytes) + command byte
//   3. Command 'R' (run):    4-byte length + script text.
//        The Switch runs the script, streams its output and closes the connection.
//        If the client closes its side (shutdown SHUT_WR), the script gets KeyboardInterrupt.
//      Command 'U' (upload): 2-byte path length + path (UTF-8, relative to /switch/nxtest,
//        '/' separator) + 4-byte size + file contents.
//        The Switch replies "ok <size>" or "error: ..." and closes the connection.

#include <switch.h>
#include <stdio.h>
#include <stdarg.h>
#include <strings.h>
#include <dirent.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <poll.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#include "port/micropython_embed.h"
#include "switch_hw.h"

#define PORT          5555
#define MAX_SCRIPT    (512 * 1024)
#define HEAP_SIZE     (4 * 1024 * 1024)

#define CONFIG_DIR    "sdmc:/switch/nxtest"
#define PASSWORD_FILE CONFIG_DIR "/password.txt"
#define SCRIPTS_DIR   CONFIG_DIR "/scripts"   // scripts shown in the menu
#define MAX_PASSWORD  128

#define PROTO_MAGIC   "NXPY"
#define PROTO_VERSION 2
#define NONCE_SIZE    16
#define MAC_SIZE      32

#define MAX_PATH_LEN  512
#define MAX_UPLOAD    (256u * 1024 * 1024)

static char mp_heap[HEAP_SIZE];
static int g_client = -1;   // current client that receives a copy of the output
static char g_password[MAX_PASSWORD + 1];

// Stopping scripts
#define STOP_COMBO    (HidNpadButton_Plus | HidNpadButton_Minus)
static PadState g_hook_pad;          // separate pad state for the stop combo
static bool g_combo_was_held = false;
static bool g_client_eof = false;    // client pressed Ctrl+C (closed its side)
static bool g_quit = false;          // the system asked the app to exit
static u64  g_last_poll = 0;

// ---------- network ----------

static int send_all(int fd, const char *buf, size_t len) {
    while (len > 0) {
        ssize_t n = send(fd, buf, len, 0);
        if (n <= 0) return -1;
        buf += n;
        len -= n;
    }
    return 0;
}

static int send_str(int fd, const char *s) {
    return send_all(fd, s, strlen(s));
}

static int recv_all(int fd, void *buf, size_t len) {
    char *p = buf;
    while (len > 0) {
        ssize_t n = recv(fd, p, len, 0);
        if (n <= 0) return -1;
        p += n;
        len -= n;
    }
    return 0;
}

// Constant-time comparison so the signature cannot be guessed from response timing
static bool secure_equal(const u8 *a, const u8 *b, size_t len) {
    u8 diff = 0;
    for (size_t i = 0; i < len; i++) diff |= a[i] ^ b[i];
    return diff == 0;
}

// ---------- password ----------

static void generate_password(char *out, const size_t len) {
    // no look-alike characters (0/o, 1/l/i), so it is easy to type from the screen
    static constexpr char alphabet[] = "abcdefghjkmnpqrstuvwxyz23456789";
    u8 rnd[MAX_PASSWORD];
    randomGet(rnd, len);
    for (size_t i = 0; i < len; i++) out[i] = alphabet[rnd[i] % (sizeof(alphabet) - 1)];
    out[len] = '\0';
}

static void load_password() {
    FILE *f = fopen(PASSWORD_FILE, "r");
    if (f) {
        if (!fgets(g_password, sizeof(g_password), f)) g_password[0] = '\0';
        fclose(f);
        size_t n = strlen(g_password);
        while (n > 0 && (g_password[n - 1] == '\n' || g_password[n - 1] == '\r' ||
                         g_password[n - 1] == ' '  || g_password[n - 1] == '\t')) {
            g_password[--n] = '\0';
        }
        if (n > 0) return;   // password loaded
    }

    // No file or it is empty: create a new password
    generate_password(g_password, 10);
    mkdir(CONFIG_DIR, 0777);  // ignore errors: the folder may already exist
    f = fopen(PASSWORD_FILE, "w");
    if (f) {
        fprintf(f, "%s\n", g_password);
        fclose(f);
        printf("New password saved to %s\n", PASSWORD_FILE);
    } else {
        printf("Warning: could not save password, it will change after restart\n");
    }
}

// ---------- MicroPython ----------

// MicroPython sends all output (print, tracebacks) here.
// ReSharper disable once CppUseInternalLinkage
void app_output(const char *str, const size_t len) {
    fwrite(str, 1, len, stdout);
    if (g_client >= 0 && send_all(g_client, str, len) < 0) {
        g_client = -1;  // client disconnected: keep printing to the screen only
    }
    consoleUpdate(nullptr);
}

// Called from MicroPython (via mp_glue.c) while a script is running.
// Returns true if the script should be interrupted.
// ReSharper disable once CppUseInternalLinkage
bool app_poll_stop() {
    // Check at most every 20 ms so the script is not slowed down
    const u64 now = armGetSystemTick();
    if (now - g_last_poll < armNsToTicks(20ULL * 1000000ULL)) return false;
    g_last_poll = now;

    bool stop = false;

    // 1. The + and - combo on the console
    padUpdate(&g_hook_pad);
    bool held = (padGetButtons(&g_hook_pad) & STOP_COMBO) == STOP_COMBO;
    if (held && !g_combo_was_held) {
        const char *msg = "\n[stopped: + and - pressed]\n";
        app_output(msg, strlen(msg));
        stop = true;
    }
    g_combo_was_held = held;

    // 2. The client pressed Ctrl+C: it closes its side, recv returns 0
    if (g_client >= 0 && !g_client_eof) {
        struct pollfd pfd = { .fd = g_client, .events = POLLIN };
        if (poll(&pfd, 1, 0) > 0) {
            char tmp[64];
            if (recv(g_client, tmp, sizeof(tmp), 0) <= 0) {
                g_client_eof = true;
                stop = true;
            }
        }
    }

    // 3. The system asks the app to exit (HOME -> close)
    if (!g_quit && !appletMainLoop()) g_quit = true;
    if (g_quit) stop = true;

    return stop;
}

// Runs before every script: mounts the SD card as "/",
// makes the script's folder the working directory and adds import paths
// (the script's folder and /switch/nxtest/lib). Helper names are deleted afterwards.
static constexpr char SETUP_FMT[] =
    "try:\n"
    "    import vfs\n"
    "except ImportError:\n"
    "    import os as vfs\n"          // before MicroPython 1.23 mount lived in os
    "vfs.mount(vfs.VfsPosix(), '/')\n"
    "del vfs\n"
    "import os, sys\n"
    "os.chdir('%s')\n"
    "for _p in ('', '%s', '/switch/nxtest/lib'):\n"
    "    if _p not in sys.path:\n"
    "        sys.path.append(_p)\n"
    "del os, sys, _p\n";

// workdir is a path as the Python script sees it, e.g. "/switch/nxtest/scripts/games"
static void run_script(const char *code, const char *workdir) {
    // The path is inserted into a quoted Python string, so escape \ and '
    static char esc[2 * 1024];
    size_t j = 0;
    for (const char *p = workdir; *p && j + 3 < sizeof(esc); p++) {
        if (*p == '\\' || *p == '\'') esc[j++] = '\\';
        esc[j++] = *p;
    }
    esc[j] = '\0';

    static char setup[sizeof(SETUP_FMT) + 2 * sizeof(esc)];
    snprintf(setup, sizeof(setup), SETUP_FMT, esc, esc);

    int stack_top;  // address of a local variable = top of the stack for the GC
    mp_embed_init(mp_heap, sizeof(mp_heap), &stack_top);
    mp_embed_exec_str(setup);
    mp_embed_exec_str(code);
    mp_embed_deinit();
}

// ---------- screen: menu and output ----------

#define SCREEN_ROWS   45   // libnx console: 80x45 characters
#define SCREEN_COLS   80
#define HEADER_ROWS   4
#define FOOTER_ROWS   3
#define LIST_ROWS     (SCREEN_ROWS - HEADER_ROWS - FOOTER_ROWS)

#define MAX_FILES     512
#define MAX_NAME      256
#define PY_SCRIPTS    "/switch/nxtest/scripts"   // the same folder as Python sees it

enum { VIEW_MENU, VIEW_LOG };
static int  g_view = VIEW_MENU;
static bool g_menu_dirty = true;
static char g_status[SCREEN_COLS];
static char g_net_line[64] = "network: starting...";

typedef struct {
    char name[MAX_NAME];
    bool is_dir;
} Entry;

static Entry g_entries[MAX_FILES];
static int   g_entry_count = 0, g_cursor = 0, g_scroll = 0;
static char  g_cur_dir[MAX_PATH_LEN] = "";   // relative to scripts/, "" is the root
static int   g_scan_errno = 0;               // opendir error, 0 if the folder opened
static int   g_scan_other = 0;               // other entries (neither .py nor folders)

// Clears the screen without relying on consoleClear(): in practice it did not
// erase old output (it seems to clear only from the cursor position, and after
// long output the cursor is at the bottom). Here every row is explicitly
// overwritten with spaces, then the cursor goes back to the top.
static void screen_clear() {
    printf("\x1b[0m");
    for (int row = 1; row <= SCREEN_ROWS; row++) {
        printf("\x1b[%d;1H%*s", row, SCREEN_COLS, "");
    }
    printf("\x1b[1;1H");
}

// Full path to the current folder (for C) or to an entry in it
static void cur_dir_path(char *out, size_t size, const char *name) {
    snprintf(out, size, "%s%s%s%s%s", SCRIPTS_DIR,
             g_cur_dir[0] ? "/" : "", g_cur_dir,
             name ? "/" : "", name ? name : "");
}

static int cmp_entries(const void *a, const void *b) {
    const Entry *x = a, *y = b;
    if (x->is_dir != y->is_dir) return x->is_dir ? -1 : 1;   // folders first
    return strcasecmp(x->name, y->name);
}

static bool is_py_name(const char *n) {
    size_t l = strlen(n);
    return l > 3 && strcasecmp(n + l - 3, ".py") == 0;
}

// Lists folders and .py files in the current folder
static void scan_scripts() {
    g_entry_count = 0;
    g_scan_other = 0;
    g_scan_errno = 0;

    char dir[sizeof(SCRIPTS_DIR) + MAX_PATH_LEN + 2];
    cur_dir_path(dir, sizeof(dir), nullptr);
    DIR *d = opendir(dir);
    if (!d) {
        g_scan_errno = errno ? errno : EIO;
    } else {
        struct dirent *e;
        while ((e = readdir(d)) != nullptr && g_entry_count < MAX_FILES) {
            const char *name = e->d_name;
            if (name[0] == '.' || strlen(name) >= MAX_NAME) continue;  // hidden, "." and ".."

            char path[sizeof(dir) + 1 + MAX_NAME];
            snprintf(path, sizeof(path), "%s/%s", dir, name);
            struct stat st;
            bool stat_ok = stat(path, &st) == 0;

            if (stat_ok && S_ISDIR(st.st_mode)) {
                if (strcmp(name, "__pycache__") == 0) continue;
                strcpy(g_entries[g_entry_count].name, name);
                g_entries[g_entry_count++].is_dir = true;
            } else if (is_py_name(name)) {
                strcpy(g_entries[g_entry_count].name, name);
                g_entries[g_entry_count++].is_dir = false;
            } else {
                g_scan_other++;
            }
        }
        closedir(d);
    }
    qsort(g_entries, g_entry_count, sizeof(Entry), cmp_entries);
    if (g_cursor >= g_entry_count) g_cursor = g_entry_count > 0 ? g_entry_count - 1 : 0;
    g_menu_dirty = true;
}

static void select_entry(const char *name) {
    for (int i = 0; i < g_entry_count; i++) {
        if (strcmp(g_entries[i].name, name) == 0) {
            g_cursor = i;
            return;
        }
    }
}

static void enter_dir(const char *name) {
    size_t cur = strlen(g_cur_dir);
    if (cur + 1 + strlen(name) + 1 > sizeof(g_cur_dir)) return;  // too deep
    if (cur > 0) strcat(g_cur_dir, "/");
    strcat(g_cur_dir, name);
    g_cursor = 0;
    g_scroll = 0;
    g_status[0] = '\0';
    scan_scripts();
}

static void leave_dir() {
    if (g_cur_dir[0] == '\0') return;
    char child[MAX_NAME];
    char *slash = strrchr(g_cur_dir, '/');
    if (slash) {
        snprintf(child, sizeof(child), "%s", slash + 1);
        *slash = '\0';
    } else {
        snprintf(child, sizeof(child), "%s", g_cur_dir);
        g_cur_dir[0] = '\0';
    }
    g_cursor = 0;
    g_scroll = 0;
    g_status[0] = '\0';
    scan_scripts();
    select_entry(child);   // put the cursor on the folder we came from
}

static void draw_menu() {
    // keep the cursor inside the visible part of the list
    if (g_cursor < g_scroll) g_scroll = g_cursor;
    if (g_cursor >= g_scroll + LIST_ROWS) g_scroll = g_cursor - LIST_ROWS + 1;

    screen_clear();
    printf("\x1b[36mnxtest\x1b[0m   %s\n", g_net_line);
    printf("Password: %s\n", g_password);
    printf("scripts/%.60s%s  (%d)\n", g_cur_dir, g_cur_dir[0] ? "/" : "", g_entry_count);
    printf("-------------------------------------------------------------------------------\n");

    if (g_scan_errno) {
        printf("\n  \x1b[31mCannot open this folder: %s\x1b[0m\n", strerror(g_scan_errno));
    } else if (g_entry_count == 0) {
        printf("\n  No .py files here");
        if (g_scan_other > 0) printf(" (%d other files)", g_scan_other);
        printf(".\n\n  Upload from your computer:  send.py upload script.py\n");
    }

    for (int i = 0; i < LIST_ROWS && g_scroll + i < g_entry_count; i++) {
        int idx = g_scroll + i;
        char label[MAX_NAME + 2];
        snprintf(label, sizeof(label), "%s%s", g_entries[idx].name, g_entries[idx].is_dir ? "/" : "");
        if (idx == g_cursor) {
            printf("\x1b[30;47m> %-77.77s\x1b[0m\n", label);
        } else if (g_entries[idx].is_dir) {
            printf("  \x1b[36m%-77.77s\x1b[0m\n", label);
        } else {
            printf("  %-77.77s\n", label);
        }
    }

    // Footer: always at the bottom of the screen
    printf("\x1b[%d;1H", SCREEN_ROWS - FOOTER_ROWS + 1);
    printf("\x1b[32m%.79s\x1b[0m\n", g_status);
    printf("\x1b[33mUp/Down\x1b[0m select  \x1b[33mA\x1b[0m open/run  \x1b[33mB\x1b[0m up  "
           "\x1b[33mY\x1b[0m refresh  \x1b[33m+\x1b[0m exit\n");
    printf("While a script runs: hold \x1b[33m+\x1b[0m and \x1b[33m-\x1b[0m together to stop it");
    g_menu_dirty = false;
}

// Event (file uploaded, access denied...): status line in the menu, new line in the log
static void note_event(const char *fmt, ...) {
    va_list ap;
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
    va_start(ap, fmt);
    if (g_view == VIEW_LOG) {
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
        vprintf(fmt, ap);
        printf("\n");
    } else {
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
        vsnprintf(g_status, sizeof(g_status), fmt, ap);
        g_menu_dirty = true;
    }
    va_end(ap);
}

// Runs a script on a clean screen.
// client >= 0: output is also sent over the network, -1: screen only.
static void execute_script(const char *code, const char *title, const char *workdir, int client) {
    g_view = VIEW_LOG;
    screen_clear();
    printf("\x1b[36m--- %s ---\x1b[0m\n", title);
    consoleUpdate(nullptr);

    g_client = client;
    g_client_eof = false;
    g_combo_was_held = true;   // if + and - are already held at start, it is not a press
    hw_script_begin();
    run_script(code, workdir);
    hw_script_end();           // stop rumble etc. if the script left it on
    g_client = -1;

    printf("\n\x1b[30;47m %-78s\x1b[0m\n", "Script finished. Press B to return to the menu.");
    consoleUpdate(nullptr);
}

// Runs the file selected in the menu
static void run_selected() {
    if (g_entry_count == 0 || g_entries[g_cursor].is_dir) return;
    char name[MAX_NAME];
    strcpy(name, g_entries[g_cursor].name);

    char path[sizeof(SCRIPTS_DIR) + MAX_PATH_LEN + MAX_NAME + 2];
    cur_dir_path(path, sizeof(path), name);

    FILE *f = fopen(path, "rb");
    if (!f) {
        note_event("Cannot open %s", name);
        return;
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size < 0 || size > MAX_SCRIPT) {
        fclose(f);
        note_event("%s is too large (max %d KB)", name, MAX_SCRIPT / 1024);
        return;
    }

    char *code = malloc((size_t)size + 1);
    if (!code) {
        fclose(f);
        note_event("Out of memory");
        return;
    }
    size_t n = fread(code, 1, (size_t)size, f);
    fclose(f);
    code[n] = '\0';

    // Working folder and title, relative to scripts/
    static char workdir[sizeof(PY_SCRIPTS) + MAX_PATH_LEN + 2];
    snprintf(workdir, sizeof(workdir), "%s%s%s", PY_SCRIPTS, g_cur_dir[0] ? "/" : "", g_cur_dir);
    static char title[MAX_PATH_LEN + MAX_NAME + 2];
    snprintf(title, sizeof(title), "%s%s%s", g_cur_dir, g_cur_dir[0] ? "/" : "", name);

    execute_script(code, title, workdir, -1);
    free(code);
}

// ---------- file upload ----------

// Only relative paths inside /switch/nxtest are allowed: no "..", ".", "//",
// no leading or trailing '/', no ':' and no '\\'.
static bool safe_relpath(const char *p) {
    const size_t len = strlen(p);
    if (len == 0 || p[0] == '/' || p[len - 1] == '/') return false;
    if (strchr(p, ':') || strchr(p, '\\')) return false;
    const char *s = p;
    while (*s) {
        const char *e = strchr(s, '/');
        const size_t n = e ? (size_t)(e - s) : strlen(s);
        if (n == 0) return false;                                    // "//"
        if (n == 1 && s[0] == '.') return false;                     // "."
        if (n == 2 && s[0] == '.' && s[1] == '.') return false;      // ".."
        s += n;
        if (*s == '/') s++;
    }
    return true;
}

// Creates all intermediate folders for a file (like mkdir -p for its parent)
static void make_parent_dirs(char *full, size_t base_len) {
    for (char *p = full + base_len + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            mkdir(full, 0777);   // ignore errors: the folder may already exist
            *p = '/';
        }
    }
}

static void handle_upload(const int client) {
    uint16_t plen_be;
    if (recv_all(client, &plen_be, 2) < 0) return;
    uint16_t plen = ntohs(plen_be);
    if (plen == 0 || plen > MAX_PATH_LEN) {
        send_str(client, "error: bad path length\n");
        return;
    }

    char rel[MAX_PATH_LEN + 1];
    if (recv_all(client, rel, plen) < 0) return;
    rel[plen] = '\0';

    uint32_t size_be;
    if (recv_all(client, &size_be, 4) < 0) return;
    const uint32_t size = ntohl(size_be);

    if (!safe_relpath(rel)) {
        send_str(client, "error: path must be relative to /switch/nxtest and must not contain '..'\n");
        return;
    }
    if (size > MAX_UPLOAD) {
        send_str(client, "error: file too large (max 256 MB)\n");
        return;
    }

    static char full[sizeof(CONFIG_DIR) + 1 + MAX_PATH_LEN + 1];
    static char part[sizeof(full) + 5];
    snprintf(full, sizeof(full), "%s/%s", CONFIG_DIR, rel);
    snprintf(part, sizeof(part), "%s.part", full);
    make_parent_dirs(full, strlen(CONFIG_DIR));

    // Write to a temporary file and rename it at the end:
    // if the connection drops, the old version of the file stays intact.
    FILE *f = fopen(part, "wb");
    if (!f) {
        send_str(client, "error: cannot create file\n");
        return;
    }

    static char buf[64 * 1024];
    uint32_t left = size;
    bool net_ok = true, disk_ok = true;
    while (left > 0) {
        size_t want = left < sizeof(buf) ? left : sizeof(buf);
        ssize_t n = recv(client, buf, want, 0);
        if (n <= 0) { net_ok = false; break; }
        if (fwrite(buf, 1, (size_t)n, f) != (size_t)n) { disk_ok = false; break; }
        left -= (uint32_t)n;
    }
    if (fclose(f) != 0) disk_ok = false;

    if (!net_ok || !disk_ok) {
        remove(part);
        send_str(client, disk_ok ? "error: connection lost\n"
                                 : "error: write failed (SD card full?)\n");
        return;
    }

    remove(full);  // on the Switch rename does not overwrite an existing file
    if (rename(part, full) != 0) {
        remove(part);
        send_str(client, "error: cannot rename temporary file\n");
        return;
    }

    if (g_view == VIEW_MENU) scan_scripts();   // a new .py shows up in the list right away
    note_event("Uploaded %s (%u bytes)", rel, (unsigned)size);
    char msg[32];
    snprintf(msg, sizeof(msg), "ok %u\n", (unsigned)size);
    send_str(client, msg);
}

// ---------- connection handling ----------

static void handle_run(int client);

static void handle_client(int client) {
    // accept() may inherit non-blocking mode: switch back to blocking
    fcntl(client, F_SETFL, fcntl(client, F_GETFL, 0) & ~O_NONBLOCK);

    // If the client connects and stays silent, do not hang forever
    const struct timeval tv = { .tv_sec = 10, .tv_usec = 0 };
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    // 1. Greeting with a random nonce
    u8 hello[4 + 1 + NONCE_SIZE];
    memcpy(hello, PROTO_MAGIC, 4);
    hello[4] = PROTO_VERSION;
    randomGet(hello + 5, NONCE_SIZE);
    if (send_all(client, (const char *)hello, sizeof(hello)) < 0) return;

    // 2. Signature check
    u8 mac[MAC_SIZE], expected[MAC_SIZE];
    if (recv_all(client, mac, MAC_SIZE) < 0) return;
    hmacSha256CalculateMac(expected, g_password, strlen(g_password), hello + 5, NONCE_SIZE);
    if (!secure_equal(mac, expected, MAC_SIZE)) {
        note_event("Rejected a connection: wrong password");
        send_str(client, "error: wrong password\n");
        svcSleepThread(1000000000LL);  // 1 s delay slows down password guessing
        return;
    }

    // 3. Command
    u8 cmd;
    if (recv_all(client, &cmd, 1) < 0) return;
    switch (cmd) {
        case 'R': handle_run(client);    break;
        case 'U': handle_upload(client); break;
        default:  send_str(client, "error: unknown command\n"); break;
    }
}

static void handle_run(const int client) {
    uint32_t len_be;

    if (recv_all(client, &len_be, 4) < 0) return;

    const uint32_t len = ntohl(len_be);

    if (len == 0 || len > MAX_SCRIPT) {
        send_str(client, "error: bad script size\n");
        return;
    }

    char *code = malloc(len + 1);

    if (!code) {
        send_str(client, "error: out of memory\n");
        return;
    }

    if (recv_all(client, code, len) == 0) {
        code[len] = '\0';
        char title[64];
        snprintf(title, sizeof(title), "script from network (%u bytes)", (unsigned)len);
        execute_script(code, title, PY_SCRIPTS, client);
    }

    free(code);
}

int main() {
    consoleInit(nullptr);
    socketInitializeDefault();

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    hw_init();
    padInitializeDefault(&g_hook_pad);

    load_password();
    mkdir(CONFIG_DIR "/lib", 0777);      // folder for your own modules (import)
    mkdir(SCRIPTS_DIR, 0777);            // folder with scripts for the menu

    int server = socket(AF_INET, SOCK_STREAM, 0);
    int yes = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);

    bool net_ok = false;
    if (bind(server, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(server, 1) < 0) {
        snprintf(g_net_line, sizeof(g_net_line), "network: error, only local scripts");
    } else {
        net_ok = true;
        fcntl(server, F_SETFL, fcntl(server, F_GETFL, 0) | O_NONBLOCK);
        const struct in_addr ip = { .s_addr = (in_addr_t)gethostid() };
        snprintf(g_net_line, sizeof(g_net_line), "%s:%d", inet_ntoa(ip), PORT);
    }

    scan_scripts();
    int repeat_frames = 0;   // for auto-repeat while up/down is held

    while (!g_quit && appletMainLoop()) {
        padUpdate(&pad);
        u64 down = padGetButtonsDown(&pad);
        u64 held = padGetButtons(&pad);

        if (g_view == VIEW_MENU) {
            if (down & HidNpadButton_Plus) break;

            // Up/down: one step per press, auto-repeat while held
            u64 dirs = held & (HidNpadButton_AnyUp | HidNpadButton_AnyDown);
            if (dirs) {
                if (repeat_frames == 0 || (repeat_frames >= 20 && repeat_frames % 4 == 0)) {
                    int move = (dirs & HidNpadButton_AnyUp) ? -1 : 1;
                    int next = g_cursor + move;
                    if (next >= 0 && next < g_entry_count) {
                        g_cursor = next;
                        g_menu_dirty = true;
                    }
                }
                repeat_frames++;
            } else {
                repeat_frames = 0;
            }

            if (down & HidNpadButton_Y) {
                scan_scripts();
                note_event("List refreshed");
            }
            if (down & HidNpadButton_A && g_entry_count > 0) {
                if (g_entries[g_cursor].is_dir) {
                    enter_dir(g_entries[g_cursor].name);
                } else {
                    run_selected();
                    padUpdate(&pad);  // swallow presses made during the script
                }
            }
            if (down & HidNpadButton_B) {
                leave_dir();
            }
        } else {  // VIEW_LOG
            if (down & HidNpadButton_B) {
                g_view = VIEW_MENU;
                g_status[0] = '\0';
                scan_scripts();   // redraws the menu (and clears the screen)
            }
        }

        if (net_ok) {
            struct sockaddr_in peer;
            socklen_t peer_len = sizeof(peer);
            int client = accept(server, (struct sockaddr *)&peer, &peer_len);
            if (client >= 0) {
                handle_client(client);
                close(client);
                padUpdate(&pad);  // swallow presses made during the script
            }
        }

        if (g_view == VIEW_MENU && g_menu_dirty) draw_menu();
        consoleUpdate(nullptr);
        svcSleepThread(16 * 1000000LL);  // ~60 frames per second, no busy looping
    }

    close(server);
    hw_exit();
    socketExit();
    consoleExit(nullptr);
    return 0;
}
