// Python module `http`: HTTP(S) requests and downloads (libcurl).
// No libnx or curl headers here, only http_hw.h. Most scripts use lib/requests.py on top of it.
#include <stdio.h>
#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "http_hw.h"
#include "switch_hw.h"   // app_check_interrupt

static constexpr size_t DEFAULT_MAX_SIZE = 1024 * 1024;     // responses kept in memory
static constexpr size_t PATH_MAX_LEN = 1024;

[[noreturn]] static void raise_http(const int err) {
    if (err == HTTP_ERR_ABORTED) {
        app_check_interrupt();                              // raises the pending KeyboardInterrupt
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("http: aborted"));
    }
    const char *what;
    switch (err) {
        case HTTP_ERR_INIT:    what = "cannot initialize libcurl"; break;
        case HTTP_ERR_NOMEM:   what = "out of memory"; break;
        case HTTP_ERR_TOO_BIG: what = "response too large (use http.download)"; break;
        default:               what = http_hw_error(); break;
    }
    mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("http: %s"), what);
}

// dict {"Name": "value"} -> "Name: value\n..." in a GC buffer (nullptr if no headers)
static const char *headers_text(const mp_obj_t headers) {
    if (headers == mp_const_none) return nullptr;
    mp_map_t *map = mp_obj_dict_get_map(headers);
    vstr_t v;
    vstr_init(&v, 256);
    for (size_t i = 0; i < map->alloc; i++) {
        if (!mp_map_slot_is_filled(map, i)) continue;
        vstr_add_str(&v, mp_obj_str_get_str(map->table[i].key));
        vstr_add_str(&v, ": ");
        vstr_add_str(&v, mp_obj_str_get_str(map->table[i].value));
        vstr_add_char(&v, '\n');
    }
    return vstr_null_terminated_str(&v);
}

// "/switch/..." (as Python sees it) -> "sdmc:/switch/..."
static void c_path(const char *py_path, char *out, const size_t size) {
    if (py_path[0] == '/') snprintf(out, size, "sdmc:%s", py_path);
    else snprintf(out, size, "%s", py_path);
}

// http.request(method, url, data=None, headers=None, timeout=30, verify=True, max_size=1MB)
//   -> (status, body: bytes)
static mp_obj_t mod_request(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_method, ARG_url, ARG_data, ARG_headers, ARG_timeout, ARG_verify, ARG_max_size };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_method,   MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_url,      MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_data,     MP_ARG_OBJ,  { .u_obj = mp_const_none } },
        { MP_QSTR_headers,  MP_ARG_OBJ,  { .u_obj = mp_const_none } },
        { MP_QSTR_timeout,  MP_ARG_INT,  { .u_int = 30 } },
        { MP_QSTR_verify,   MP_ARG_BOOL, { .u_bool = true } },
        { MP_QSTR_max_size, MP_ARG_INT,  { .u_int = (mp_int_t)DEFAULT_MAX_SIZE } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);

    mp_buffer_info_t body = { .buf = nullptr, .len = 0 };
    if (args[ARG_data].u_obj != mp_const_none) {
        mp_get_buffer_raise(args[ARG_data].u_obj, &body, MP_BUFFER_READ);
    }
    const mp_int_t max_size = args[ARG_max_size].u_int;

    http_body_t out;
    const int status = http_hw_request(mp_obj_str_get_str(args[ARG_method].u_obj),
                                       mp_obj_str_get_str(args[ARG_url].u_obj),
                                       headers_text(args[ARG_headers].u_obj),
                                       body.buf, body.len,
                                       (int)args[ARG_timeout].u_int, args[ARG_verify].u_bool,
                                       max_size > 0 ? (size_t)max_size : DEFAULT_MAX_SIZE, &out);
    if (status < 0) raise_http(status);

    // Copy into a Python object and release the C buffer before anything can raise
    const mp_obj_t data = mp_obj_new_bytes((const byte *)out.data, out.len);
    http_hw_free(&out);
    const mp_obj_t items[2] = { MP_OBJ_NEW_SMALL_INT(status), data };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_request_obj, 2, mod_request);

// http.download(url, path, timeout=300, verify=True) -> status
// Streams the response into a file; the file is written only for a 2xx status.
static mp_obj_t mod_download(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_url, ARG_path, ARG_timeout, ARG_verify };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_url,     MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_path,    MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_timeout, MP_ARG_INT,  { .u_int = 300 } },
        { MP_QSTR_verify,  MP_ARG_BOOL, { .u_bool = true } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);

    char path[PATH_MAX_LEN];
    c_path(mp_obj_str_get_str(args[ARG_path].u_obj), path, sizeof(path));
    const int status = http_hw_download(mp_obj_str_get_str(args[ARG_url].u_obj), path,
                                        (int)args[ARG_timeout].u_int, args[ARG_verify].u_bool);
    if (status < 0) raise_http(status);
    return MP_OBJ_NEW_SMALL_INT(status);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_download_obj, 2, mod_download);

static const mp_rom_map_elem_t http_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_http) },
    { MP_ROM_QSTR(MP_QSTR_request),  MP_ROM_PTR(&mod_request_obj) },
    { MP_ROM_QSTR(MP_QSTR_download), MP_ROM_PTR(&mod_download_obj) },
};
static MP_DEFINE_CONST_DICT(http_module_globals, http_module_globals_table);

const mp_obj_module_t http_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&http_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_http, http_user_cmodule);