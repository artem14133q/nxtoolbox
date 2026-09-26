#pragma once

// Configuration of the embedded MicroPython.
#include <port/mpconfigport_common.h>

// Basic set of language features (more than MINIMUM)
#define MICROPY_CONFIG_ROM_LEVEL      (MICROPY_CONFIG_ROM_LEVEL_CORE_FEATURES)

#define MICROPY_ENABLE_COMPILER       (1)
#define MICROPY_ENABLE_GC             (1)
#define MICROPY_PY_GC                 (1)
#define MICROPY_PY_JSON               (1)

// float/double and arbitrary-precision integers
#define MICROPY_FLOAT_IMPL            (MICROPY_FLOAT_IMPL_DOUBLE)
#define MICROPY_LONGINT_IMPL          (MICROPY_LONGINT_IMPL_MPZ)

// Line numbers in tracebacks: important for debugging
#define MICROPY_ENABLE_SOURCE_LINE    (1)
#define MICROPY_ERROR_REPORTING       (MICROPY_ERROR_REPORTING_DETAILED)

// Platform name (sys.platform) and banner strings
#define MICROPY_PY_SYS_PLATFORM       "switch"
#define MICROPY_HW_BOARD_NAME         "Nintendo Switch"
#define MICROPY_HW_MCU_NAME           "Tegra X1"

// ---- Stopping scripts ----
// Enables KeyboardInterrupt
#define MICROPY_KBD_EXCEPTION         (1)

// Every MICROPY_VM_HOOK_COUNT instructions the interpreter calls app_vm_hook()
// (source/mp_glue.c), which checks the buttons and the network.
#define MICROPY_VM_HOOK_COUNT         (100)
#define MICROPY_VM_HOOK_INIT          static unsigned int vm_hook_divisor = MICROPY_VM_HOOK_COUNT;
#define MICROPY_VM_HOOK_POLL          if (--vm_hook_divisor == 0) { \
                                          vm_hook_divisor = MICROPY_VM_HOOK_COUNT; \
                                          extern void app_vm_hook(void); \
                                          app_vm_hook(); \
                                      }
#define MICROPY_VM_HOOK_LOOP          MICROPY_VM_HOOK_POLL
#define MICROPY_VM_HOOK_RETURN        MICROPY_VM_HOOK_POLL

// Needed by micropython.kbd_intr(); does nothing here (see mp_glue.c)
void mp_hal_set_interrupt_char(int c);

// ---- Filesystem ----
// VfsPosix: open(), os.listdir() and import work through the libnx POSIX functions
#define MICROPY_VFS                   (1)
#define MICROPY_VFS_POSIX             (1)
#define MICROPY_PY_VFS                (1)
#define MICROPY_PY_OS                 (1)
#define MICROPY_READER_VFS            (1)   // import your own .py files from the SD card
#define MICROPY_ENABLE_FINALISER      (1)   // the GC closes files that were not closed

// Needed by vfs_posix.c: run a system call and raise OSError on failure
#define MP_HAL_RETRY_SYSCALL(ret, syscall, raise) \
    { ret = syscall; if (ret == -1) { int err = errno; raise; } }
