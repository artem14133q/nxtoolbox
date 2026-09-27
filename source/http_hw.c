// HTTP(S) client on top of libcurl (devkitPro package switch-curl).
// Compiled only with devkitA64 (lives in source/).
#include <switch.h>
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "http_hw.h"

// Defined in source/mp_glue.c: true if the script must stop. Does not raise,
// so it is safe inside libcurl callbacks; the KeyboardInterrupt stays pending.
bool app_stop_requested();

// The app folder; must match CONFIG_DIR in main.c. Can also be set from the Makefile:
// CFLAGS += -DAPP_DIR='"sdmc:/switch/NXToolBox"'
#ifndef APP_DIR
#define APP_DIR     "sdmc:/switch/NXToolBox"
#endif
#define USER_AGENT  "NXToolBox (Nintendo Switch; libcurl)"

// Trusted certificate authorities (Mozilla list from https://curl.se/docs/caextract.html):
// the user's copy first, then the one bundled in the .nro (see tools/bundle.py).
// Without either, the console's own certificate store is used.
static const char *const CA_FILES[] = {
    APP_DIR "/cacert.pem",
    APP_DIR "/sys/cacert.pem",
};

static bool s_initialized = false;
static char s_error[CURL_ERROR_SIZE];

static bool ensure_init() {
    if (!s_initialized) s_initialized = curl_global_init(CURL_GLOBAL_DEFAULT) == CURLE_OK;
    return s_initialized;
}

const char *http_hw_error() {
    return s_error;
}

void http_hw_free(http_body_t *body) {
    free(body->data);
    body->data = nullptr;
    body->len = 0;
}

// ---------- callbacks ----------

typedef struct {
    char  *data;
    size_t len, cap, max;
    bool   too_big;
} Buffer;

static size_t on_memory(const char *ptr, const size_t size, const size_t count, void *user) {
    Buffer *b = user;
    const size_t add = size * count;
    if (b->len + add > b->max) {
        b->too_big = true;
        return 0;                                   // makes libcurl stop with a write error
    }
    if (b->len + add + 1 > b->cap) {
        size_t cap = b->cap ? b->cap : 16 * 1024;
        while (cap < b->len + add + 1) cap *= 2;
        char *p = realloc(b->data, cap);
        if (!p) return 0;
        b->data = p;
        b->cap = cap;
    }
    memcpy(b->data + b->len, ptr, add);
    b->len += add;
    b->data[b->len] = '\0';
    return add;
}

static size_t on_file(const char *ptr, const size_t size, const size_t count, void *user) {
    return fwrite(ptr, size, count, (FILE *)user) * size;
}

// Called by libcurl regularly during a transfer: non-zero aborts it
static int on_progress(void *, curl_off_t, curl_off_t, curl_off_t, curl_off_t) {
    return app_stop_requested() ? 1 : 0;
}

// ---------- common setup ----------

static const char *ca_file() {
    for (size_t i = 0; i < sizeof(CA_FILES) / sizeof(CA_FILES[0]); i++) {
        struct stat st;
        if (stat(CA_FILES[i], &st) == 0 && S_ISREG(st.st_mode)) return CA_FILES[i];
    }
    return nullptr;
}

