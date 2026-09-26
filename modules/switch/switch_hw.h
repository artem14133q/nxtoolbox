// Thin layer between the MicroPython module and libnx.
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>

// Button bits match HidNpadButton_* from libnx
// (checked with static_assert in switch_hw.c)
#define HW_BTN_A      (1ULL << 0)
#define HW_BTN_B      (1ULL << 1)
#define HW_BTN_X      (1ULL << 2)
#define HW_BTN_Y      (1ULL << 3)
#define HW_BTN_LSTICK (1ULL << 4)
#define HW_BTN_RSTICK (1ULL << 5)
#define HW_BTN_L      (1ULL << 6)
#define HW_BTN_R      (1ULL << 7)
#define HW_BTN_ZL     (1ULL << 8)
#define HW_BTN_ZR     (1ULL << 9)
#define HW_BTN_PLUS   (1ULL << 10)
#define HW_BTN_MINUS  (1ULL << 11)
#define HW_BTN_LEFT   (1ULL << 12)
#define HW_BTN_UP     (1ULL << 13)
#define HW_BTN_RIGHT  (1ULL << 14)
#define HW_BTN_DOWN   (1ULL << 15)

#define HW_MAX_TOUCHES 16

void hw_init();
void hw_exit();

// Called from main.c before and after every script
void hw_script_begin();   // reset press tracking
void hw_script_end();     // stop rumble, close USB devices

uint64_t hw_buttons_held();   // held right now
uint64_t hw_buttons_down();   // pressed since the previous hw_buttons_down call
int      hw_battery();        // charge in %, -1 on error
void     hw_sleep_ms(uint32_t ms);
uint64_t hw_ticks_ms();       // milliseconds since the console was powered on
bool     hw_running();        // false if the system asked the app to exit

// Stick: index 0 left, 1 right; x, y from -1.0 to 1.0 (up and right are positive)
void     hw_stick(int index, float *x, float *y);

// Screen touches (handheld mode only): coordinates 0..1279 x 0..719.
// Returns the number of touches (at most max).
int      hw_touches(int *xs, int *ys, int max);

// Rumble: strength 0.0..1.0, frequencies of the low and high bands in Hz.
// Lasts until called again or hw_rumble_stop().
void     hw_rumble(float amp, float freq_low, float freq_high);
void     hw_rumble_stop();

// Defined in source/mp_glue.c: raises KeyboardInterrupt
// if the user asked to stop the script
void app_check_interrupt();
