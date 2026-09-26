// Python module `switch`. No libnx headers here, only switch_hw.h.
#include "py/runtime.h"
#include "py/obj.h"
#include "switch_hw.h"

// Sleep in 20 ms slices so it can be interrupted (+ and -, Ctrl+C, HOME)
static void sleep_interruptible(mp_int_t ms) {
    while (ms > 0) {
        mp_int_t step = ms > 20 ? 20 : ms;
        hw_sleep_ms((uint32_t)step);
        ms -= step;
        app_check_interrupt();
    }
}

// ---------- system ----------

// switch.battery() -> int
static mp_obj_t mod_battery() {
    int pct = hw_battery();
    if (pct < 0) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("battery info unavailable"));
    }
    return mp_obj_new_int(pct);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_battery_obj, mod_battery);

// switch.sleep_ms(ms)
static mp_obj_t mod_sleep_ms(mp_obj_t ms_in) {
    sleep_interruptible(mp_obj_get_int(ms_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_sleep_ms_obj, mod_sleep_ms);

// switch.ticks_ms() -> int: milliseconds since the console was powered on
static mp_obj_t mod_ticks_ms() {
    return mp_obj_new_int_from_ull(hw_ticks_ms());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_ticks_ms_obj, mod_ticks_ms);

// switch.running() -> bool: call it in every loop
static mp_obj_t mod_running() {
    return mp_obj_new_bool(hw_running());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_running_obj, mod_running);

// ---------- buttons ----------

// switch.buttons() -> int (bit mask of held buttons)
static mp_obj_t mod_buttons() {
    return mp_obj_new_int_from_ull(hw_buttons_held());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_buttons_obj, mod_buttons);

// switch.buttons_down() -> int (pressed since the previous buttons_down call)
static mp_obj_t mod_buttons_down() {
    return mp_obj_new_int_from_ull(hw_buttons_down());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_buttons_down_obj, mod_buttons_down);

// ---------- sticks ----------

// switch.stick(n) -> (x, y), n: 0 left, 1 right; values from -1.0 to 1.0
// ReSharper disable once CppParameterMayBeConst
static mp_obj_t mod_stick(mp_obj_t index_in) {
    const mp_int_t index = mp_obj_get_int(index_in);
    if (index != 0 && index != 1) {
        mp_raise_ValueError(MP_ERROR_TEXT("stick must be 0 (left) or 1 (right)"));
    }
    float x, y;
    hw_stick((int)index, &x, &y);
    const mp_obj_t items[2] = { mp_obj_new_float(x), mp_obj_new_float(y) };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_stick_obj, mod_stick);

// ---------- touch screen ----------

// switch.touches() -> [(x, y), ...], handheld mode only
static mp_obj_t mod_touches() {
    int xs[HW_MAX_TOUCHES], ys[HW_MAX_TOUCHES];
    int n = hw_touches(xs, ys, HW_MAX_TOUCHES);
    // ReSharper disable once CppLocalVariableMayBeConst
    mp_obj_t list = mp_obj_new_list(0, nullptr);
    for (int i = 0; i < n; i++) {
        const mp_obj_t pt[2] = { MP_OBJ_NEW_SMALL_INT(xs[i]), MP_OBJ_NEW_SMALL_INT(ys[i]) };
        mp_obj_list_append(list, mp_obj_new_tuple(2, pt));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_touches_obj, mod_touches);

// ---------- rumble ----------

// switch.rumble(amp, ms=0, *, low=160, high=320)
//   amp  - strength 0.0..1.0 (0 turns it off)
//   ms   - if > 0: vibrate for this many milliseconds, then stop;
//          if 0: vibrate until rumble(0) is called
//   low, high - frequencies of the low and high bands in Hz
static mp_obj_t mod_rumble(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_amp, ARG_ms, ARG_low, ARG_high };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_amp,  MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_ms,   MP_ARG_INT,                   {.u_int = 0} },
        { MP_QSTR_low,  MP_ARG_KW_ONLY | MP_ARG_OBJ,  {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_high, MP_ARG_KW_ONLY | MP_ARG_OBJ,  {.u_obj = MP_OBJ_NULL} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    float amp  = (float)mp_obj_get_float(args[ARG_amp].u_obj);
    float low  = args[ARG_low].u_obj  == MP_OBJ_NULL ? 160.0f : (float)mp_obj_get_float(args[ARG_low].u_obj);
    float high = args[ARG_high].u_obj == MP_OBJ_NULL ? 320.0f : (float)mp_obj_get_float(args[ARG_high].u_obj);
    mp_int_t ms = args[ARG_ms].u_int;

    if (amp <= 0.0f) {
        hw_rumble_stop();
        return mp_const_none;
    }

    hw_rumble(amp, low, high);
    if (ms > 0) {
        // Stop the rumble even if the script is interrupted while waiting
        nlr_buf_t nlr;
        if (nlr_push(&nlr) == 0) {
            sleep_interruptible(ms);
            nlr_pop();
            hw_rumble_stop();
        } else {
            hw_rumble_stop();
            nlr_jump(nlr.ret_val);
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_rumble_obj, 1, mod_rumble);

// ---------- module table ----------

static const mp_rom_map_elem_t switch_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),     MP_ROM_QSTR(MP_QSTR_switch) },
    { MP_ROM_QSTR(MP_QSTR_battery),      MP_ROM_PTR(&mod_battery_obj) },
    { MP_ROM_QSTR(MP_QSTR_sleep_ms),     MP_ROM_PTR(&mod_sleep_ms_obj) },
    { MP_ROM_QSTR(MP_QSTR_running),      MP_ROM_PTR(&mod_running_obj) },
    { MP_ROM_QSTR(MP_QSTR_ticks_ms),     MP_ROM_PTR(&mod_ticks_ms_obj) },
    { MP_ROM_QSTR(MP_QSTR_buttons),      MP_ROM_PTR(&mod_buttons_obj) },
    { MP_ROM_QSTR(MP_QSTR_buttons_down), MP_ROM_PTR(&mod_buttons_down_obj) },
    { MP_ROM_QSTR(MP_QSTR_stick),        MP_ROM_PTR(&mod_stick_obj) },
    { MP_ROM_QSTR(MP_QSTR_touches),      MP_ROM_PTR(&mod_touches_obj) },
    { MP_ROM_QSTR(MP_QSTR_rumble),       MP_ROM_PTR(&mod_rumble_obj) },

    { MP_ROM_QSTR(MP_QSTR_A),      MP_ROM_INT(HW_BTN_A) },
    { MP_ROM_QSTR(MP_QSTR_B),      MP_ROM_INT(HW_BTN_B) },
    { MP_ROM_QSTR(MP_QSTR_X),      MP_ROM_INT(HW_BTN_X) },
    { MP_ROM_QSTR(MP_QSTR_Y),      MP_ROM_INT(HW_BTN_Y) },
    { MP_ROM_QSTR(MP_QSTR_L),      MP_ROM_INT(HW_BTN_L) },
    { MP_ROM_QSTR(MP_QSTR_R),      MP_ROM_INT(HW_BTN_R) },
    { MP_ROM_QSTR(MP_QSTR_ZL),     MP_ROM_INT(HW_BTN_ZL) },
    { MP_ROM_QSTR(MP_QSTR_ZR),     MP_ROM_INT(HW_BTN_ZR) },
    { MP_ROM_QSTR(MP_QSTR_PLUS),   MP_ROM_INT(HW_BTN_PLUS) },
    { MP_ROM_QSTR(MP_QSTR_MINUS),  MP_ROM_INT(HW_BTN_MINUS) },
    { MP_ROM_QSTR(MP_QSTR_UP),     MP_ROM_INT(HW_BTN_UP) },
    { MP_ROM_QSTR(MP_QSTR_DOWN),   MP_ROM_INT(HW_BTN_DOWN) },
    { MP_ROM_QSTR(MP_QSTR_LEFT),   MP_ROM_INT(HW_BTN_LEFT) },
    { MP_ROM_QSTR(MP_QSTR_RIGHT),  MP_ROM_INT(HW_BTN_RIGHT) },
    { MP_ROM_QSTR(MP_QSTR_LSTICK), MP_ROM_INT(HW_BTN_LSTICK) },   // stick click
    { MP_ROM_QSTR(MP_QSTR_RSTICK), MP_ROM_INT(HW_BTN_RSTICK) },
};
static MP_DEFINE_CONST_DICT(switch_module_globals, switch_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t switch_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&switch_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_switch, switch_user_cmodule);
