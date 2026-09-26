// NXToolBox - runs Python scripts on the Switch: from an on-console menu or over the network.
//
// Start screen: launcher.py, a Python script (VIEW_LAUNCHER) that picks what to run through
// the nxapp module. If it is missing or fails (or - is held at startup), the built-in text
// menu is used instead (VIEW_MENU). Script output is shown in VIEW_LOG.
//
// Bundled files: launcher.py and lib/ are packed into the .nro (RomFS, see tools/bundle.py)
// and copied to /switch/NXToolBox/sys/ when the bundled version is newer than the installed
// one. /switch/NXToolBox/launcher.py and /switch/NXToolBox/lib/ override them (quick patches).
//
// Protocol (version 2), all numbers are big-endian:
//   1. Switch -> client: "NXPY" + version byte + 16 random bytes (nonce)
//   2. client -> Switch: HMAC-SHA256(password, nonce) (32 bytes) + command byte
//   3. Command 'R' (run):    4-byte length + script text.
//        The Switch runs the script, streams its output and closes the connection.
//        If the client closes its side (shutdown SHUT_WR), the script gets KeyboardInterrupt.
//      Command 'U' (upload): 2-byte path length + path (UTF-8, relative to /switch/NXToolBox,
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
#include "gfx_hw.h"
#include "app_api.h"

#define PORT          5555
#define MAX_SCRIPT    (512 * 1024)
#define HEAP_SIZE     (4 * 1024 * 1024)

#define CONFIG_DIR    "sdmc:/switch/NXToolBox"
#define PASSWORD_FILE CONFIG_DIR "/password.txt"
#define SCRIPTS_DIR   CONFIG_DIR "/scripts"      // scripts shown in the menu
#define LAUNCHER_FILE CONFIG_DIR "/launcher.py"  // user's start screen (overrides the bundled one)
#define SYS_DIR       CONFIG_DIR "/sys"          // bundled files installed from RomFS
#define SYS_LAUNCHER  SYS_DIR "/launcher.py"     // bundled start screen
#define PY_NXToolBox     "/switch/NXToolBox"           // CONFIG_DIR as Python sees it
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

// Network server (also polled by the launcher through nxapp.poll)
static int  g_server = -1;
static bool g_net_ok = false;
static char g_ip[32] = "";

// Stopping scripts
#define STOP_COMBO    (HidNpadButton_Plus | HidNpadButton_Minus)
static PadState g_hook_pad;          // separate pad state for the stop combo
static bool g_combo_was_held = false;
static bool g_client_eof = false;    // client pressed Ctrl+C (closed its side)
static bool g_quit = false;          // the system asked the app to exit
static u64  g_last_poll = 0;

// ---------- network ----------

static int send_all(const int fd, const char *buf, size_t len) {
    while (len > 0) {
        const ssize_t n = send(fd, buf, len, 0);
        if (n <= 0) return -1;
        buf += n;
        len -= n;
    }
    return 0;
}

static int send_str(const int fd, const char *s) {
    return send_all(fd, s, strlen(s));
}

static int recv_all(const int fd, void *buf, size_t len) {
    char *p = buf;
    while (len > 0) {
        const ssize_t n = recv(fd, p, len, 0);
        if (n <= 0) return -1;
        p += n;
        len -= n;
    }
    return 0;
}

