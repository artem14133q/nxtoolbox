// Image decoding (stb_image): thin layer between the image MicroPython module and stb.
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>
#include <stdbool.h>

// Loads an image file (PNG, JPEG, BMP, GIF - first frame, TGA) as RGBA.
// max_w/max_h > 0: scaled down (never up) to fit, keeping the aspect ratio.
// has_bg: composited onto the opaque color bg (0xAABBGGRR, like gfx colors).
// Returns an malloc'ed buffer (release with image_hw_free) or nullptr on error.
uint8_t    *image_hw_load(const char *path, int max_w, int max_h, bool has_bg, uint32_t bg,
                          int *out_w, int *out_h);
void        image_hw_free(uint8_t *pixels);
const char *image_hw_error();