static CURL *make_handle(const char *url, const int timeout_s, const bool verify) {
    s_error[0] = '\0';
    if (!ensure_init()) return nullptr;
    CURL *c = curl_easy_init();
    if (!c) return nullptr;
    curl_easy_setopt(c, CURLOPT_URL, url);
    curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(c, CURLOPT_MAXREDIRS, 10L);
    curl_easy_setopt(c, CURLOPT_CONNECTTIMEOUT, 15L);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, (long)timeout_s);
    curl_easy_setopt(c, CURLOPT_USERAGENT, USER_AGENT);
    curl_easy_setopt(c, CURLOPT_ERRORBUFFER, s_error);
    curl_easy_setopt(c, CURLOPT_ACCEPT_ENCODING, "");      // compressed responses if available
    curl_easy_setopt(c, CURLOPT_NOPROGRESS, 0L);
    curl_easy_setopt(c, CURLOPT_XFERINFOFUNCTION, on_progress);
    if (verify) {
        // The console's certificate store may miss newer root CAs, so a cacert.pem is used
        // when there is one
        const char *ca = ca_file();
        if (ca) curl_easy_setopt(c, CURLOPT_CAINFO, ca);
        curl_easy_setopt(c, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(c, CURLOPT_SSL_VERIFYHOST, 2L);
    } else {
        curl_easy_setopt(c, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(c, CURLOPT_SSL_VERIFYHOST, 0L);
    }
    return c;
}

// "A: 1\nB: 2" -> curl header list
static struct curl_slist *make_headers(const char *headers) {
    struct curl_slist *list = nullptr;
    if (!headers) return nullptr;
    const char *p = headers;
    while (*p) {
        const char *end = strchr(p, '\n');
        const size_t n = end ? (size_t)(end - p) : strlen(p);
        if (n > 0 && n < 1024) {
            char line[1024];
            memcpy(line, p, n);
            line[n] = '\0';
            list = curl_slist_append(list, line);
        }
        p += n;
        if (*p == '\n') p++;
    }
    return list;
}

static int finish(CURL *c, const CURLcode rc, const bool too_big) {
    long status = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &status);
    curl_easy_cleanup(c);
    if (rc == CURLE_ABORTED_BY_CALLBACK) return HTTP_ERR_ABORTED;
    if (too_big) return HTTP_ERR_TOO_BIG;
    if (rc != CURLE_OK) {
        if (!s_error[0]) snprintf(s_error, sizeof(s_error), "%s", curl_easy_strerror(rc));
        return HTTP_ERR_NETWORK;
    }
    return (int)status;
}

// ---------- public API ----------

int http_hw_request(const char *method, const char *url, const char *headers,
                    const void *body, const size_t body_len, const int timeout_s,
                    const bool verify, const size_t max_size, http_body_t *out) {
    out->data = nullptr;
    out->len = 0;
    CURL *c = make_handle(url, timeout_s, verify);
    if (!c) return s_error[0] ? HTTP_ERR_NETWORK : HTTP_ERR_INIT;

    Buffer buf = { .max = max_size };
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, on_memory);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &buf);

    if (strcmp(method, "GET") != 0) curl_easy_setopt(c, CURLOPT_CUSTOMREQUEST, method);
    if (strcmp(method, "HEAD") == 0) curl_easy_setopt(c, CURLOPT_NOBODY, 1L);
    if (body) {
        // size first: the body may contain zero bytes
        curl_easy_setopt(c, CURLOPT_POSTFIELDSIZE_LARGE, (curl_off_t)body_len);
        curl_easy_setopt(c, CURLOPT_POSTFIELDS, body);
    }
    struct curl_slist *list = make_headers(headers);
    if (list) curl_easy_setopt(c, CURLOPT_HTTPHEADER, list);

    const CURLcode rc = curl_easy_perform(c);
    curl_slist_free_all(list);
    const int result = finish(c, rc, buf.too_big);
    if (result < 0) {
        free(buf.data);
        return result;
    }
    if (!buf.data) {                                   // empty body
        buf.data = malloc(1);
        if (!buf.data) return HTTP_ERR_NOMEM;
        buf.data[0] = '\0';
    }
    out->data = buf.data;
    out->len = buf.len;
    return result;
}

int http_hw_download(const char *url, const char *path, const int timeout_s, const bool verify) {
    char part[1024];
    snprintf(part, sizeof(part), "%s.part", path);

    CURL *c = make_handle(url, timeout_s, verify);
    if (!c) return s_error[0] ? HTTP_ERR_NETWORK : HTTP_ERR_INIT;

    FILE *f = fopen(part, "wb");
    if (!f) {
        curl_easy_cleanup(c);
        snprintf(s_error, sizeof(s_error), "cannot create %s", part);
        return HTTP_ERR_FILE;
    }
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, on_file);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, f);
    curl_easy_setopt(c, CURLOPT_FAILONERROR, 0L);

    const CURLcode rc = curl_easy_perform(c);
    const bool closed_ok = fclose(f) == 0;
    const int result = finish(c, rc, false);

    // Keep the file only for a complete 2xx response; the old version stays otherwise
    if (result < 200 || result > 299 || !closed_ok) {
        remove(part);
        if (result >= 0 && !closed_ok) {
            snprintf(s_error, sizeof(s_error), "write failed (SD card full?)");
            return HTTP_ERR_FILE;
        }
        return result;
    }
    remove(path);                                      // rename does not overwrite on the Switch
    if (rename(part, path) != 0) {
        remove(part);
        snprintf(s_error, sizeof(s_error), "cannot rename %s", part);
        return HTTP_ERR_FILE;
    }
    return result;
}