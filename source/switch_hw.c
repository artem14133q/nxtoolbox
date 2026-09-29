// Implementation on top of libnx. Compiled only with devkitA64 (lives in source/).
#include <switch.h>
#include <string.h>
#include "switch_hw.h"
#include "usb_hw.h"

_Static_assert(HW_BTN_A      == HidNpadButton_A,      "button mismatch");
_Static_assert(HW_BTN_B      == HidNpadButton_B,      "button mismatch");
_Static_assert(HW_BTN_X      == HidNpadButton_X,      "button mismatch");
_Static_assert(HW_BTN_Y      == HidNpadButton_Y,      "button mismatch");
_Static_assert(HW_BTN_LSTICK == HidNpadButton_StickL, "button mismatch");
_Static_assert(HW_BTN_RSTICK == HidNpadButton_StickR, "button mismatch");
_Static_assert(HW_BTN_L      == HidNpadButton_L,      "button mismatch");
_Static_assert(HW_BTN_R      == HidNpadButton_R,      "button mismatch");
_Static_assert(HW_BTN_ZL     == HidNpadButton_ZL,     "button mismatch");
_Static_assert(HW_BTN_ZR     == HidNpadButton_ZR,     "button mismatch");
_Static_assert(HW_BTN_PLUS   == HidNpadButton_Plus,   "button mismatch");
_Static_assert(HW_BTN_MINUS  == HidNpadButton_Minus,  "button mismatch");
_Static_assert(HW_BTN_UP     == HidNpadButton_Up,     "button mismatch");
_Static_assert(HW_BTN_DOWN   == HidNpadButton_Down,   "button mismatch");
_Static_assert(HW_BTN_LEFT   == HidNpadButton_Left,   "button mismatch");
_Static_assert(HW_BTN_RIGHT  == HidNpadButton_Right,  "button mismatch");

static PadState s_pad;          // own pad state, independent of main.c
static u64  s_down_prev = 0;    // buttons held at the previous hw_buttons_down()
static bool s_psm_ok = false;

// ---------- synthetic input (see switch_hw.h) ----------
#define REMOTE_MAX_MS 5000       // safety cap: never "hold" longer than this

static u32 s_remote_buttons = 0;
static u64 s_remote_buttons_until = 0;   // hw_ticks_ms() deadline; 0 = nothing held

static bool s_remote_touch_on = false;
static int  s_remote_tx0, s_remote_ty0, s_remote_tx1, s_remote_ty1;
static u64  s_remote_touch_start, s_remote_touch_end;

// Rumble: motor handles for three connection types.
// The signal is sent to all of them; unconnected ones just return an error.
#define VIB_SETS 3
static HidVibrationDeviceHandle s_vib[VIB_SETS][2];
static bool s_vib_ok[VIB_SETS];
static bool s_rumbling = false;

void hw_init() {
    padInitializeDefault(&s_pad);
    s_psm_ok = R_SUCCEEDED(psmInitialize());

    hidInitializeTouchScreen();

    // Handheld mode, Joy-Con pair, Pro Controller
    s_vib_ok[0] = R_SUCCEEDED(hidInitializeVibrationDevices(s_vib[0], 2,
                      HidNpadIdType_Handheld, HidNpadStyleTag_NpadHandheld));
    s_vib_ok[1] = R_SUCCEEDED(hidInitializeVibrationDevices(s_vib[1], 2,
                      HidNpadIdType_No1, HidNpadStyleTag_NpadJoyDual));
    s_vib_ok[2] = R_SUCCEEDED(hidInitializeVibrationDevices(s_vib[2], 2,
                      HidNpadIdType_No1, HidNpadStyleTag_NpadFullKey));

    // usb_hw_init() is NOT called here: see the comment on it in usb_hw.c. It only starts
    // once a script actually uses usbhost, so the system's own external keyboard/mouse
    // support keeps working for scripts that do not touch raw USB.
}

void hw_exit() {
    hw_rumble_stop();
    usb_hw_exit();
    if (s_psm_ok) psmExit();
}

void hw_script_begin() {
    // Buttons held at launch (e.g. A in the menu) do not count as new presses
    padUpdate(&s_pad);
    s_down_prev = padGetButtons(&s_pad);
}

void hw_script_end() {
    hw_rumble_stop();     // the script may have ended in the middle of a rumble
    usb_hw_close_all();   // or left USB devices open
}

// Clears the synthetic buttons once their hold_ms has passed; called from both
// hw_buttons_held() and hw_buttons_down() so neither ever misses an expiry.
static u64 remote_buttons_now() {
    if (s_remote_buttons_until && hw_ticks_ms() >= s_remote_buttons_until) {
        s_remote_buttons = 0;
        s_remote_buttons_until = 0;
    }
    return s_remote_buttons;
}

uint64_t hw_buttons_held() {
    padUpdate(&s_pad);
    return padGetButtons(&s_pad) | remote_buttons_now();
}

uint64_t hw_buttons_down() {
    // Own tracking instead of padGetButtonsDown: otherwise any other padUpdate call
    // (buttons(), stick()) would swallow presses
    padUpdate(&s_pad);
    u64 cur = padGetButtons(&s_pad) | remote_buttons_now();
    u64 down = cur & ~s_down_prev;
    s_down_prev = cur;
    return down;
}

