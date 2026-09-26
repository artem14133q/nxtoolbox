// HTTP(S) client: thin layer between the http MicroPython module and libcurl.
// This header must NOT include <switch.h> or <curl/curl.h>: the qstr generator reads it
// on the host PC.
#pragma once
#include <stddef.h>

// Negative results are errors; values >= 0 are HTTP status codes
enum {
    HTTP_ERR_INIT    = -1,   // libcurl could not be initialized
    HTTP_ERR_NETWORK = -2,   // DNS, connection, TLS, timeout... (text: http_hw_error())
    HTTP_ERR_ABORTED = -3,   // stopped by the user (+ and -, Ctrl+C, HOME)
    HTTP_ERR_NOMEM   = -4,
    HTTP_ERR_FILE    = -5,   // cannot write the destination file
    HTTP_ERR_TOO_BIG = -6,   // the response is larger than max_size
};

typedef struct {
    char  *data;   // malloc'ed, zero-terminated; release with http_hw_free()
    size_t len;
} http_body_t;

// method: "GET", "POST", ...; headers: "Name: value" lines separated by '\n', or nullptr
int  http_hw_request(const char *method, const char *url, const char *headers,
                     const void *body, size_t body_len, int timeout_s, bool verify,
                     size_t max_size, http_body_t *out);

// Streams the response into a file (C path, e.g. "sdmc:/switch/NXToolBox/x.py").
// The file is written only if the status is 2xx.
int  http_hw_download(const char *url, const char *path, int timeout_s, bool verify);

void        http_hw_free(http_body_t *body);
const char *http_hw_error();   // text of the last network error