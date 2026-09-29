// Python module `image`: decodes PNG/JPEG/BMP/GIF/TGA files for gfx.blit().
// No libnx headers here, only image_hw.h.
#include <stdio.h>
#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "image_hw.h"

static constexpr size_t PATH_MAX_LEN = 1024;

// image.load(path, max_w=0, max_h=0, bg=None) -> (w, h, rgba: bytes)
//   max_w/max_h: scale down to fit (keeping the aspect ratio), 0 = no limit
//   bg: a gfx color; transparent pixels are blended onto it (the result is opaque)
static mp_obj_t mod_load(const size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_path, ARG_max_w, ARG_max_h, ARG_bg };
    static const mp_arg_t allowed[] = {
        { .qst = MP_QSTR_path,  .flags = MP_ARG_REQUIRED | MP_ARG_OBJ, .defval = { .u_obj = MP_OBJ_NULL }},
        { .qst = MP_QSTR_max_w, .flags = MP_ARG_INT, .defval = { .u_int = 0 }},
        { .qst = MP_QSTR_max_h, .flags = MP_ARG_INT, .defval = { .u_int = 0 }},
        { .qst = MP_QSTR_bg,    .flags = MP_ARG_OBJ, .defval = { .u_obj = mp_const_none }},
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);

    // "/switch/..." (as Python sees it) -> "sdmc:/switch/..."
    const char *py_path = mp_obj_str_get_str(args[ARG_path].u_obj);
    char path[PATH_MAX_LEN];
    snprintf(path, sizeof(path), py_path[0] == '/' ? "sdmc:%s" : "%s", py_path);

    const bool has_bg = args[ARG_bg].u_obj != mp_const_none;
    const uint32_t bg = has_bg ? (uint32_t)mp_obj_get_int_truncated(args[ARG_bg].u_obj) : 0;

    int w = 0, h = 0;
    uint8_t *pixels = image_hw_load(path, (int)args[ARG_max_w].u_int, (int)args[ARG_max_h].u_int,
                                    has_bg, bg, &w, &h);
    if (!pixels) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("image: %s: %s"), py_path, image_hw_error());
    }
    const auto data = mp_obj_new_bytes(pixels, (size_t)w * h * 4);
    image_hw_free(pixels);
    const mp_obj_t items[3] = { MP_OBJ_NEW_SMALL_INT(w), MP_OBJ_NEW_SMALL_INT(h), data };
    return mp_obj_new_tuple(3, items);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_load_obj, 1, mod_load);

static const mp_rom_map_elem_t image_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_image) },
    { MP_ROM_QSTR(MP_QSTR_load),     MP_ROM_PTR(&mod_load_obj) },
};
static MP_DEFINE_CONST_DICT(image_module_globals, image_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t image_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&image_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_image, image_user_cmodule);