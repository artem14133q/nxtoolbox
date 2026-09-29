// USB keyboard and mouse through the system input service (libnx hid).
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>
#include <stdbool.h>

// Keyboard modifier bits (match HidKeyboardModifier_*, checked in usbinput_hw.c)
#define KBD_MOD_CTRL         (1ULL << 0)
#define KBD_MOD_SHIFT        (1ULL << 1)
#define KBD_MOD_LEFT_ALT     (1ULL << 2)
#define KBD_MOD_RIGHT_ALT    (1ULL << 3)
#define KBD_MOD_GUI          (1ULL << 4)
#define KBD_MOD_CAPS_LOCK    (1ULL << 8)
#define KBD_MOD_SCROLL_LOCK  (1ULL << 9)
#define KBD_MOD_NUM_LOCK     (1ULL << 10)

// Mouse button bits (match HidMouseButton_*)
#define MOUSE_BTN_LEFT       (1U << 0)
#define MOUSE_BTN_RIGHT      (1U << 1)
#define MOUSE_BTN_MIDDLE     (1U << 2)
#define MOUSE_BTN_FORWARD    (1U << 3)
#define MOUSE_BTN_BACK       (1U << 4)

typedef struct {
    uint64_t keys[4];           // bit N set = key with HID usage code N is held
    uint64_t modifiers;         // KBD_MOD_* (lock bits are the lock state)
} kbd_state_t;

typedef struct {
    int32_t  x, y;              // cursor position (kept inside the screen by the system)
    int32_t  dx, dy;            // movement since the previous call
    int32_t  wheel, wheel_h;    // wheel steps since the previous call (raw WheelDeltaX / Y)
    uint32_t buttons;           // MOUSE_BTN_* held
    bool     connected;
} mouse_state_t;

void usbinput_hw_keyboard(kbd_state_t *out);
void usbinput_hw_mouse(mouse_state_t *out);
