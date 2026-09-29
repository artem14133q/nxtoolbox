// Python module `draw`: alpha-blended rounded rectangles, circles and images drawn into
// the gfx frame. No libnx headers here, only draw_hw.h. The GUI uses it through ui.box().
#include "py/runtime.h"
#include "py/obj.h"
#include "draw_hw.h"

static constexpr mp_int_t NONE = 0;              // a transparent color: nothing is drawn

[[noreturn]] static void no_graphics() {
    mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("draw: graphics mode is not available"));
}

static uint32_t color_arg(const mp_obj_t obj) {
    return obj == mp_const_none ? (uint32_t)NONE : (uint32_t)mp_obj_get_int_truncated(obj);
}

// draw.rect(x, y, w, h, color, radius=0, border=None, border_width=0)
static mp_obj_t mod_rect(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_x, ARG_y, ARG_w, ARG_h, ARG_color, ARG_radius, ARG_border, ARG_border_width };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_x,            MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_y,            MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_w,            MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_h,            MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_color,        MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_radius,       MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_border,       MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_border_width, MP_ARG_INT, { .u_int = 0 } },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, a);
    const uint32_t border = color_arg(a[ARG_border].u_obj);
    if (!draw_hw_rect((int)a[ARG_x].u_int, (int)a[ARG_y].u_int, (int)a[ARG_w].u_int, (int)a[ARG_h].u_int,
                      (int)a[ARG_radius].u_int, color_arg(a[ARG_color].u_obj), border,
                      border ? (int)a[ARG_border_width].u_int : 0)) {
        no_graphics();
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_rect_obj, 5, mod_rect);

// draw.circle(cx, cy, r, color, border=None, border_width=0)
static mp_obj_t mod_circle(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_cx, ARG_cy, ARG_r, ARG_color, ARG_border, ARG_border_width };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_cx,           MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_cy,           MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_r,            MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_color,        MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_border,       MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_border_width, MP_ARG_INT, { .u_int = 0 } },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, a);
    const int r = (int)a[ARG_r].u_int;
    const uint32_t border = color_arg(a[ARG_border].u_obj);
    if (!draw_hw_rect((int)a[ARG_cx].u_int - r, (int)a[ARG_cy].u_int - r, 2 * r, 2 * r, r,
                      color_arg(a[ARG_color].u_obj), border, border ? (int)a[ARG_border_width].u_int : 0)) {
        no_graphics();
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_circle_obj, 4, mod_circle);

// draw.blit(x, y, w, h, rgba) - like gfx.blit, but blended by the alpha channel
static mp_obj_t mod_blit(const size_t n_args, const mp_obj_t *args) {
    const mp_int_t w = mp_obj_get_int(args[2]), h = mp_obj_get_int(args[3]);
    mp_buffer_info_t buf;
    mp_get_buffer_raise(args[4], &buf, MP_BUFFER_READ);
    if (w < 0 || h < 0 || buf.len < (size_t)(w * h * 4)) {
        mp_raise_ValueError(MP_ERROR_TEXT("draw: image data is too short"));
    }
    if (!draw_hw_blit((int)mp_obj_get_int(args[0]), (int)mp_obj_get_int(args[1]), (int)w, (int)h,
                      (const uint8_t *)buf.buf)) {
        no_graphics();
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_blit_obj, 5, 5, mod_blit);

static const mp_rom_map_elem_t draw_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_draw) },
    { MP_ROM_QSTR(MP_QSTR_rect),     MP_ROM_PTR(&mod_rect_obj) },
    { MP_ROM_QSTR(MP_QSTR_circle),   MP_ROM_PTR(&mod_circle_obj) },
    { MP_ROM_QSTR(MP_QSTR_blit),     MP_ROM_PTR(&mod_blit_obj) },
};
static MP_DEFINE_CONST_DICT(draw_module_globals, draw_module_globals_table);

const mp_obj_module_t draw_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&draw_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_draw, draw_user_cmodule);
