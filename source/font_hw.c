// TrueType text with stb_truetype (https://github.com/nothings/stb, public domain / MIT).
// Put stb_truetype.h into source/ next to this file. Draws straight into the gfx frame
// buffer (gfx_hw_buffer) with alpha blending; glyph bitmaps are cached.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "font_hw.h"
#include "gfx_hw.h"

#define STB_TRUETYPE_IMPLEMENTATION
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wall"
#pragma GCC diagnostic ignored "-Wextra"
#include "stb_truetype.h"
#pragma GCC diagnostic pop

static constexpr int MAX_FONTS = 8;
static constexpr int CACHE_SIZE = 2048;          // glyph bitmaps kept (hash table slots)
static constexpr int MAX_SIZE = 256;             // largest font size in pixels
static constexpr float GAMMA = 0.8f;             // < 1 makes thin strokes a little fuller

typedef struct {
    char           path[256];
    unsigned char *data;                         // the whole file (stb reads from it)
    stbtt_fontinfo info;
    int            ascent, descent, line_gap;    // font units
    int            fallback;                     // font for missing characters, -1 = none
} Font;

typedef struct {
    bool     used;
    int      font, size, cp;
    int      index;                              // glyph index in the font
    int      w, h, x_off, y_off;
    float    advance;                            // pixels
    uint8_t *bitmap;                             // w*h coverage values, nullptr for empty glyphs
} Glyph;

static Font    s_fonts[MAX_FONTS];
static int     s_font_count = 0;
static Glyph   s_cache[CACHE_SIZE];
static uint8_t s_gamma[256];
static bool    s_gamma_ready = false;
static char    s_error[160];

const char *font_hw_error() {
    return s_error;
}

// ---------- loading ----------

int font_hw_load(const char *path) {
    s_error[0] = '\0';
    for (int i = 0; i < s_font_count; i++) {
        if (strcmp(s_fonts[i].path, path) == 0) return i;
    }

    if (s_font_count >= MAX_FONTS) {
        snprintf(s_error, sizeof(s_error), "too many fonts (max %d)", MAX_FONTS);
        return -1;
    }

    FILE *f = fopen(path, "rb");
    if (!f) {
        snprintf(s_error, sizeof(s_error), "cannot open %s", path);
        return -1;
    }
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *data = size > 0 ? malloc((size_t)size) : nullptr;
    const bool ok = data && fread(data, 1, (size_t)size, f) == (size_t)size;
    fclose(f);
    if (!ok) {
        free(data);
        snprintf(s_error, sizeof(s_error), "cannot read %s", path);
        return -1;
    }
    Font *font = &s_fonts[s_font_count];
    const int offset = stbtt_GetFontOffsetForIndex(data, 0);
    if (offset < 0 || !stbtt_InitFont(&font->info, data, offset)) {
        free(data);
        snprintf(s_error, sizeof(s_error), "not a TrueType font: %s", path);
        return -1;
    }
    font->data = data;
    font->fallback = -1;
    snprintf(font->path, sizeof(font->path), "%s", path);
    stbtt_GetFontVMetrics(&font->info, &font->ascent, &font->descent, &font->line_gap);
    return s_font_count++;
}

static Font *get_font(const int id) {
    return id >= 0 && id < s_font_count ? &s_fonts[id] : nullptr;
}

static float scale_for(const Font *f, const int size) {
    return stbtt_ScaleForPixelHeight(&f->info, (float)size);
}

bool font_hw_set_fallback(const int id, const int fallback) {
    Font *f = id >= 0 && id < s_font_count ? &s_fonts[id] : nullptr;
    if (!f || fallback >= s_font_count || fallback == id) return false;
    f->fallback = fallback < 0 ? -1 : fallback;
    return true;
}

bool font_hw_metrics(const int id, const int size, int *ascent, int *descent, int *line_height) {
    const Font *f = get_font(id);
    if (!f) return false;
    const float s = scale_for(f, size);
    *ascent = (int)lroundf((float)f->ascent * s);
    *descent = (int)lroundf(-(float)f->descent * s);
    *line_height = (int)lroundf((float)(f->ascent - f->descent + f->line_gap) * s);
    return true;
}

// ---------- glyph cache ----------

static Glyph *get_glyph(const int id, const int size, const int cp) {
    const uint32_t hash = (uint32_t)cp * 2654435761u ^ (uint32_t)size * 40503u ^ (uint32_t)id * 7919u;
    Glyph *g = &s_cache[hash % CACHE_SIZE];
    if (g->used && g->font == id && g->size == size && g->cp == cp) return g;

    free(g->bitmap);                             // replace whatever was in this slot
    *g = (Glyph){};
    const Font *f = &s_fonts[id];
    const float s = scale_for(f, size);
    g->index = stbtt_FindGlyphIndex(&f->info, cp);
    int adv = 0, lsb = 0;
    stbtt_GetGlyphHMetrics(&f->info, g->index, &adv, &lsb);
    g->advance = (float)adv * s;
    if (!stbtt_IsGlyphEmpty(&f->info, g->index)) {
        g->bitmap = stbtt_GetGlyphBitmap(&f->info, s, s, g->index, &g->w, &g->h, &g->x_off, &g->y_off);
    }
    g->font = id;
    g->size = size;
    g->cp = cp;
    g->used = true;
    return g;
}

