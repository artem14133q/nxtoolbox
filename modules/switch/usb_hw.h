// USB host: thin layer between the usbhost MicroPython module and libnx (usbHs).
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>
#include <stdbool.h>

#define USB_MAX_LIST        32      // how many interfaces usb_hw_list returns
#define USB_MAX_EPS         30      // up to 15 IN + 15 OUT per interface
#define USB_MAX_XFER        4096    // maximum size of a single transfer
#define USB_WAIT_FOREVER    0xFFFFFFFFu

// Error codes (negative)
#define USB_ERR_TIMEOUT     (-1)
#define USB_ERR_NOT_READY   (-2)    // the USB host service did not start
#define USB_ERR_BAD_HANDLE  (-3)
#define USB_ERR_NO_EP       (-4)    // the interface has no such endpoint
#define USB_ERR_NOT_FOUND   (-5)    // interface not found (unplugged or already open)
#define USB_ERR_TOO_MANY    (-6)    // too many open interfaces
#define USB_ERR_NOMEM       (-7)
#define USB_ERR_IO          (-8)    // transfer error (see usb_hw_last_result)
#define USB_ERR_TOO_BIG     (-9)

typedef struct {
    uint8_t  addr;          // address: bit 0x80 means IN (from the device), otherwise OUT
    uint8_t  type;          // 0 control, 1 isochronous, 2 bulk, 3 interrupt
    uint16_t max_packet;
} usb_ep_info_t;

typedef struct {
    int32_t  id;            // interface identifier for usb_hw_open
    uint16_t vid, pid;
    uint32_t bus, dev;      // together they identify the device
    char     path[64];
    uint8_t  iface;         // bInterfaceNumber
    uint8_t  cls, subcls, proto;
    int      n_eps;
    usb_ep_info_t eps[USB_MAX_EPS];
} usb_if_info_t;

void     usb_hw_init(void);
void     usb_hw_exit(void);
void     usb_hw_close_all(void);        // called after every script
uint32_t usb_hw_last_result(void);      // libnx code of the last error (for messages)

int  usb_hw_list(usb_if_info_t *out, int max);          // count or error
int  usb_hw_open(int32_t id);                           // handle >= 0 or error
int  usb_hw_close(int handle);

// Control request via endpoint 0. If (type & 0x80): read into buf,
// otherwise send len bytes from buf. Returns the number of bytes transferred or an error.
int  usb_hw_ctrl(int handle, uint8_t type, uint8_t request, uint16_t value,
                 uint16_t index, void *buf, uint16_t len);

// Read from an IN endpoint: number of bytes (0 = empty packet) or an error (USB_ERR_TIMEOUT).
// After a timeout the request stays active, and the next call keeps waiting for it.
int  usb_hw_read(int handle, uint8_t ep, void *buf, uint32_t max, uint32_t timeout_ms);

// Write to an OUT endpoint: number of bytes sent or an error.
int  usb_hw_write(int handle, uint8_t ep, const void *buf, uint32_t len, uint32_t timeout_ms);