// Constant-time comparison so the signature cannot be guessed from response timing
static bool secure_equal(const u8 *a, const u8 *b, const size_t len) {
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

// Output printed while the script is in graphics mode (the text console is off then).
// The last GFX_LOG_SIZE bytes are shown when the console comes back.
#define GFX_LOG_SIZE 4096
static char   g_gfx_log[GFX_LOG_SIZE];
static size_t g_gfx_log_len = 0;
static bool   g_gfx_log_cut = false;

static void gfx_log_append(const char *str, size_t len) {
    if (len >= GFX_LOG_SIZE) {
        str += len - GFX_LOG_SIZE;
        len = GFX_LOG_SIZE;
        g_gfx_log_len = 0;
        g_gfx_log_cut = true;
    } else if (g_gfx_log_len + len > GFX_LOG_SIZE) {
        const size_t drop = g_gfx_log_len + len - GFX_LOG_SIZE;
        memmove(g_gfx_log, g_gfx_log + drop, g_gfx_log_len - drop);
        g_gfx_log_len -= drop;
        g_gfx_log_cut = true;
    }
    memcpy(g_gfx_log + g_gfx_log_len, str, len);
    g_gfx_log_len += len;
}

// MicroPython sends all output (print, tracebacks) here.
// ReSharper disable once CppUseInternalLinkage
void app_output(const char *str, const size_t len) {
    const bool gfx = gfx_hw_active();
    if (gfx) gfx_log_append(str, len);
    else fwrite(str, 1, len, stdout);
    if (g_client >= 0 && send_all(g_client, str, len) < 0) {
        g_client = -1;  // client disconnected: keep printing to the screen only
    }
    if (!gfx) consoleUpdate(nullptr);
}

// Called by gfx_hw_end() when the text console has been re-created
void app_gfx_ended() {
    printf("\x1b[36m--- back from graphics mode ---\x1b[0m\n");
    if (g_gfx_log_len > 0) {
        if (g_gfx_log_cut) printf("[... earlier output cut ...]\n");
        fwrite(g_gfx_log, 1, g_gfx_log_len, stdout);
    }
    g_gfx_log_len = 0;
    g_gfx_log_cut = false;
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
    const bool held = (padGetButtons(&g_hook_pad) & STOP_COMBO) == STOP_COMBO;
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
// (the script's folder, /switch/NXToolBox/lib, then the bundled /switch/NXToolBox/sys/lib).
// Helper names are deleted afterwards.
static constexpr char SETUP_FMT[] =
    "try:\n"
    "    import vfs\n"
    "except ImportError:\n"
    "    import os as vfs\n"          // before MicroPython 1.23 mount lived in os
    "vfs.mount(vfs.VfsPosix(), '/')\n"
    "del vfs\n"
    "import os, sys\n"
    "os.chdir('%s')\n"
    "for _p in ('', '%s', '/switch/NXToolBox/lib', '/switch/NXToolBox/sys/lib'):\n"
    "    if _p not in sys.path:\n"
    "        sys.path.append(_p)\n"
    "del os, sys, _p\n";

// workdir is a path as the Python script sees it, e.g. "/switch/NXToolBox/scripts/games"
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
    // Leave graphics mode while MicroPython is still alive: switching the screen
    // back after mp_embed_deinit() crashed the app (hw_script_end() is only a fallback).
    gfx_hw_end();
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
#define PY_SCRIPTS    "/switch/NXToolBox/scripts"   // the same folder as Python sees it

enum { VIEW_MENU, VIEW_LOG, VIEW_LAUNCHER };
static int  g_view = VIEW_MENU;
static bool g_menu_dirty = true;
static char g_status[SCREEN_COLS];
static char g_net_line[64] = "network: starting...";

// ---- launcher ----
enum { LREQ_NONE, LREQ_RUN, LREQ_QUIT, LREQ_RESTART, LREQ_NETRUN };
static int   g_lreq = LREQ_NONE;                 // what the launcher asked for
static char  g_lreq_path[MAX_PATH_LEN + 64];     // script to run (Python path)
static bool  g_launcher_failed = false;          // use the built-in menu instead
static char  g_launcher_state[512] = "";         // kept between launcher runs
static char  g_ev_kind[16], g_ev_text[160];      // event for nxapp.poll()
static bool  g_ev_new = false;
static char *g_pending_code = nullptr;           // network script received during the launcher
static int   g_pending_client = -1;

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
static void cur_dir_path(char *out, const size_t size, const char *name) {
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
    const size_t l = strlen(n);
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
            const bool stat_ok = stat(path, &st) == 0;

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
    const size_t cur = strlen(g_cur_dir);
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
    printf("\x1b[36mNXToolBox\x1b[0m   %s\n", g_net_line);
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
        const int idx = g_scroll + i;
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
    printf("\x1b[33mUp/Down\x1b[0m select \x1b[33mA\x1b[0m open/run \x1b[33mB\x1b[0m up "
           "\x1b[33mY\x1b[0m refresh \x1b[33mX\x1b[0m launcher \x1b[33m+\x1b[0m exit\n");
    printf("While a script runs: hold \x1b[33m+\x1b[0m and \x1b[33m-\x1b[0m together to stop it");
    g_menu_dirty = false;
}

// Event for the launcher (returned by nxapp.poll)
static void launcher_event(const char *kind, const char *fmt, ...) {
    va_list ap;
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
    va_start(ap, fmt);
    snprintf(g_ev_kind, sizeof(g_ev_kind), "%s", kind);
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
    vsnprintf(g_ev_text, sizeof(g_ev_text), fmt, ap);
    va_end(ap);
    g_ev_new = true;
}

// Event (file uploaded, access denied...): status line in the menu, new line in the log,
// an "info" event for the launcher
static void note_event(const char *fmt, ...) {
    va_list ap;
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
    va_start(ap, fmt);
    if (g_view == VIEW_LAUNCHER) {
        snprintf(g_ev_kind, sizeof(g_ev_kind), "info");
    // ReSharper disable once CppLocalVariableMightNotBeInitialized
        vsnprintf(g_ev_text, sizeof(g_ev_text), fmt, ap);
        g_ev_new = true;
    } else if (g_view == VIEW_LOG) {
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
static void execute_script(const char *code, const char *title, const char *workdir, const int client) {
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

    printf("\n\x1b[30;47m %-78s\x1b[0m\n", "Script finished. Press B to go back.");
    consoleUpdate(nullptr);
}

// Reads a whole file into a malloc'ed, zero-terminated buffer (nullptr on error)
static char *read_file(const char *path, const char *name_for_errors) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        note_event("Cannot open %s", name_for_errors);
        return nullptr;
    }
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size < 0 || size > MAX_SCRIPT) {
        fclose(f);
        note_event("%s is too large (max %d KB)", name_for_errors, MAX_SCRIPT / 1024);
        return nullptr;
    }
    char *code = malloc((size_t)size + 1);
    if (!code) {
        fclose(f);
        note_event("Out of memory");
        return nullptr;
    }
    const size_t n = fread(code, 1, (size_t)size, f);
    fclose(f);
    code[n] = '\0';
    return code;
}

// Runs a script file. py_path is the path as Python sees it ("/switch/NXToolBox/...").
// The script's folder becomes its working directory.
static void run_file(const char *py_path) {
    char path[MAX_PATH_LEN + 80];
    snprintf(path, sizeof(path), "sdmc:%s", py_path);
    char *code = read_file(path, py_path);
    if (!code) return;

    static char workdir[MAX_PATH_LEN + 64];
    snprintf(workdir, sizeof(workdir), "%s", py_path);
    char *slash = strrchr(workdir, '/');
    if (slash && slash != workdir) *slash = '\0';

    // Title: path relative to scripts/ if it is there
    const char *title = py_path;
    const size_t prefix = strlen(PY_SCRIPTS "/");
    if (strncmp(py_path, PY_SCRIPTS "/", prefix) == 0) title = py_path + prefix;

    execute_script(code, title, workdir, -1);
    free(code);
}

// Runs the file selected in the built-in menu
static void run_selected() {
    if (g_entry_count == 0 || g_entries[g_cursor].is_dir) return;
    static char py_path[sizeof(PY_SCRIPTS) + MAX_PATH_LEN + MAX_NAME + 2];
    snprintf(py_path, sizeof(py_path), "%s%s%s/%s", PY_SCRIPTS,
             g_cur_dir[0] ? "/" : "", g_cur_dir, g_entries[g_cursor].name);
    run_file(py_path);
}

// ---------- file upload ----------

// Only relative paths inside /switch/NXToolBox are allowed: no "..", ".", "//",
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
static void make_parent_dirs(char *full, const size_t base_len) {
    for (char *p = full + base_len + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            mkdir(full, 0777);   // ignore errors: the folder may already exist
            *p = '/';
        }
    }
}

