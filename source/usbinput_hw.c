// USB keyboard and mouse through libnx hid. Compiled only with devkitA64 (lives in source/).
#include <switch.h>
#include <string.h>
#include "usbinput_hw.h"

static_assert(KBD_MOD_CTRL        == HidKeyboardModifier_Control,    "modifier mismatch");
static_assert(KBD_MOD_SHIFT       == HidKeyboardModifier_Shift,      "modifier mismatch");
static_assert(KBD_MOD_LEFT_ALT    == HidKeyboardModifier_LeftAlt,    "modifier mismatch");
static_assert(KBD_MOD_RIGHT_ALT   == HidKeyboardModifier_RightAlt,   "modifier mismatch");
static_assert(KBD_MOD_GUI         == HidKeyboardModifier_Gui,        "modifier mismatch");
static_assert(KBD_MOD_CAPS_LOCK   == HidKeyboardModifier_CapsLock,   "modifier mismatch");
static_assert(KBD_MOD_SCROLL_LOCK == HidKeyboardModifier_ScrollLock, "modifier mismatch");
static_assert(KBD_MOD_NUM_LOCK    == HidKeyboardModifier_NumLock,    "modifier mismatch");
static_assert(MOUSE_BTN_LEFT      == HidMouseButton_Left,            "button mismatch");
static_assert(MOUSE_BTN_RIGHT     == HidMouseButton_Right,           "button mismatch");
static_assert(MOUSE_BTN_MIDDLE    == HidMouseButton_Middle,          "button mismatch");
static_assert(MOUSE_BTN_FORWARD   == HidMouseButton_Forward,         "button mismatch");
static_assert(MOUSE_BTN_BACK      == HidMouseButton_Back,            "button mismatch");

static constexpr size_t MOUSE_HISTORY = 17;         // states kept by the system

static bool s_keyboard_ready = false;
static bool s_mouse_ready = false;
static bool s_mouse_seen = false;                   // s_mouse_sample is valid
static u64  s_mouse_sample = 0;                     // newest state already counted

void usbinput_hw_keyboard(kbd_state_t *out) {
    if (!s_keyboard_ready) {
        hidInitializeKeyboard();
        s_keyboard_ready = true;
    }
    *out = (kbd_state_t){};
    HidKeyboardState state = {};
    if (hidGetKeyboardStates(&state, 1) == 0) return;
    memcpy(out->keys, state.keys, sizeof(out->keys));
    out->modifiers = state.modifiers;
}

void usbinput_hw_mouse(mouse_state_t *out) {
    if (!s_mouse_ready) {
        hidInitializeMouse();
        s_mouse_ready = true;
    }
    *out = (mouse_state_t){};
    HidMouseState states[MOUSE_HISTORY];
    const size_t n = hidGetMouseStates(states, MOUSE_HISTORY);
    if (n == 0) return;

    // Newest state: the largest sampling number (does not depend on the order of the array)
    const HidMouseState *latest = &states[0];
    for (size_t i = 1; i < n; i++) {
        if (states[i].sampling_number > latest->sampling_number) latest = &states[i];
    }
    out->x = latest->x;
    out->y = latest->y;
    out->buttons = latest->buttons;
    out->connected = (latest->attributes & HidMouseAttribute_IsConnected) != 0;

    // Movement and wheel: sum of all states newer than the previous call, so nothing is
    // lost between frames. The first call only remembers where we are.
    if (s_mouse_seen) {
        for (size_t i = 0; i < n; i++) {
            if (states[i].sampling_number <= s_mouse_sample) continue;
            out->dx += states[i].delta_x;
            out->dy += states[i].delta_y;
            out->wheel += states[i].wheel_delta_x;
            out->wheel_h += states[i].wheel_delta_y;
        }
    }
    s_mouse_sample = latest->sampling_number;
    s_mouse_seen = true;
}
