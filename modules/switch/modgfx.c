// Python module `gfx`: 1280x720 graphics for scripts.
// No libnx headers here, only gfx_hw.h. All drawing happens in plain C on the frame buffer.
#include <string.h>
#include <math.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "gfx_hw.h"
#include "gfx_font.h"

#define W GFX_WIDTH
#define H GFX_HEIGHT

#define RGBA(r, g, b, a) ((uint32_t)(r) | ((uint32_t)(g) << 8) | ((uint32_t)(b) << 16) | ((uint32_t)(a) << 24))
#define COLOR_BLACK RGBA(0, 0, 0, 255)
#define COLOR_WHITE RGBA(255, 255, 255, 255)

static uint32_t *s_buf;
static uint32_t  s_stride;

// Enters graphics mode on first use and fetches the current frame buffer
static void ensure() {
    if (!gfx_hw_active() && !gfx_hw_begin()) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("gfx: cannot switch to graphics mode"));
    }
    s_buf = gfx_hw_buffer(&s_stride);
}

static uint32_t get_color(mp_obj_t o) {
    return (uint32_t)mp_obj_get_int_truncated(o);
}

static int clampi(const mp_int_t v, const int lo, const int hi) {
    return v < lo ? lo : v > hi ? hi : (int)v;
}

// ---------- primitives (clipped to the screen) ----------

static void put(const int x, const int y, const uint32_t c) {
    if ((unsigned)x < W && (unsigned)y < H) s_buf[(uint32_t)y * s_stride + (uint32_t)x] = c;
}

static void fill(const mp_int_t x, const mp_int_t y, const mp_int_t w, const mp_int_t h, const uint32_t c) {
    if (w <= 0 || h <= 0) return;
    const int x0 = clampi(x, 0, W);
    const int x1 = clampi(x + w, 0, W);
    const int y0 = clampi(y, 0, H);
    const int y1 = clampi(y + h, 0, H);
    for (int yy = y0; yy < y1; yy++) {
        uint32_t *row = s_buf + (uint32_t)yy * s_stride;
        for (int xx = x0; xx < x1; xx++) row[xx] = c;
    }
}

static void hline(mp_int_t x0, mp_int_t x1, mp_int_t y, uint32_t c) {
    if (x1 < x0) { const mp_int_t t = x0; x0 = x1; x1 = t; }
    fill(x0, y, x1 - x0 + 1, 1, c);
}

