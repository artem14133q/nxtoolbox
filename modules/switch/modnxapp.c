// Python module `nxapp`: API for the Python start screen (launcher.py).
// No libnx headers here, only app_api.h.
#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "app_api.h"

// nxapp.run(path) - run this script after the launcher exits; the launcher should
// close its screen right after calling it. path is as Python sees it ("/switch/...").
// ReSharper disable once CppParameterMayBeConst
static mp_obj_t mod_run(mp_obj_t path_in) {
    app_request_run(mp_obj_str_get_str(path_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_run_obj, mod_run);

// nxapp.quit() - exit the app after the launcher exits
static mp_obj_t mod_quit() {
    app_request_quit();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_quit_obj, mod_quit);

// nxapp.restart() - start the launcher again after it exits (reloads launcher.py)
static mp_obj_t mod_restart() {
    app_request_restart();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_restart_obj, mod_restart);

// nxapp.poll() -> None or (kind, text); call it every frame to keep the network working
static mp_obj_t mod_poll() {
    char kind[16], text[160];
    if (!app_poll_network(kind, sizeof(kind), text, sizeof(text))) {
        return mp_const_none;
    }
    mp_obj_t items[2] = {
        mp_obj_new_str(kind, strlen(kind)),
        mp_obj_new_str(text, strlen(text)),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_poll_obj, mod_poll);

// nxapp.state() -> str kept between launcher runs
static mp_obj_t mod_state() {
    const char *s = app_get_state();
    return mp_obj_new_str(s, strlen(s));
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_state_obj, mod_state);

// nxapp.set_state(str)
static mp_obj_t mod_set_state(mp_obj_t s_in) {
    size_t len;
    const char *s = mp_obj_str_get_data(s_in, &len);
    app_set_state(s, len);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_set_state_obj, mod_set_state);

// nxapp.info() -> {"ip": str, "port": int, "password": str, "network": bool}
static mp_obj_t mod_info() {
    const char *ip = app_ip();
    const char *pw = app_password();
    mp_obj_t d = mp_obj_new_dict(4);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_ip), mp_obj_new_str(ip, strlen(ip)));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_port), MP_OBJ_NEW_SMALL_INT(app_port()));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_password), mp_obj_new_str(pw, strlen(pw)));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_network), mp_obj_new_bool(ip[0] != '\0'));
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_info_obj, mod_info);

static const mp_rom_map_elem_t nxapp_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),  MP_ROM_QSTR(MP_QSTR_nxapp) },
    { MP_ROM_QSTR(MP_QSTR_run),       MP_ROM_PTR(&mod_run_obj) },
    { MP_ROM_QSTR(MP_QSTR_quit),      MP_ROM_PTR(&mod_quit_obj) },
    { MP_ROM_QSTR(MP_QSTR_restart),   MP_ROM_PTR(&mod_restart_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll),      MP_ROM_PTR(&mod_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_state),     MP_ROM_PTR(&mod_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_state), MP_ROM_PTR(&mod_set_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_info),      MP_ROM_PTR(&mod_info_obj) },
};
static MP_DEFINE_CONST_DICT(nxapp_module_globals, nxapp_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t nxapp_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&nxapp_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_nxapp, nxapp_user_cmodule);