// ---------- drawing ----------

static void init_gamma() {
    for (int i = 0; i < 256; i++) {
        s_gamma[i] = (uint8_t)lroundf(powf((float)i / 255.0f, GAMMA) * 255.0f);
    }
    s_gamma_ready = true;
}

static void blend_glyph(
    uint32_t *fb, const uint32_t stride, const int gx, const int gy,
    const Glyph *g, const uint32_t color
) {
    const uint32_t cr = color & 0xFF, cg = (color >> 8) & 0xFF, cb = (color >> 16) & 0xFF;
    const uint32_t ca = color >> 24;
    for (int row = 0; row < g->h; row++) {
        const int y = gy + row;
        if (y < 0 || y >= GFX_HEIGHT) continue;
        const uint8_t *src = g->bitmap + row * g->w;
        uint32_t *dst = fb + (size_t)y * stride;
        for (int col = 0; col < g->w; col++) {
            const int x = gx + col;
            if (x < 0 || x >= GFX_WIDTH || !src[col]) continue;
            const uint32_t a = s_gamma[src[col]] * ca / 255;
            if (!a) continue;
            const uint32_t d = dst[x], na = 255 - a;
            const uint32_t r = (cr * a + (d & 0xFF) * na) / 255;
            const uint32_t gg = (cg * a + ((d >> 8) & 0xFF) * na) / 255;
            const uint32_t b = (cb * a + ((d >> 16) & 0xFF) * na) / 255;
            dst[x] = r | (gg << 8) | (b << 16) | 0xFF000000u;
        }
    }
}

// Next code point of UTF-8 text; invalid bytes are returned as they are (Latin-1)
static int next_cp(const unsigned char **p, const unsigned char *end) {
    const unsigned char *s = *p;
    const int c = *s;
    int n = c < 0x80 ? 0 : c < 0xE0 ? 1 : c < 0xF0 ? 2 : 3;
    if (c >= 0x80 && c < 0xC0) n = 0;            // stray continuation byte
    if (s + n >= end) n = (int)(end - s) - 1;
    int cp = n == 0 ? c : n == 1 ? c & 0x1F : n == 2 ? c & 0x0F : c & 0x07;
    for (int i = 1; i <= n; i++) {
        if ((s[i] & 0xC0) != 0x80) {             // broken sequence: take the lead byte only
            *p = s + 1;
            return c;
        }
        cp = (cp << 6) | (s[i] & 0x3F);
    }
    *p = s + n + 1;
    return cp;
}

int font_hw_text(
    const int id, const int x, const int y, const char *text, const size_t len,
    const uint32_t color, int size, const int advance, const bool draw
) {
    const Font *f = get_font(id);
    if (!f) return -1;
    if (size < 1) size = 1;
    if (size > MAX_SIZE) size = MAX_SIZE;
    const float s = scale_for(f, size);
    const int ascent = (int)lroundf((float)f->ascent * s);
    const int line_h = (int)lroundf((float)(f->ascent - f->descent + f->line_gap) * s);

    uint32_t *fb = nullptr;
    uint32_t stride = 0;
    if (draw) {
        if (!gfx_hw_active() && !gfx_hw_begin()) return -2;
        fb = gfx_hw_buffer(&stride);
        if (!fb) return -2;
        if (!s_gamma_ready) init_gamma();
    }

    const unsigned char *p = (const unsigned char *)text, *end = p + len;
    float pen = (float)x;
    int baseline = y + ascent;
    float widest = 0;
    int prev = 0;
    while (p < end) {
        const int cp = next_cp(&p, end);
        if (cp == '\n') {
            if (pen - (float)x > widest) widest = pen - (float)x;
            pen = (float)x;
            baseline += line_h;
            prev = 0;
            continue;
        }
        const Glyph *g = get_glyph(id, size, cp);
        bool fell_back = false;
        if (g->index == 0 && f->fallback >= 0) {     // not in this font: try the fallback font
            const Glyph *alt = get_glyph(f->fallback, size, cp);
            if (alt->index != 0) {
                g = alt;
                fell_back = true;
            }
        }
        int gx;
        if (advance > 0) {                       // monospace grid: center the glyph in its cell
            gx = (int)pen + (advance - (int)lroundf(g->advance)) / 2 + g->x_off;
        } else {
            if (prev && !fell_back) pen += (float)stbtt_GetGlyphKernAdvance(&f->info, prev, g->index) * s;
            gx = (int)lroundf(pen) + g->x_off;
        }
        if (draw && g->bitmap) blend_glyph(fb, stride, gx, baseline + g->y_off, g, color);
        pen += advance > 0 ? (float)advance : g->advance;
        prev = fell_back ? 0 : g->index;
    }
    if (pen - (float)x > widest) widest = pen - (float)x;
    return (int)ceilf(widest);
}
