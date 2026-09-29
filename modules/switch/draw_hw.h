// Alpha-blended shapes: thin layer between the draw MicroPython module and the gfx frame.
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>
#include <stdbool.h>

// A rectangle with rounded, antialiased corners and an optional border, blended into the
// frame. Colors are gfx colors (0xAABBGGRR): alpha 255 is opaque, 0 invisible. The border
// (bw pixels wide, drawn inside the rectangle) follows the rounding. Returns false if
// graphics mode is not available.
bool draw_hw_rect(int x, int y, int w, int h, int radius, uint32_t fill, uint32_t border, int bw);

// An RGBA image (w*h*4 bytes, R G B A) blended into the frame by its alpha channel.
bool draw_hw_blit(int x, int y, int w, int h, const uint8_t *rgba);
