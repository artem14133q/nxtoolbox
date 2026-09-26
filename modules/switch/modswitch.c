// Python module `switch`. No libnx headers here, only switch_hw.h.
#include "py/runtime.h"
#include "py/obj.h"
#include "switch_hw.h"

// Sleep in 20 ms slices so it can be interrupted (+ and -, Ctrl+C, HOME)
static void sleep_interruptible(mp_int_t ms) {
    while (ms > 0) {
        const mp_int_t step = ms > 20 ? 20 : ms;
        hw_sleep_ms((uint32_t)step);
        ms -= step;
        app_check_interrupt();
    }
}

// ---------- system ----------

// switch.battery() -> int
static mp_obj_t mod_battery() {
    const int pct = hw_battery();
    if (pct < 0) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("battery info unavailable"));
    }
    return mp_obj_new_int(pct);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_battery_obj, mod_battery);

// switch.sleep_ms(ms)
// ReSharper disable once CppParameterMayBeConst
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
static mp_obj_t mod_rumble(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_amp, ARG_ms, ARG_low, ARG_high };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_amp,  MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_ms,   MP_ARG_INT,                   {.u_int = 0} },
        { MP_QSTR_low,  MP_ARG_KW_ONLY | MP_ARG_OBJ,  {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_high, MP_ARG_KW_ONLY | MP_ARG_OBJ,  {.u_obj = MP_OBJ_NULL} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    const float amp  = (float)mp_obj_get_float(args[ARG_amp].u_obj);
    const float low  = args[ARG_low].u_obj  == MP_OBJ_NULL ? 160.0f : (float)mp_obj_get_float(args[ARG_low].u_obj);
    const float high = args[ARG_high].u_obj == MP_OBJ_NULL ? 320.0f : (float)mp_obj_get_float(args[ARG_high].u_obj);
    const mp_int_t ms = args[ARG_ms].u_int;

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


// switch.keyboard(text="", hint="") -> str, or None if cancelled
static mp_obj_t mod_keyboard(const size_t n_args, const mp_obj_t *args) {
    const char *initial = n_args > 0 ? mp_obj_str_get_str(args[0]) : "";
    const char *hint = n_args > 1 ? mp_obj_str_get_str(args[1]) : "";
    static char out[1024];
    if (!hw_keyboard(initial, hint, out, sizeof(out))) return mp_const_none;
    return mp_obj_new_str(out, strlen(out));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_keyboard_obj, 0, 2, mod_keyboard);

// ---------- module table ----------

static const mp_rom_map_elem_t switch_module_globals_table[] = {
    {.key = MP_ROM_QSTR(MP_QSTR___name__), .value = MP_ROM_QSTR(MP_QSTR_switch)},
    {.key = MP_ROM_QSTR(MP_QSTR_battery), .value = MP_ROM_PTR(&mod_battery_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_sleep_ms), .value = MP_ROM_PTR(&mod_sleep_ms_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_running), .value = MP_ROM_PTR(&mod_running_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_ticks_ms), .value = MP_ROM_PTR(&mod_ticks_ms_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_buttons), .value = MP_ROM_PTR(&mod_buttons_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_buttons_down), .value = MP_ROM_PTR(&mod_buttons_down_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_stick), .value = MP_ROM_PTR(&mod_stick_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_touches), .value = MP_ROM_PTR(&mod_touches_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_rumble), .value = MP_ROM_PTR(&mod_rumble_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_keyboard), .value = MP_ROM_PTR(&mod_keyboard_obj)},

    {.key = MP_ROM_QSTR(MP_QSTR_A), .value = MP_ROM_INT(HW_BTN_A)},
    {.key = MP_ROM_QSTR(MP_QSTR_B), .value = MP_ROM_INT(HW_BTN_B)},
    {.key = MP_ROM_QSTR(MP_QSTR_X), .value = MP_ROM_INT(HW_BTN_X)},
    {.key = MP_ROM_QSTR(MP_QSTR_Y), .value = MP_ROM_INT(HW_BTN_Y)},
    {.key = MP_ROM_QSTR(MP_QSTR_L), .value = MP_ROM_INT(HW_BTN_L)},
    {.key = MP_ROM_QSTR(MP_QSTR_R), .value = MP_ROM_INT(HW_BTN_R)},
    {.key = MP_ROM_QSTR(MP_QSTR_ZL), .value = MP_ROM_INT(HW_BTN_ZL)},
    {.key = MP_ROM_QSTR(MP_QSTR_ZR), .value = MP_ROM_INT(HW_BTN_ZR)},
    {.key = MP_ROM_QSTR(MP_QSTR_PLUS), .value = MP_ROM_INT(HW_BTN_PLUS)},
    {.key = MP_ROM_QSTR(MP_QSTR_MINUS), .value = MP_ROM_INT(HW_BTN_MINUS)},
    {.key = MP_ROM_QSTR(MP_QSTR_UP), .value = MP_ROM_INT(HW_BTN_UP)},
    {.key = MP_ROM_QSTR(MP_QSTR_DOWN), .value = MP_ROM_INT(HW_BTN_DOWN)},
    {.key = MP_ROM_QSTR(MP_QSTR_LEFT), .value = MP_ROM_INT(HW_BTN_LEFT)},
    {.key = MP_ROM_QSTR(MP_QSTR_RIGHT), .value = MP_ROM_INT(HW_BTN_RIGHT)},
    {.key = MP_ROM_QSTR(MP_QSTR_LSTICK), .value = MP_ROM_INT(HW_BTN_LSTICK)},   // stick click
    {.key = MP_ROM_QSTR(MP_QSTR_RSTICK), .value = MP_ROM_INT(HW_BTN_RSTICK)},
};
static MP_DEFINE_CONST_DICT(switch_module_globals, switch_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t switch_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&switch_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_switch, switch_user_cmodule);
