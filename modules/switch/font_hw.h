// TrueType text (stb_truetype): thin layer between the font MicroPython module and stb.
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

// Loads a .ttf file (C path, e.g. "sdmc:/switch/NXToolBox/sys/fonts/Inter-Regular.ttf").
// Loading the same path again returns the same id. Returns the font id, or -1 (see font_hw_error).
int font_hw_load(const char *path);

// Draws (draw = true) or measures UTF-8 text. (x, y) is the top-left corner of the first line;
// size is the pixel height of the font (ascent - descent). advance > 0 puts the glyphs on a
// fixed grid of that many pixels (monospace columns). color is a gfx color (0xAABBGGRR).
// Returns the width of the widest line in pixels, or -1 for a bad font id, -2 if graphics
// mode cannot be started.
int font_hw_text(int id, int x, int y, const char *text, size_t len, uint32_t color,
                 int size, int advance, bool draw);

// Characters missing in font id are taken from font fallback (-1 = none). false for bad ids.
bool font_hw_set_fallback(int id, int fallback);

// Vertical metrics in pixels for a size: ascent (above the baseline), descent (below, >= 0)
// and the recommended distance between lines. false for a bad font id.
bool font_hw_metrics(int id, int size, int *ascent, int *descent, int *line_height);

const char *font_hw_error();
