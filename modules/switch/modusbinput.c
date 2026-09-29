// Python module `usbinput`: USB keyboard and mouse (see lib/keys.py for a friendlier API).
// No libnx headers here, only usbinput_hw.h.
#include "py/runtime.h"
#include "py/obj.h"
#include "usbinput_hw.h"

// usbinput.keys() -> [code, ...]: HID usage codes of the held keys
static mp_obj_t mod_keys() {
    kbd_state_t s;
    usbinput_hw_keyboard(&s);
    const mp_obj_t list = mp_obj_new_list(0, nullptr);
    for (int word = 0; word < 4; word++) {
        for (int bit = 0; bit < 64; bit++) {
            if (s.keys[word] & (1ULL << bit)) {
                mp_obj_list_append(list, MP_OBJ_NEW_SMALL_INT(word * 64 + bit));
            }
        }
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_keys_obj, mod_keys);

// usbinput.modifiers() -> int: MOD_* bits
static mp_obj_t mod_modifiers() {
    kbd_state_t s;
    usbinput_hw_keyboard(&s);
    return mp_obj_new_int_from_ull(s.modifiers);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_modifiers_obj, mod_modifiers);

// usbinput.mouse() -> dict: x, y, dx, dy, wheel, wheel_h, buttons, connected
static mp_obj_t mod_mouse() {
    mouse_state_t s;
    usbinput_hw_mouse(&s);
    const mp_obj_t d = mp_obj_new_dict(8);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_x), mp_obj_new_int(s.x));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_y), mp_obj_new_int(s.y));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_dx), mp_obj_new_int(s.dx));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_dy), mp_obj_new_int(s.dy));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_wheel), mp_obj_new_int(s.wheel));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_wheel_h), mp_obj_new_int(s.wheel_h));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_buttons), MP_OBJ_NEW_SMALL_INT(s.buttons));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_connected), mp_obj_new_bool(s.connected));
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_mouse_obj, mod_mouse);

static const mp_rom_map_elem_t usbinput_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),  MP_ROM_QSTR(MP_QSTR_usbinput) },
    { MP_ROM_QSTR(MP_QSTR_keys),      MP_ROM_PTR(&mod_keys_obj) },
    { MP_ROM_QSTR(MP_QSTR_modifiers), MP_ROM_PTR(&mod_modifiers_obj) },
    { MP_ROM_QSTR(MP_QSTR_mouse),     MP_ROM_PTR(&mod_mouse_obj) },

    { MP_ROM_QSTR(MP_QSTR_MOD_CTRL),        MP_ROM_INT(KBD_MOD_CTRL) },
    { MP_ROM_QSTR(MP_QSTR_MOD_SHIFT),       MP_ROM_INT(KBD_MOD_SHIFT) },
    { MP_ROM_QSTR(MP_QSTR_MOD_LEFT_ALT),    MP_ROM_INT(KBD_MOD_LEFT_ALT) },
    { MP_ROM_QSTR(MP_QSTR_MOD_RIGHT_ALT),   MP_ROM_INT(KBD_MOD_RIGHT_ALT) },
    { MP_ROM_QSTR(MP_QSTR_MOD_GUI),         MP_ROM_INT(KBD_MOD_GUI) },
    { MP_ROM_QSTR(MP_QSTR_MOD_CAPS_LOCK),   MP_ROM_INT(KBD_MOD_CAPS_LOCK) },
    { MP_ROM_QSTR(MP_QSTR_MOD_SCROLL_LOCK), MP_ROM_INT(KBD_MOD_SCROLL_LOCK) },
    { MP_ROM_QSTR(MP_QSTR_MOD_NUM_LOCK),    MP_ROM_INT(KBD_MOD_NUM_LOCK) },

    { MP_ROM_QSTR(MP_QSTR_MOUSE_LEFT),    MP_ROM_INT(MOUSE_BTN_LEFT) },
    { MP_ROM_QSTR(MP_QSTR_MOUSE_RIGHT),   MP_ROM_INT(MOUSE_BTN_RIGHT) },
    { MP_ROM_QSTR(MP_QSTR_MOUSE_MIDDLE),  MP_ROM_INT(MOUSE_BTN_MIDDLE) },
    { MP_ROM_QSTR(MP_QSTR_MOUSE_FORWARD), MP_ROM_INT(MOUSE_BTN_FORWARD) },
    { MP_ROM_QSTR(MP_QSTR_MOUSE_BACK),    MP_ROM_INT(MOUSE_BTN_BACK) },
};
static MP_DEFINE_CONST_DICT(usbinput_module_globals, usbinput_module_globals_table);

const mp_obj_module_t usbinput_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&usbinput_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_usbinput, usbinput_user_cmodule);