static void line(mp_int_t x0, mp_int_t y0, mp_int_t x1, mp_int_t y1, uint32_t c) {
    // Bresenham; very long off-screen lines are clamped first to stay fast
    x0 = clampi(x0, -4 * W, 5 * W); x1 = clampi(x1, -4 * W, 5 * W);
    y0 = clampi(y0, -4 * H, 5 * H); y1 = clampi(y1, -4 * H, 5 * H);
    const mp_int_t dx = x1 > x0 ? x1 - x0 : x0 - x1;
    const mp_int_t dy = y1 > y0 ? y0 - y1 : y1 - y0;
    const int sx = x0 < x1 ? 1 : -1;
    const int sy = y0 < y1 ? 1 : -1;
    mp_int_t err = dx + dy;
    for (;;) {
        put((int)x0, (int)y0, c);
        if (x0 == x1 && y0 == y1) break;
        const mp_int_t e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

static void circle(mp_int_t cx, mp_int_t cy, mp_int_t r, const uint32_t c, const bool filled) {
    if (r < 0) return;
    if (r > 4 * W) r = 4 * W;
    cx = clampi(cx, -8 * W, 9 * W);
    cy = clampi(cy, -8 * H, 9 * H);
    if (filled) {
        for (mp_int_t dy = -r; dy <= r; dy++) {
            const mp_int_t dx = (mp_int_t)sqrt((double)(r * r - dy * dy));
            hline(cx - dx, cx + dx, cy + dy, c);
        }
        return;
    }
    // Midpoint circle
    mp_int_t x = r, y = 0, err = 1 - r;
    while (x >= y) {
        put(cx + x, cy + y, c); put(cx + y, cy + x, c); // NOLINT(*-narrowing-conversions)
        put(cx - y, cy + x, c); put(cx - x, cy + y, c); // NOLINT(*-narrowing-conversions)
        put(cx - x, cy - y, c); put(cx - y, cy - x, c); // NOLINT(*-narrowing-conversions)
        put(cx + y, cy - x, c); put(cx + x, cy - y, c); // NOLINT(*-narrowing-conversions)
        y++;
        if (err < 0) {
            err += 2 * y + 1;
        } else {
            x--;
            err += 2 * (y - x) + 1;
        }
    }
}

// ---------- text ----------

static uint32_t utf8_next(const uint8_t **p, const uint8_t *end) {
    const uint8_t *s = *p;
    uint32_t c = *s++;
    int extra = 0;
    if (c >= 0xF0)      { c &= 0x07; extra = 3; }
    else if (c >= 0xE0) { c &= 0x0F; extra = 2; }
    else if (c >= 0xC0) { c &= 0x1F; extra = 1; }
    while (extra-- > 0 && s < end && (*s & 0xC0) == 0x80) c = (c << 6) | (*s++ & 0x3F);
    *p = s;
    return c;
}

static const uint8_t *glyph_for(uint32_t cp) {
    int lo = 0, hi = GFX_FONT_COUNT - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (gfx_font_codes[mid] == cp) return gfx_font_bitmaps[mid];
        if (gfx_font_codes[mid] < cp) lo = mid + 1; else hi = mid - 1;
    }
    return cp == '?' ? nullptr : glyph_for('?');   // unknown characters are shown as '?'
}

static void draw_glyph(mp_int_t x, mp_int_t y, const uint8_t *g, uint32_t c, int scale) {
    if (!g) return;
    for (int row = 0; row < GFX_FONT_H; row++) {
        uint8_t bits = g[row];
        for (int col = 0; bits && col < GFX_FONT_W; col++, bits <<= 1) {
            if (!(bits & 0x80)) continue;
            if (scale == 1) put((int)(x + col), (int)(y + row), c);
            else fill(x + col * scale, y + row * scale, scale, scale, c);
        }
    }
}

// Draws (if draw is true) or measures text; returns the width of the widest line
static mp_int_t text_run(const mp_int_t x, mp_int_t y, const char *str, const size_t len,
                         const uint32_t c, const int scale, const bool draw) {
    const uint8_t *p = (const uint8_t *)str, *end = p + len;
    mp_int_t cx = x, widest = 0;
    while (p < end) {
        uint32_t cp = utf8_next(&p, end);
        if (cp == '\n') {
            if (cx - x > widest) widest = cx - x;
            cx = x;
            y += GFX_FONT_H * scale;
            continue;
        }
        if (cp == '\r') continue;
        if (cp == '\t') cp = ' ';
        if (draw) draw_glyph(cx, y, glyph_for(cp), c, scale);
        cx += GFX_FONT_W * scale;
    }
    if (cx - x > widest) widest = cx - x;
    return widest;
}

static int get_scale(const size_t n_args, const mp_obj_t *args, const size_t index) {
    const mp_int_t scale = n_args > index ? mp_obj_get_int(args[index]) : 1;
    return clampi(scale, 1, 32);
}

// ---------- Python functions ----------

// gfx.begin() - switch to graphics mode (drawing functions also do it automatically)
static mp_obj_t mod_begin() {
    ensure();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_begin_obj, mod_begin);

// gfx.end() - back to the text console (also happens automatically when the script ends)
static mp_obj_t mod_end() {
    gfx_hw_end();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_end_obj, mod_end);

// gfx.present() - show what has been drawn; waits for the display (~60 fps)
static mp_obj_t mod_present() {
    ensure();
    gfx_hw_present();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_present_obj, mod_present);

// gfx.rgb(r, g, b, a=255) -> color
static mp_obj_t mod_rgb(const size_t n_args, const mp_obj_t *args) {
    const int r = clampi(mp_obj_get_int(args[0]), 0, 255);
    const int g = clampi(mp_obj_get_int(args[1]), 0, 255);
    const int b = clampi(mp_obj_get_int(args[2]), 0, 255);
    const int a = n_args > 3 ? clampi(mp_obj_get_int(args[3]), 0, 255) : 255;
    return mp_obj_new_int_from_uint(RGBA(r, g, b, a));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_rgb_obj, 3, 4, mod_rgb);

// gfx.clear(color=BLACK)
static mp_obj_t mod_clear(size_t n_args, const mp_obj_t *args) {
    ensure();
    fill(0, 0, W, H, n_args > 0 ? get_color(args[0]) : COLOR_BLACK);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_clear_obj, 0, 1, mod_clear);

// gfx.pixel(x, y, color)
static mp_obj_t mod_pixel(mp_obj_t x, mp_obj_t y, mp_obj_t c) {
    ensure();
    mp_int_t px = mp_obj_get_int(x), py = mp_obj_get_int(y);
    if (px >= 0 && px < W && py >= 0 && py < H) put((int)px, (int)py, get_color(c));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(mod_pixel_obj, mod_pixel);

// gfx.line(x0, y0, x1, y1, color)
static mp_obj_t mod_line(size_t n_args, const mp_obj_t *args) {
    ensure();
    line(mp_obj_get_int(args[0]), mp_obj_get_int(args[1]),
         mp_obj_get_int(args[2]), mp_obj_get_int(args[3]), get_color(args[4]));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_line_obj, 5, 5, mod_line);

// gfx.rect(x, y, w, h, color) - outline
static mp_obj_t mod_rect(size_t n_args, const mp_obj_t *args) {
    ensure();
    const mp_int_t x = mp_obj_get_int(args[0]);
    const mp_int_t y = mp_obj_get_int(args[1]);
    const mp_int_t w = mp_obj_get_int(args[2]);
    const mp_int_t h = mp_obj_get_int(args[3]);
    const uint32_t c = get_color(args[4]);
    if (w > 0 && h > 0) {
        fill(x, y, w, 1, c);
        fill(x, y + h - 1, w, 1, c);
        fill(x, y, 1, h, c);
        fill(x + w - 1, y, 1, h, c);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_rect_obj, 5, 5, mod_rect);

// gfx.fill_rect(x, y, w, h, color)
static mp_obj_t mod_fill_rect(size_t n_args, const mp_obj_t *args) {
    ensure();
    fill(mp_obj_get_int(args[0]), mp_obj_get_int(args[1]),
         mp_obj_get_int(args[2]), mp_obj_get_int(args[3]), get_color(args[4]));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_fill_rect_obj, 5, 5, mod_fill_rect);

// gfx.circle(x, y, r, color) - outline
static mp_obj_t mod_circle(size_t n_args, const mp_obj_t *args) {
    ensure();
    circle(mp_obj_get_int(args[0]), mp_obj_get_int(args[1]), mp_obj_get_int(args[2]),
           get_color(args[3]), false);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_circle_obj, 4, 4, mod_circle);

// gfx.fill_circle(x, y, r, color)
static mp_obj_t mod_fill_circle(size_t n_args, const mp_obj_t *args) {
    ensure();
    circle(mp_obj_get_int(args[0]), mp_obj_get_int(args[1]), mp_obj_get_int(args[2]),
           get_color(args[3]), true);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_fill_circle_obj, 4, 4, mod_fill_circle);

// gfx.text(x, y, text, color=WHITE, scale=1) -> width in pixels
// Characters are 8x16 pixels (times scale); '\n' starts a new line.
static mp_obj_t mod_text(const size_t n_args, const mp_obj_t *args) {
    ensure();
    size_t len;
    const char *s = mp_obj_str_get_data(args[2], &len);
    const uint32_t c = n_args > 3 ? get_color(args[3]) : COLOR_WHITE;
    const mp_int_t w = text_run(clampi(mp_obj_get_int(args[0]), -100000, 100000),
                          clampi(mp_obj_get_int(args[1]), -100000, 100000), s, len, c,
                          get_scale(n_args, args, 4), true);
    return mp_obj_new_int(w);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_text_obj, 3, 5, mod_text);

// gfx.text_width(text, scale=1) -> width in pixels (widest line)
static mp_obj_t mod_text_width(const size_t n_args, const mp_obj_t *args) {
    size_t len;
    const char *s = mp_obj_str_get_data(args[0], &len);
    return mp_obj_new_int(text_run(0, 0, s, len, 0, get_scale(n_args, args, 1), false));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_text_width_obj, 1, 2, mod_text_width);

// gfx.blit(x, y, w, h, data) - draw an image: w*h pixels, 4 bytes each (R, G, B, A).
// Pixels with A == 0 are transparent, others are copied as is.
static mp_obj_t mod_blit(size_t n_args, const mp_obj_t *args) {
    ensure();
    const mp_int_t x = mp_obj_get_int(args[0]);
    const mp_int_t y = mp_obj_get_int(args[1]);
    const mp_int_t w = mp_obj_get_int(args[2]);
    const mp_int_t h = mp_obj_get_int(args[3]);
    mp_buffer_info_t bi;
    mp_get_buffer_raise(args[4], &bi, MP_BUFFER_READ);
    if (w <= 0 || h <= 0) return mp_const_none;
    if (bi.len < (mp_uint_t)(w * h * 4)) {
        mp_raise_ValueError(MP_ERROR_TEXT("gfx.blit: data must contain w*h*4 bytes (RGBA)"));
    }
    const uint8_t *src = bi.buf;
    for (mp_int_t row = 0; row < h; row++) {
        const mp_int_t yy = y + row;
        if (yy < 0 || yy >= H) continue;
        uint32_t *dst = s_buf + (uint32_t)yy * s_stride;
        const uint8_t *s = src + (size_t)row * (size_t)w * 4;
        for (mp_int_t col = 0; col < w; col++, s += 4) {
            const mp_int_t xx = x + col;
            if (xx < 0 || xx >= W || s[3] == 0) continue;
            dst[xx] = RGBA(s[0], s[1], s[2], s[3]);
        }
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_blit_obj, 5, 5, mod_blit);

// ---------- module table ----------

#define COLOR_CONST(name, r, g, b) { MP_ROM_QSTR(MP_QSTR_##name), MP_ROM_INT(RGBA(r, g, b, 255)) }

static const mp_rom_map_elem_t gfx_module_globals_table[] = {
    {.key = MP_ROM_QSTR(MP_QSTR___name__), .value = MP_ROM_QSTR(MP_QSTR_gfx)},
    {.key = MP_ROM_QSTR(MP_QSTR_begin), .value = MP_ROM_PTR(&mod_begin_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_end), .value = MP_ROM_PTR(&mod_end_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_present), .value = MP_ROM_PTR(&mod_present_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_rgb), .value = MP_ROM_PTR(&mod_rgb_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_clear), .value = MP_ROM_PTR(&mod_clear_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_pixel), .value = MP_ROM_PTR(&mod_pixel_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_line), .value = MP_ROM_PTR(&mod_line_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_rect), .value = MP_ROM_PTR(&mod_rect_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_fill_rect), .value = MP_ROM_PTR(&mod_fill_rect_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_circle), .value = MP_ROM_PTR(&mod_circle_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_fill_circle), .value = MP_ROM_PTR(&mod_fill_circle_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_text), .value = MP_ROM_PTR(&mod_text_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_text_width), .value = MP_ROM_PTR(&mod_text_width_obj)},
    {.key = MP_ROM_QSTR(MP_QSTR_blit), .value = MP_ROM_PTR(&mod_blit_obj)},

    {.key = MP_ROM_QSTR(MP_QSTR_WIDTH), .value = MP_ROM_INT(W)},
    {.key = MP_ROM_QSTR(MP_QSTR_HEIGHT), .value = MP_ROM_INT(H)},
    {.key = MP_ROM_QSTR(MP_QSTR_FONT_WIDTH), .value = MP_ROM_INT(GFX_FONT_W)},
    {.key = MP_ROM_QSTR(MP_QSTR_FONT_HEIGHT), .value = MP_ROM_INT(GFX_FONT_H)},

    COLOR_CONST(BLACK,     0,   0,   0),
    COLOR_CONST(WHITE,   255, 255, 255),
    COLOR_CONST(GRAY,    128, 128, 128),
    COLOR_CONST(RED,     230,  40,  40),
    COLOR_CONST(GREEN,    40, 200,  60),
    COLOR_CONST(BLUE,     40,  90, 230),
    COLOR_CONST(YELLOW,  250, 220,  40),
    COLOR_CONST(ORANGE,  250, 140,  20),
    COLOR_CONST(CYAN,     40, 210, 230),
    COLOR_CONST(MAGENTA, 220,  50, 220),
};
static MP_DEFINE_CONST_DICT(gfx_module_globals, gfx_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t gfx_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&gfx_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_gfx, gfx_user_cmodule);
