// Python module `font`: smooth TrueType text drawn into the gfx frame (stb_truetype).
// No libnx headers here, only font_hw.h. The GUI uses it through ui.text().
#include <stdio.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "font_hw.h"

static constexpr size_t PATH_MAX_LEN = 256;
static constexpr mp_int_t DEFAULT_SIZE = 16;
static constexpr mp_int_t WHITE = 0xFFFFFFFF;

// font.load(path) -> font id (the same path gives the same id)
static mp_obj_t mod_load(const mp_obj_t path_obj) { // NOLINT(*-misplaced-const)
    const char *py_path = mp_obj_str_get_str(path_obj);
    char path[PATH_MAX_LEN];
    snprintf(path, sizeof(path), py_path[0] == '/' ? "sdmc:%s" : "%s", py_path);
    const int id = font_hw_load(path);
    if (id < 0) mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("font: %s"), font_hw_error());
    return MP_OBJ_NEW_SMALL_INT(id);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_load_obj, mod_load);

static mp_int_t run(const bool draw, const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_font, ARG_x, ARG_y, ARG_text, ARG_color, ARG_size, ARG_advance };
    static const mp_arg_t allowed[] = {
        { .qst = MP_QSTR_font   ,   .flags = MP_ARG_REQUIRED | MP_ARG_INT, .defval = { .u_int = 0            }},
        { .qst = MP_QSTR_x      ,   .flags = MP_ARG_REQUIRED | MP_ARG_INT, .defval = { .u_int = 0            }},
        { .qst = MP_QSTR_y      ,   .flags = MP_ARG_REQUIRED | MP_ARG_INT, .defval = { .u_int = 0            }},
        { .qst = MP_QSTR_text   ,   .flags = MP_ARG_REQUIRED | MP_ARG_OBJ, .defval = { .u_obj = MP_OBJ_NULL  }},
        { .qst = MP_QSTR_color  ,   .flags = MP_ARG_OBJ                  , .defval = { .u_obj = MP_OBJ_NULL  }},
        { .qst = MP_QSTR_size   ,   .flags = MP_ARG_INT                  , .defval = { .u_int = DEFAULT_SIZE }},
        { .qst = MP_QSTR_advance,   .flags = MP_ARG_INT                  , .defval = { .u_int = 0            }},
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);

    size_t len = 0;
    const char *text = mp_obj_str_get_data(args[ARG_text].u_obj, &len);
    const uint32_t color = args[ARG_color].u_obj != MP_OBJ_NULL
        ? (uint32_t)mp_obj_get_int_truncated(args[ARG_color].u_obj) : (uint32_t)WHITE;
    const int w = font_hw_text(
        (int)args[ARG_font].u_int,
        (int)args[ARG_x].u_int,
        (int)args[ARG_y].u_int,
        text,
        len,
        color,
        (int)args[ARG_size].u_int,
        (int)args[ARG_advance].u_int,
        draw
    );
    if (w == -1) mp_raise_ValueError(MP_ERROR_TEXT("font: bad font id"));
    if (w == -2) mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("font: graphics mode is not available"));
    return w;
}

// font.text(font, x, y, text, color=WHITE, size=16, advance=0) -> width in pixels
//   (x, y) is the top-left corner; size is the pixel height of the font;
//   advance > 0 places the characters on a fixed grid (monospace columns)
static mp_obj_t mod_text(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    return mp_obj_new_int(run(true, n_args, pos_args, kw_args));
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_text_obj, 4, mod_text);

// font.width(font, text, size=16, advance=0) -> width of the widest line in pixels
static mp_obj_t mod_width(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_font, ARG_text, ARG_size, ARG_advance };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_font,    MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_text,    MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_size,    MP_ARG_INT, { .u_int = DEFAULT_SIZE } },
        { MP_QSTR_advance, MP_ARG_INT, { .u_int = 0 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);
    size_t len = 0;
    const char *text = mp_obj_str_get_data(args[ARG_text].u_obj, &len);
    const int w = font_hw_text((int)args[ARG_font].u_int, 0, 0, text, len, 0,
                               (int)args[ARG_size].u_int, (int)args[ARG_advance].u_int, false);
    if (w < 0) mp_raise_ValueError(MP_ERROR_TEXT("font: bad font id"));
    return mp_obj_new_int(w);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_width_obj, 2, mod_width);

// font.metrics(font, size=16) -> (ascent, descent, line_height) in pixels
static mp_obj_t mod_metrics(const size_t n_args, const mp_obj_t *args) {
    int ascent = 0, descent = 0, line_h = 0;
    const int size = n_args > 1 ? (int)mp_obj_get_int(args[1]) : (int)DEFAULT_SIZE;
    if (!font_hw_metrics((int)mp_obj_get_int(args[0]), size, &ascent, &descent, &line_h)) {
        mp_raise_ValueError(MP_ERROR_TEXT("font: bad font id"));
    }
    const mp_obj_t items[3] = { mp_obj_new_int(ascent), mp_obj_new_int(descent), mp_obj_new_int(line_h) };
    return mp_obj_new_tuple(3, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_metrics_obj, 1, 2, mod_metrics);

// font.fallback(font, other) - characters missing in font are drawn with other (-1 = none)
static mp_obj_t mod_fallback(const mp_obj_t font_obj, const mp_obj_t other_obj) { // NOLINT(*-misplaced-const)
    if (!font_hw_set_fallback((int)mp_obj_get_int(font_obj), (int)mp_obj_get_int(other_obj))) {
        mp_raise_ValueError(MP_ERROR_TEXT("font: bad font id"));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(mod_fallback_obj, mod_fallback);

static const mp_rom_map_elem_t font_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_font) },
    { MP_ROM_QSTR(MP_QSTR_load),     MP_ROM_PTR(&mod_load_obj) },
    { MP_ROM_QSTR(MP_QSTR_text),     MP_ROM_PTR(&mod_text_obj) },
    { MP_ROM_QSTR(MP_QSTR_width),    MP_ROM_PTR(&mod_width_obj) },
    { MP_ROM_QSTR(MP_QSTR_metrics),  MP_ROM_PTR(&mod_metrics_obj) },
    { MP_ROM_QSTR(MP_QSTR_fallback), MP_ROM_PTR(&mod_fallback_obj) },
};
static MP_DEFINE_CONST_DICT(font_module_globals, font_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t font_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&font_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_font, font_user_cmodule);