static void handle_upload(const int client) {
    uint16_t len_be;
    if (recv_all(client, &len_be, 2) < 0) return;
    const uint16_t len = ntohs(len_be);
    if (len == 0 || len > MAX_PATH_LEN) {
        send_str(client, "error: bad path length\n");
        return;
    }

    char rel[MAX_PATH_LEN + 1];
    if (recv_all(client, rel, len) < 0) return;
    rel[len] = '\0';

    uint32_t size_be;
    if (recv_all(client, &size_be, 4) < 0) return;
    const uint32_t size = ntohl(size_be);

    if (!safe_relpath(rel)) {
        send_str(client, "error: path must be relative to /switch/NXToolBox and must not contain '..'\n");
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
        const size_t want = left < sizeof(buf) ? left : sizeof(buf);
        const ssize_t n = recv(client, buf, want, 0);
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
    if (g_view == VIEW_LAUNCHER) launcher_event("upload", "%s", rel);
    else note_event("Uploaded %s (%u bytes)", rel, (unsigned)size);
    char msg[32];
    snprintf(msg, sizeof(msg), "ok %u\n", (unsigned)size);
    send_str(client, msg);
}

// ---------- connection handling ----------

static bool handle_run(int client);

// Returns true if the connection must stay open (a network script is waiting
// for the launcher to exit; the main loop runs it and closes the socket).
static bool handle_client(const int client) {
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
    if (send_all(client, (const char *)hello, sizeof(hello)) < 0) return false;

    // 2. Signature check
    u8 mac[MAC_SIZE], expected[MAC_SIZE];
    if (recv_all(client, mac, MAC_SIZE) < 0) return false;
    hmacSha256CalculateMac(expected, g_password, strlen(g_password), hello + 5, NONCE_SIZE);
    if (!secure_equal(mac, expected, MAC_SIZE)) {
        note_event("Rejected a connection: wrong password");
        send_str(client, "error: wrong password\n");
        svcSleepThread(1000000000LL);  // 1 s delay slows down password guessing
        return false;
    }

    // 3. Command
    u8 cmd;
    if (recv_all(client, &cmd, 1) < 0) return false;
    switch (cmd) {
        case 'R': return handle_run(client);
        case 'U': handle_upload(client); return false;
        default:  send_str(client, "error: unknown command\n"); return false;
    }
}

static void run_network_script(const char *code, const int client) {
    char title[64];
    snprintf(title, sizeof(title), "script from network (%u bytes)", (unsigned)strlen(code));
    execute_script(code, title, PY_SCRIPTS, client);
}

static bool handle_run(const int client) {
    uint32_t len_be;

    if (recv_all(client, &len_be, 4) < 0) return false;

    const uint32_t len = ntohl(len_be);

    if (len == 0 || len > MAX_SCRIPT) {
        send_str(client, "error: bad script size\n");
        return false;
    }

    char *code = malloc(len + 1);

    if (!code) {
        send_str(client, "error: out of memory\n");
        return false;
    }

    if (recv_all(client, code, len) != 0) {
        free(code);
        return false;
    }
    code[len] = '\0';

    if (g_view == VIEW_LAUNCHER) {
        // MicroPython is busy with the launcher: keep the script and the connection,
        // the launcher exits and the main loop runs it
        g_pending_code = code;
        g_pending_client = client;
        g_lreq = LREQ_NETRUN;
        launcher_event("run", "script from network (%u bytes)", (unsigned)len);
        return true;
    }

    run_network_script(code, client);
    free(code);
    return false;
}

// ---------- launcher API (called from the nxapp module) ----------

// ReSharper disable once CppUseInternalLinkage
void app_request_run(const char *py_path) {
    snprintf(g_lreq_path, sizeof(g_lreq_path), "%s", py_path);
    g_lreq = LREQ_RUN;
}

// ReSharper disable once CppUseInternalLinkage
void app_request_quit() { g_lreq = LREQ_QUIT; }

// ReSharper disable once CppUseInternalLinkage
void app_request_restart() { g_lreq = LREQ_RESTART; }

// ReSharper disable once CppUseInternalLinkage
bool app_poll_network(char *kind, const size_t kind_size, char *text, const size_t text_size) {
    if (!g_net_ok || g_pending_client >= 0) return false;
    struct sockaddr_in peer;
    socklen_t peer_len = sizeof(peer);
    const int client = accept(g_server, (struct sockaddr *)&peer, &peer_len);
    if (client < 0) return false;

    g_ev_new = false;
    if (!handle_client(client)) close(client);
    if (!g_ev_new) return false;
    snprintf(kind, kind_size, "%s", g_ev_kind);
    snprintf(text, text_size, "%s", g_ev_text);
    return true;
}

// ReSharper disable once CppUseInternalLinkage
const char *app_get_state() { return g_launcher_state; }

// ReSharper disable once CppUseInternalLinkage
void app_set_state(const char *s, size_t len) {
    if (len >= sizeof(g_launcher_state)) len = sizeof(g_launcher_state) - 1;
    memcpy(g_launcher_state, s, len);
    g_launcher_state[len] = '\0';
}

// ReSharper disable once CppUseInternalLinkage
const char *app_ip() { return g_ip; }

// ReSharper disable once CppUseInternalLinkage
int app_port() { return PORT; }

// ReSharper disable once CppUseInternalLinkage
const char *app_password() { return g_password; }

// ---------- bundled files (RomFS -> /switch/NXToolBox/sys) ----------

// First line of a text file without the line break ("" if there is no file)
static void read_line(const char *path, char *out, const size_t size) {
    out[0] = '\0';
    FILE *f = fopen(path, "r");
    if (!f) return;
    if (fgets(out, (int)size, f)) out[strcspn(out, "\r\n")] = '\0';
    fclose(f);
}

static bool copy_file(const char *from, const char *to) {
    FILE *in = fopen(from, "rb");
    if (!in) return false;
    FILE *out = fopen(to, "wb");
    if (!out) {
        fclose(in);
        return false;
    }
    static char buf[16 * 1024];
    bool ok = true;
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        if (fwrite(buf, 1, n, out) != n) {
            ok = false;
            break;
        }
    }
    fclose(in);
    if (fclose(out) != 0) ok = false;
    return ok;
}

