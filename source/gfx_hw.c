// Graphics mode on top of the libnx framebuffer. Compiled only with devkitA64 (lives in source/).
//
// The text console and the framebuffer cannot own the screen at the same time,
// so entering graphics mode shuts the console down and leaving it re-creates it.
//
// Switching right after a frame was presented can fail: the system compositor may
// still be holding the window buffers. So we wait briefly after the last frame and
// retry creating the new owner of the screen a few times before giving up.
#include <switch.h>
#include "gfx_hw.h"

#define SWITCH_RETRIES   20
#define SWITCH_DELAY_NS  (50 * 1000000LL)   // 50 ms, ~3 frames

static Framebuffer s_fb;
static bool        s_active = false;
static uint32_t   *s_buf = nullptr;
static uint32_t    s_stride_px = 0;

static void begin_frame() {
    u32 stride = 0;
    s_buf = (uint32_t *)framebufferBegin(&s_fb, &stride);
    s_stride_px = stride / sizeof(uint32_t);
}

// Re-creates the text console; returns false if the screen could not be taken back
static bool console_restore() {
    for (int i = 0; i < SWITCH_RETRIES; i++) {
        if (consoleInit(nullptr) != NULL) return true;
        svcSleepThread(SWITCH_DELAY_NS);
    }
    return false;
}

static bool fb_create() {
    for (int i = 0; i < SWITCH_RETRIES; i++) {
        if (R_SUCCEEDED(framebufferCreate(&s_fb, nwindowGetDefault(), GFX_WIDTH, GFX_HEIGHT,
                                          PIXEL_FORMAT_RGBA_8888, 2))) {
            return true;
        }
        svcSleepThread(SWITCH_DELAY_NS);
    }
    return false;
}

bool gfx_hw_begin() {
    if (s_active) return true;

    consoleExit(nullptr);
    svcSleepThread(SWITCH_DELAY_NS);   // let the compositor finish with the console frame
    if (!fb_create()) {
        console_restore();
        return false;
    }
    // Linear mode: we draw into a plain buffer that survives between frames,
    // libnx converts it to the GPU layout on framebufferEnd()
    if (R_FAILED(framebufferMakeLinear(&s_fb))) {
        framebufferClose(&s_fb);
        console_restore();
        return false;
    }

    begin_frame();
    for (uint32_t y = 0; y < GFX_HEIGHT; y++) {
        uint32_t *row = s_buf + y * s_stride_px;
        for (uint32_t x = 0; x < GFX_WIDTH; x++) row[x] = 0xFF000000;   // opaque black
    }
    s_active = true;
    return true;
}

void gfx_hw_end() {
    if (!s_active) return;
    s_active = false;
    s_buf = nullptr;

    framebufferEnd(&s_fb);
    svcSleepThread(SWITCH_DELAY_NS);   // let the compositor finish with the queued frames
    framebufferClose(&s_fb);

    if (console_restore()) {
        app_gfx_ended();
    }
    // Otherwise the screen stays unavailable; printing would crash, so print nothing.
}

bool gfx_hw_active() {
    return s_active;
}

uint32_t *gfx_hw_buffer(uint32_t *stride_px) {
    if (stride_px) *stride_px = s_stride_px;
    return s_active ? s_buf : nullptr;
}

void gfx_hw_present() {
    if (!s_active) return;
    framebufferEnd(&s_fb);
    begin_frame();
}