// Image decoding: raster formats with stb_image (https://github.com/nothings/stb,
// public domain / MIT), SVG with nanosvg (https://github.com/memononen/nanosvg, zlib).
// Put stb_image.h, nanosvg.h and nanosvgrast.h into source/ next to this file.
// No libnx needed - this file works the same in any build.
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "image_hw.h"

#define STB_IMAGE_IMPLEMENTATION
#define STBI_NO_HDR
#define STBI_NO_LINEAR
#define STBI_NO_PSD
#define STBI_NO_PIC
#define STBI_NO_PNM
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wall"
#pragma GCC diagnostic ignored "-Wextra"
#include "stb_image.h"
#pragma GCC diagnostic pop

// nanosvg only parses+rasterizes (no file format sniffing of its own), so a file stb_image
// does not recognize is tried as SVG next - vector, rendered straight at the target size
// (see svg_load below), never decoded at native size and then thrown away like a raster
// downscale would.
#define NANOSVG_ALL_COLOR_KEYWORDS
#define NANOSVG_IMPLEMENTATION
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wall"
#pragma GCC diagnostic ignored "-Wextra"
#include "nanosvg.h"
#define NANOSVGRAST_IMPLEMENTATION
#include "nanosvgrast.h"
#pragma GCC diagnostic pop

static char s_error[128];

const char *image_hw_error() {
    return s_error;
}

void image_hw_free(uint8_t *pixels) {
    free(pixels);
}

// Box-filter downscale with premultiplied alpha (no dark fringes at transparent edges)
static uint8_t *scale_rgba(const uint8_t *src, const int sw, const int sh, const int dw, const int dh) {
    uint8_t *dst = malloc((size_t)dw * dh * 4);
    if (!dst) return nullptr;
    for (int y = 0; y < dh; y++) {
        const int y0 = y * sh / dh;
        int y1 = (y + 1) * sh / dh;
        if (y1 <= y0) y1 = y0 + 1;
        for (int x = 0; x < dw; x++) {
            const int x0 = x * sw / dw;
            int x1 = (x + 1) * sw / dw;
            if (x1 <= x0) x1 = x0 + 1;
            uint64_t r = 0, g = 0, b = 0, a = 0, n = 0;
            for (int yy = y0; yy < y1; yy++) {
                const uint8_t *p = src + ((size_t)yy * sw + x0) * 4;
                for (int xx = x0; xx < x1; xx++, p += 4) {
                    r += (uint64_t)p[0] * p[3];
                    g += (uint64_t)p[1] * p[3];
                    b += (uint64_t)p[2] * p[3];
                    a += p[3];
                    n++;
                }
            }
            uint8_t *d = dst + ((size_t)y * dw + x) * 4;
            d[0] = a ? (uint8_t)(r / a) : 0;
            d[1] = a ? (uint8_t)(g / a) : 0;
            d[2] = a ? (uint8_t)(b / a) : 0;
            d[3] = (uint8_t)(a / n);
        }
    }
    return dst;
}

static void composite(uint8_t *px, const size_t count, const uint32_t bg) {
    const unsigned br = bg & 0xFF, bgr = (bg >> 8) & 0xFF, bb = (bg >> 16) & 0xFF;
    for (size_t i = 0; i < count; i++, px += 4) {
        const unsigned a = px[3];
        px[0] = (uint8_t)((px[0] * a + br * (255 - a)) / 255);
        px[1] = (uint8_t)((px[1] * a + bgr * (255 - a)) / 255);
        px[2] = (uint8_t)((px[2] * a + bb * (255 - a)) / 255);
        px[3] = 255;
    }
}

// Fits src_w x src_h into max_w x max_h (0 = no limit), scaling down only, never up,
// and always keeping the aspect ratio (both raster and vector paths use this).
static void fit_size(const double src_w, const double src_h, const int max_w, const int max_h,
                     int *out_w, int *out_h) {
    double dw = src_w, dh = src_h;
    if (max_w > 0 && dw > max_w) {
        dh = dh * max_w / dw;
        dw = max_w;
    }
    if (max_h > 0 && dh > max_h) {
        dw = dw * max_h / dh;
        dh = max_h;
    }
    *out_w = dw < 1.0 ? 1 : (int)(dw + 0.5);
    *out_h = dh < 1.0 ? 1 : (int)(dh + 0.5);
}

// Vector path: nanosvg parses the SVG into shapes/paths, then rasterizes straight at the
// target size (dw x dh computed from the SVG's own viewBox/width/height) - unlike a
// raster image there is no wasted work decoding at native size just to downscale after,
// and no blur from resampling: every pixel is anti-aliased fresh for the size asked for.
static uint8_t *svg_load(const char *path, const int max_w, const int max_h, int *out_w, int *out_h) {
    NSVGimage *image = nsvgParseFromFile(path, "px", 96.0f);
    if (!image) return nullptr;
    if (image->width <= 0 || image->height <= 0) {
        nsvgDelete(image);
        return nullptr;
    }

    int dw, dh;
    fit_size(image->width, image->height, max_w, max_h, &dw, &dh);
    const float scale = (float)dw / image->width;

    uint8_t *result = malloc((size_t)dw * dh * 4);
    if (!result) {
        nsvgDelete(image);
        return nullptr;
    }

    NSVGrasterizer *rast = nsvgCreateRasterizer();
    if (!rast) {
        free(result);
        nsvgDelete(image);
        return nullptr;
    }
    nsvgRasterize(rast, image, 0, 0, scale, result, dw, dh, dw * 4);
    nsvgDeleteRasterizer(rast);
    nsvgDelete(image);

    *out_w = dw;
    *out_h = dh;
    return result;
}

uint8_t *image_hw_load(const char *path, const int max_w, const int max_h, const bool has_bg,
                       const uint32_t bg, int *out_w, int *out_h) {
    s_error[0] = '\0';

    FILE *probe = fopen(path, "rb");
    if (!probe) {
        snprintf(s_error, sizeof(s_error), "cannot open the file");
        return nullptr;
    }
    fclose(probe);

    int w = 0, h = 0, channels = 0;
    stbi_uc *pixels = stbi_load(path, &w, &h, &channels, 4);
    if (!pixels) {
        // Not a raster format stb_image recognizes: try it as SVG before giving up.
        int dw, dh;
        uint8_t *svg = svg_load(path, max_w, max_h, &dw, &dh);
        if (!svg) {
            snprintf(s_error, sizeof(s_error), "not a recognized image (PNG/JPEG/BMP/GIF/TGA/SVG)");
            return nullptr;
        }
        if (has_bg) composite(svg, (size_t)dw * dh, bg);
        *out_w = dw;
        *out_h = dh;
        return svg;
    }

    int dw, dh;
    fit_size(w, h, max_w, max_h, &dw, &dh);

    uint8_t *result = pixels;
    if (dw != w || dh != h) {
        result = scale_rgba(pixels, w, h, dw, dh);
        stbi_image_free(pixels);
        if (!result) {
            snprintf(s_error, sizeof(s_error), "out of memory");
            return nullptr;
        }
    }
    if (has_bg) composite(result, (size_t)dw * dh, bg);
    *out_w = dw;
    *out_h = dh;
    return result;
}