// Copies a folder tree, overwriting files. VERSION files are skipped: the caller writes
// VERSION last, so an interrupted copy is repeated on the next start.
static void copy_tree(const char *from, const char *to) {
    mkdir(to, 0777);
    DIR *d = opendir(from);
    if (!d) return;
    const size_t from_len = strlen(from);
    const char *sep = from_len > 0 && from[from_len - 1] == '/' ? "" : "/";
    const struct dirent *e;
    while ((e = readdir(d)) != nullptr) {
        if (e->d_name[0] == '.' || strcmp(e->d_name, "VERSION") == 0) continue;
        char src[MAX_PATH_LEN], dst[MAX_PATH_LEN];
        snprintf(src, sizeof(src), "%s%s%s", from, sep, e->d_name);
        snprintf(dst, sizeof(dst), "%s/%s", to, e->d_name);
        struct stat st;
        if (stat(src, &st) == 0 && S_ISDIR(st.st_mode)) copy_tree(src, dst);
        else copy_file(src, dst);
    }
    closedir(d);
}

// Removes the files (not folders) in a folder: modules dropped from the bundle go away
static void remove_files(const char *dir) {
    DIR *d = opendir(dir);
    if (!d) return;
    const struct dirent *e;
    while ((e = readdir(d)) != nullptr) {
        char path[MAX_PATH_LEN];
        snprintf(path, sizeof(path), "%s/%s", dir, e->d_name);
        struct stat st;
        if (stat(path, &st) == 0 && S_ISREG(st.st_mode)) remove(path);
    }
    closedir(d);
}

