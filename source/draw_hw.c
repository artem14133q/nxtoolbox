// Alpha-blended shapes drawn straight into the gfx frame buffer (gfx_hw_buffer).
// No libnx needed: only gfx_hw.h.
#include <math.h>
#include <stddef.h>
#include "draw_hw.h"
#include "gfx_hw.h"

static uint32_t *s_fb = nullptr;
static uint32_t s_stride = 0;

static bool frame() {
    if (!gfx_hw_active() && !gfx_hw_begin()) return false;
    s_fb = gfx_hw_buffer(&s_stride);
    return s_fb != nullptr;
}

// Blends color into *p with opacity a (0..255, the color's own alpha already included)
static inline void blend(uint32_t *p, const uint32_t color, const uint32_t a) {
    if (a == 0) return;
    if (a >= 255) {
        *p = color | 0xFF000000u;
        return;
    }
    const uint32_t d = *p, na = 255 - a;
    const uint32_t r = ((color & 0xFF) * a + (d & 0xFF) * na + 127) / 255;
    const uint32_t g = (((color >> 8) & 0xFF) * a + ((d >> 8) & 0xFF) * na + 127) / 255;
    const uint32_t b = (((color >> 16) & 0xFF) * a + ((d >> 16) & 0xFF) * na + 127) / 255;
    *p = r | (g << 8) | (b << 16) | 0xFF000000u;
}

// Coverage (0..1) of a pixel whose center is at distance d from a circle's center
static inline float coverage(const float d, const float radius) {
    const float c = radius - d + 0.5f;
    return c <= 0.0f ? 0.0f : c >= 1.0f ? 1.0f : c;
}

static void span(const int y, int x0, int x1, const uint32_t color, const uint32_t a) {
    if (a == 0 || y < 0 || y >= GFX_HEIGHT) return;
    if (x0 < 0) x0 = 0;
    if (x1 > GFX_WIDTH) x1 = GFX_WIDTH;
    uint32_t *row = s_fb + (size_t)y * s_stride;
    for (int x = x0; x < x1; x++) blend(&row[x], color, a);
}

bool draw_hw_rect(const int x, const int y, const int w, const int h, int radius,
                  const uint32_t fill, const uint32_t border, int bw) {
    if (w <= 0 || h <= 0) return true;
    if (!frame()) return false;
    const int half = (w < h ? w : h) / 2;
    radius = radius < 0 ? 0 : radius > half ? half : radius;
    bw = bw < 0 ? 0 : bw > half ? half : bw;
    const uint32_t fa = fill >> 24, ba = bw ? border >> 24 : 0;
    const float inner_r = (float)(radius - bw);

    for (int j = 0; j < h; j++) {
        const int py = y + j;
        if (py < 0 || py >= GFX_HEIGHT) continue;
        const bool corner_row = j < radius || j >= h - radius;
        const bool border_row = j < bw || j >= h - bw;
        if (!corner_row) {                         // straight part: border | fill | border
            if (border_row) {
                span(py, x, x + w, border, ba);
            } else {
                span(py, x, x + bw, border, ba);
                span(py, x + bw, x + w - bw, fill, fa);
                span(py, x + w - bw, x + w, border, ba);
            }
            continue;
        }
        // A row through the corners: per-pixel coverage near the corners, spans between them
        const float v = (float)j + 0.5f;
        const float cy = j < radius ? (float)radius : (float)(h - radius);
        uint32_t *row = s_fb + (size_t)py * s_stride;
        for (int i = 0; i < w; i++) {
            const int px = x + i;
            if (px < 0 || px >= GFX_WIDTH) continue;
            const bool corner_col = i < radius || i >= w - radius;
            if (!corner_col) {
                if (border_row) blend(&row[px], border, ba);
                else blend(&row[px], fill, fa);
                continue;
            }
            const float u = (float)i + 0.5f;
            const float cx = i < radius ? (float)radius : (float)(w - radius);
            const float d = sqrtf((u - cx) * (u - cx) + (v - cy) * (v - cy));
            const float outer = coverage(d, (float)radius);
            if (outer <= 0.0f) continue;
            float in = outer;
            if (bw) {
                if (inner_r > 0.0f) {
                    in = coverage(d, inner_r);
                } else {                           // the inner edge is square
                    in = (i >= bw && i < w - bw && j >= bw && j < h - bw) ? outer : 0.0f;
                }
            }
            blend(&row[px], fill, (uint32_t)(fa * in + 0.5f));
            if (bw) blend(&row[px], border, (uint32_t)(ba * (outer - in) + 0.5f));
        }
    }
    return true;
}

bool draw_hw_blit(const int x, const int y, const int w, const int h, const uint8_t *rgba) {
    if (w <= 0 || h <= 0) return true;
    if (!frame()) return false;
    for (int j = 0; j < h; j++) {
        const int py = y + j;
        if (py < 0 || py >= GFX_HEIGHT) continue;
        uint32_t *row = s_fb + (size_t)py * s_stride;
        const uint8_t *src = rgba + (size_t)j * w * 4;
        for (int i = 0; i < w; i++, src += 4) {
            const int px = x + i;
            if (px < 0 || px >= GFX_WIDTH) continue;
            blend(&row[px], src[0] | (src[1] << 8) | ((uint32_t)src[2] << 16), src[3]);
        }
    }
    return true;
}