int hw_battery() {
    u32 charge = 0;
    if (!s_psm_ok || R_FAILED(psmGetBatteryChargePercentage(&charge))) return -1;
    return (int)charge;
}

void hw_sleep_ms(const uint32_t ms) {
    svcSleepThread((s64)ms * 1000000LL);
}

uint64_t hw_ticks_ms() {
    return armTicksToNs(armGetSystemTick()) / 1000000ULL;
}

bool hw_running() {
    consoleUpdate(nullptr);        // refresh the screen as well
    return appletMainLoop();    // handles HOME and system events
}

void hw_stick(const int index, float *x, float *y) {
    padUpdate(&s_pad);
    const HidAnalogStickState st = padGetStickPos(&s_pad, index ? 1 : 0);
    *x = (float)st.x / (float)JOYSTICK_MAX;
    *y = (float)st.y / (float)JOYSTICK_MAX;
}

int hw_touches(int *xs, int *ys, int max) {
    if (s_remote_touch_on) {
        const u64 now = hw_ticks_ms();
        if (now >= s_remote_touch_end) {
            s_remote_touch_on = false;   // expired: fall through to the real touch screen below
        } else if (max > 0) {
            const u64 total = s_remote_touch_end - s_remote_touch_start;
            const u64 elapsed = now - s_remote_touch_start;
            const int permille = total ? (int)(elapsed * 1000 / total) : 1000;
            xs[0] = s_remote_tx0 + (s_remote_tx1 - s_remote_tx0) * permille / 1000;
            ys[0] = s_remote_ty0 + (s_remote_ty1 - s_remote_ty0) * permille / 1000;
            return 1;   // a real finger on the screen is ignored while this is active
        }
    }

    HidTouchScreenState state = {0};
    if (hidGetTouchScreenStates(&state, 1) == 0) return 0;
    int n = state.count;
    if (n > max) n = max;
    if (n > HW_MAX_TOUCHES) n = HW_MAX_TOUCHES;
    for (int i = 0; i < n; i++) {
        xs[i] = (int)state.touches[i].x;
        ys[i] = (int)state.touches[i].y;
    }
    return n;
}

// ---------- synthetic input ----------

void hw_remote_press(const uint32_t mask, uint32_t hold_ms) {
    if (hold_ms > REMOTE_MAX_MS) hold_ms = REMOTE_MAX_MS;
    s_remote_buttons = mask;
    s_remote_buttons_until = hw_ticks_ms() + hold_ms;
}

void hw_remote_touch(const int x0, const int y0, const int x1, const int y1, uint32_t duration_ms) {
    if (duration_ms > REMOTE_MAX_MS) duration_ms = REMOTE_MAX_MS;
    s_remote_tx0 = x0; s_remote_ty0 = y0;
    s_remote_tx1 = x1; s_remote_ty1 = y1;
    s_remote_touch_start = hw_ticks_ms();
    s_remote_touch_end = s_remote_touch_start + duration_ms;
    s_remote_touch_on = true;
}

void hw_remote_cancel() {
    s_remote_buttons = 0;
    s_remote_buttons_until = 0;
    s_remote_touch_on = false;
}

static float clampf(const float v, const float lo, const float hi) {
    return v < lo ? lo : v > hi ? hi : v;
}

void hw_rumble(const float amp, const float freq_low, const float freq_high) {
    HidVibrationValue v[2];
    v[0].amp_low   = clampf(amp, 0.0f, 1.0f);
    v[0].freq_low  = clampf(freq_low, 10.0f, 1250.0f);
    v[0].amp_high  = v[0].amp_low;
    v[0].freq_high = clampf(freq_high, 10.0f, 1250.0f);
    v[1] = v[0];   // same values for both motors (left and right)

    for (int i = 0; i < VIB_SETS; i++) {
        if (s_vib_ok[i]) hidSendVibrationValues(s_vib[i], v, 2);
    }
    s_rumbling = v[0].amp_low > 0.0f;
}

void hw_rumble_stop() {
    if (!s_rumbling) return;
    HidVibrationValue v[2] = {0};
    v[0].freq_low = 160.0f;    // neutral frequencies with zero strength
    v[0].freq_high = 320.0f;
    v[1] = v[0];
    for (int i = 0; i < VIB_SETS; i++) {
        if (s_vib_ok[i]) hidSendVibrationValues(s_vib[i], v, 2);
    }
    s_rumbling = false;
}

bool hw_keyboard(const char *initial, const char *hint, char *out, const size_t out_size) {
    SwkbdConfig kbd;
    if (R_FAILED(swkbdCreate(&kbd, 0))) return false;
    swkbdConfigMakePresetDefault(&kbd);
    if (initial && initial[0]) swkbdConfigSetInitialText(&kbd, initial);
    if (hint && hint[0]) swkbdConfigSetGuideText(&kbd, hint);
    const Result rc = swkbdShow(&kbd, out, out_size);
    swkbdClose(&kbd);
    return R_SUCCEEDED(rc);                     // fails when the user cancels
}