// Installs the files bundled in the .nro if they are newer than the installed ones.
// Online updates (launcher.py) can make the installed copy newer: it is kept then.
static void install_bundle() {
    if (R_FAILED(romfsInit())) return;                 // built without RomFS
    char bundled[32], installed[32];
    read_line("romfs:/VERSION", bundled, sizeof(bundled));
    read_line(SYS_DIR "/VERSION", installed, sizeof(installed));
    if (bundled[0] && strcmp(bundled, installed) > 0) {
        printf("Installing bundled files, version %s...\n", bundled);
        consoleUpdate(nullptr);
        mkdir(SYS_DIR, 0777);
        remove_files(SYS_DIR "/lib");
        copy_tree("romfs:/", SYS_DIR);
        copy_file("romfs:/VERSION", SYS_DIR "/VERSION");
    }
    romfsExit();
}

// ---------- launcher ----------

// The user's launcher.py wins over the bundled one; nullptr if there is none
static const char *launcher_path() {
    struct stat st;
    if (stat(LAUNCHER_FILE, &st) == 0 && S_ISREG(st.st_mode)) return LAUNCHER_FILE;
    if (stat(SYS_LAUNCHER, &st) == 0 && S_ISREG(st.st_mode)) return SYS_LAUNCHER;
    return nullptr;
}

static bool launcher_exists() {
    return launcher_path() != nullptr;
}

static void enter_menu() {
    g_view = VIEW_MENU;
    g_status[0] = '\0';
    scan_scripts();   // redraws the menu (and clears the screen)
}

// Where B goes from the output screen
static void leave_log() {
    if (!g_launcher_failed && launcher_exists()) g_view = VIEW_LAUNCHER;
    else enter_menu();
}

