// Glue between main.c (libnx) and the MicroPython interrupt mechanism.
// Only MicroPython headers here, no <switch.h>.
#include "py/runtime.h"
#include "py/mpstate.h"
#include "switch_hw.h"

bool app_poll_stop();  // defined in main.c

// Called by the interpreter every MICROPY_VM_HOOK_COUNT instructions
// (see mpconfigport.h). Schedules a KeyboardInterrupt if needed.
// ReSharper disable once CppUseInternalLinkage
void app_vm_hook() {
    if (app_poll_stop()) {
        mp_sched_keyboard_interrupt();
    }
}

// For long-running C functions (e.g. switch.sleep_ms): check for a stop request
// and, if there is one, raise KeyboardInterrupt right away.
void app_check_interrupt() {
    app_vm_hook();
    // ReSharper disable once CppLocalVariableMayBeConst
    mp_obj_t exc = MP_STATE_THREAD(mp_pending_exception);
    if (exc != MP_OBJ_NULL) {
        MP_STATE_THREAD(mp_pending_exception) = MP_OBJ_NULL;
        nlr_raise(exc);
    }
}

// We do not need a terminal interrupt character: stopping works via network and buttons.
// weak, so there is no conflict if MicroPython provides its own version.
__attribute__((weak)) void mp_hal_set_interrupt_char(const int c) {
    (void)c;
}

// For code that must not raise (e.g. inside libcurl callbacks in http_hw.c): returns true
// if the script should stop. The KeyboardInterrupt stays pending and is raised later.
// ReSharper disable once CppUseInternalLinkage
bool app_stop_requested() {
    app_vm_hook();
    return MP_STATE_THREAD(mp_pending_exception) != MP_OBJ_NULL;
}
