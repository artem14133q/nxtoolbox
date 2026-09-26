// Graphics mode: thin layer between the gfx MicroPython module and libnx (framebuffer).
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>

#define GFX_WIDTH   1280
#define GFX_HEIGHT  720

bool      gfx_hw_begin();                   // switch to graphics mode; false on failure
void      gfx_hw_end();                     // back to the text console (no-op if inactive)
bool      gfx_hw_active();
uint32_t *gfx_hw_buffer(uint32_t *stride_px);   // current frame, RGBA8888; NULL if inactive
void      gfx_hw_present();                 // show the frame (waits for the display)

// Called by gfx_hw_end() once the text console is back (defined in source/main.c)
void      app_gfx_ended();