// Runs launcher.py in a fresh interpreter and then does what it asked for.
// Returns false if the app should exit.
static bool run_launcher() {
    const char *path = launcher_path();
    char *code = path ? read_file(path, "launcher.py") : nullptr;
    if (!code) {
        g_launcher_failed = true;
        enter_menu();
        return true;
    }

    // Loading the launcher (and ui.py) takes a moment; errors that happen before it
    // switches to graphics are printed right below this line
    screen_clear();
    printf("\x1b[36mStarting launcher...\x1b[0m\n");
    consoleUpdate(nullptr);

    g_view = VIEW_LAUNCHER;
    g_lreq = LREQ_NONE;
    g_client = -1;
    g_client_eof = false;
    g_combo_was_held = true;
    hw_script_begin();
    run_script(code, PY_NXToolBox);
    hw_script_end();
    free(code);

    switch (g_lreq) {
        case LREQ_QUIT:
            return false;
        case LREQ_RESTART:
            return true;                           // the main loop starts the launcher again
        case LREQ_RUN:
            run_file(g_lreq_path);
            if (g_view != VIEW_LOG) leave_log();   // the file could not be opened
            return true;
        case LREQ_NETRUN:
            run_network_script(g_pending_code, g_pending_client);
            free(g_pending_code);
            close(g_pending_client);
            g_pending_code = nullptr;
            g_pending_client = -1;
            return true;
        default:
            // The launcher ended without a request: an error (the traceback is on the
            // screen already), + and - were pressed, or it simply returned.
            g_launcher_failed = true;
            g_view = VIEW_LOG;
            printf("\n\x1b[30;47m %-78s\x1b[0m\n",
                   "The launcher stopped. Press B for the built-in menu (X there retries).");
            consoleUpdate(nullptr);
            return true;
    }
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
    install_bundle();                    // launcher.py and lib/ from the .nro

    g_server = socket(AF_INET, SOCK_STREAM, 0);
    constexpr int yes = 1;
    setsockopt(g_server, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);

    if (bind(g_server, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(g_server, 1) < 0) {
        snprintf(g_net_line, sizeof(g_net_line), "network: error, only local scripts");
    } else {
        g_net_ok = true;
        fcntl(g_server, F_SETFL, fcntl(g_server, F_GETFL, 0) | O_NONBLOCK);
        const struct in_addr ip = { .s_addr = (in_addr_t)gethostid() };
        snprintf(g_ip, sizeof(g_ip), "%s", inet_ntoa(ip));
        snprintf(g_net_line, sizeof(g_net_line), "%s:%d", g_ip, PORT);
    }

    // Holding - at startup skips the Python launcher (recovery if it is broken)
    padUpdate(&pad);
    if (padGetButtons(&pad) & HidNpadButton_Minus) g_launcher_failed = true;

    if (!g_launcher_failed && launcher_exists()) g_view = VIEW_LAUNCHER;
    else enter_menu();
    int repeat_frames = 0;   // for auto-repeat while up/down is held

    while (!g_quit && appletMainLoop()) {
        if (g_view == VIEW_LAUNCHER) {
            if (!run_launcher()) break;
            padUpdate(&pad);  // swallow presses made in the launcher
            padUpdate(&pad);
            continue;
        }

        padUpdate(&pad);
        const u64 down = padGetButtonsDown(&pad);
        const u64 held = padGetButtons(&pad);

        if (g_view == VIEW_MENU) {
            if (down & HidNpadButton_Plus) break;

            // Up/down: one step per press, auto-repeat while held
            const u64 dirs = held & (HidNpadButton_AnyUp | HidNpadButton_AnyDown);
            if (dirs) {
                if (repeat_frames == 0 || (repeat_frames >= 20 && repeat_frames % 4 == 0)) {
                    const int move = dirs & HidNpadButton_AnyUp ? -1 : 1;
                    const int next = g_cursor + move;
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
            if (down & HidNpadButton_X) {
                if (launcher_exists()) {
                    g_launcher_failed = false;
                    g_view = VIEW_LAUNCHER;
                    continue;
                }
                note_event("No launcher.py (neither bundled nor in /switch/NXToolBox)");
            }
        } else {  // VIEW_LOG
            if (down & HidNpadButton_B) {
                leave_log();
                if (g_view == VIEW_LAUNCHER) continue;
            }
        }

        if (g_net_ok) {
            struct sockaddr_in peer;
            socklen_t peer_len = sizeof(peer);
            const int client = accept(g_server, (struct sockaddr *)&peer, &peer_len);
            if (client >= 0) {
                if (!handle_client(client)) close(client);   // never kept open outside the launcher
                padUpdate(&pad);  // swallow presses made during the script
            }
        }

        if (g_view == VIEW_MENU && g_menu_dirty) draw_menu();
        consoleUpdate(nullptr);
        svcSleepThread(16 * 1000000LL);  // ~60 frames per second, no busy looping
    }

    close(g_server);
    hw_exit();
    socketExit();
    consoleExit(nullptr);
    return 0;
}