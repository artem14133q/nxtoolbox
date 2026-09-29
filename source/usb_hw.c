// USB host via libnx (usbHs). Compiled only with devkitA64 (lives in source/).
#include <switch.h>
#include <string.h>
#include <malloc.h>
#include "usb_hw.h"
#include "switch_hw.h"   // app_check_interrupt

#define MAX_HANDLES   8
#define MAX_OPEN_EPS  8
#define WAIT_SLICE_MS 20

typedef struct {
    bool     open;
    uint8_t  addr;
    bool     is_in;
    UsbHsClientEpSession s;
    struct usb_endpoint_descriptor desc;
    void    *buf;            // 0x1000-aligned, required by usbHs
    uint32_t xfer_size;      // how much to request per transfer
    bool     pending;        // a request has been posted but not completed
    uint32_t xfer_id;
    uint32_t rx_len, rx_off; // received data not yet handed to the script
} Ep;

typedef struct {
    bool used;
    UsbHsClientIfSession s;
    UsbHsInterface intf;
    Ep eps[MAX_OPEN_EPS];
} UsbHandle;

static bool     s_ready = false;
static UsbHandle   s_handles[MAX_HANDLES];
static void    *s_ctrl_buf = NULL;
static uint32_t s_last_rc = 0;
static UsbHsInterface s_query[USB_MAX_LIST];

// ---------- initialization ----------

// Initializing usb:hs (even without acquiring any interface) makes the system's own
// keyboard/mouse HID support stop seeing devices behind a USB hub, so this is not called
// eagerly at startup (see hw_init() in switch_hw.c) - only lazily, the first time a script
// actually touches usbhost (query() below), so scripts that never use raw USB access do
// not pay that cost.
void usb_hw_init() {
    if (s_ready) return;
    const Result rc = usbHsInitialize();
    s_ready = R_SUCCEEDED(rc);
    if (!s_ready) s_last_rc = rc;
}

void usb_hw_exit() {
    usb_hw_close_all();
    if (s_ctrl_buf) { free(s_ctrl_buf); s_ctrl_buf = NULL; }
    if (s_ready) usbHsExit();
    s_ready = false;
}

uint32_t usb_hw_last_result() {
    return s_last_rc;
}

// ---------- device list ----------

static int query(s32 *total) {
    usb_hw_init();
    if (!s_ready) return USB_ERR_NOT_READY;
    // An empty filter is rejected, so use "bcdDevice >= 0", which matches everything
    UsbHsInterfaceFilter f = {0};
    f.Flags = UsbHsInterfaceFilterFlags_bcdDevice_Min;
    f.bcdDevice_Min = 0;
    *total = 0;
    const Result rc = usbHsQueryAvailableInterfaces(&f, s_query, sizeof(s_query), total);
    if (R_FAILED(rc)) { s_last_rc = rc; return USB_ERR_IO; }
    if (*total > USB_MAX_LIST) *total = USB_MAX_LIST;
    return 0;
}

static int add_eps(usb_if_info_t *info, const struct usb_endpoint_descriptor *descs) {
    for (int i = 0; i < 15 && info->n_eps < USB_MAX_EPS; i++) {
        const struct usb_endpoint_descriptor *d = &descs[i];
        if (d->bLength == 0) continue;
        usb_ep_info_t *e = &info->eps[info->n_eps++];
        e->addr = d->bEndpointAddress;
        e->type = d->bmAttributes & 0x03;
        e->max_packet = d->wMaxPacketSize & 0x7FF;
    }
    return 0;
}

int usb_hw_list(usb_if_info_t *out, int max) {
    s32 total;
    int err = query(&total);
    if (err) return err;
    int n = 0;
    for (s32 i = 0; i < total && n < max; i++) {
        UsbHsInterface *it = &s_query[i];
        usb_if_info_t *info = &out[n++];
        memset(info, 0, sizeof(*info));
        info->id     = it->inf.ID;
        info->vid    = it->device_desc.idVendor;
        info->pid    = it->device_desc.idProduct;
        info->bus    = it->busID;
        info->dev    = it->deviceID;
        info->iface  = it->inf.interface_desc.bInterfaceNumber;
        info->cls    = it->inf.interface_desc.bInterfaceClass;
        info->subcls = it->inf.interface_desc.bInterfaceSubClass;
        info->proto  = it->inf.interface_desc.bInterfaceProtocol;
        memcpy(info->path, it->pathstr, sizeof(info->path) - 1);
        add_eps(info, it->inf.input_endpoint_descs);
        add_eps(info, it->inf.output_endpoint_descs);
    }
    return n;
}

// ---------- open and close ----------

static UsbHandle *get_handle(int h) {
    if (h < 0 || h >= MAX_HANDLES || !s_handles[h].used) return nullptr;
    return &s_handles[h];
}

int usb_hw_open(const int32_t id) {
    s32 total;
    const int err = query(&total);
    if (err) return err;

    UsbHsInterface *found = nullptr;
    for (s32 i = 0; i < total; i++) {
        if (s_query[i].inf.ID == id) { found = &s_query[i]; break; }
    }
    if (!found) return USB_ERR_NOT_FOUND;

    int h = -1;
    for (int i = 0; i < MAX_HANDLES; i++) {
        if (!s_handles[i].used) { h = i; break; }
    }
    if (h < 0) return USB_ERR_TOO_MANY;

    UsbHandle *hd = &s_handles[h];
    memset(hd, 0, sizeof(*hd));
    hd->intf = *found;
    Result rc = usbHsAcquireUsbIf(&hd->s, &hd->intf);
    if (R_FAILED(rc)) { s_last_rc = rc; return USB_ERR_IO; }
    hd->used = true;
    return h;
}

static void ep_close(Ep *e) {
    if (!e->open) return;
    usbHsEpClose(&e->s);   // also cancels pending requests
    free(e->buf);
    memset(e, 0, sizeof(*e));
}

int usb_hw_close(const int handle) {
    UsbHandle *hd = get_handle(handle);
    if (!hd) return USB_ERR_BAD_HANDLE;
    for (int i = 0; i < MAX_OPEN_EPS; i++) ep_close(&hd->eps[i]);
    usbHsIfClose(&hd->s);
    memset(hd, 0, sizeof(*hd));
    return 0;
}

void usb_hw_close_all() {
    for (int i = 0; i < MAX_HANDLES; i++) {
        if (s_handles[i].used) usb_hw_close(i);
    }
}

// ---------- endpoints ----------

static int ep_reopen(UsbHandle *hd, Ep *e) {
    usbHsEpClose(&e->s);
    e->pending = false;
    e->rx_len = e->rx_off = 0;
    Result rc = usbHsIfOpenUsbEp(&hd->s, &e->s, 1, e->xfer_size, &e->desc);
    if (R_FAILED(rc)) {
        s_last_rc = rc;
        free(e->buf);
        memset(e, 0, sizeof(*e));
        return USB_ERR_IO;
    }
    return 0;
}

// Finds an open endpoint or opens it on first use
static int get_ep(UsbHandle *hd, const uint8_t addr, Ep **out) {
    for (int i = 0; i < MAX_OPEN_EPS; i++) {
        if (hd->eps[i].open && hd->eps[i].addr == addr) { *out = &hd->eps[i]; return 0; }
    }

    const bool is_in = (addr & 0x80) != 0;
    const struct usb_endpoint_descriptor *descs =
        is_in ? hd->intf.inf.input_endpoint_descs : hd->intf.inf.output_endpoint_descs;
    const struct usb_endpoint_descriptor *desc = nullptr;
    for (int i = 0; i < 15; i++) {
        if (descs[i].bLength != 0 && descs[i].bEndpointAddress == addr) { desc = &descs[i]; break; }
    }
    if (!desc) return USB_ERR_NO_EP;

    const uint8_t type = desc->bmAttributes & 0x03;
    if (type != 2 && type != 3) return USB_ERR_NO_EP;   // bulk and interrupt are supported

    Ep *e = nullptr;
    for (int i = 0; i < MAX_OPEN_EPS; i++) {
        if (!hd->eps[i].open) { e = &hd->eps[i]; break; }
    }
    if (!e) return USB_ERR_TOO_MANY;

    memset(e, 0, sizeof(*e));
    e->addr = addr;
    e->is_in = is_in;
    e->desc = *desc;
    uint32_t max_packet = desc->wMaxPacketSize & 0x7FF;
    if (max_packet == 0) max_packet = 64;
    // interrupt: exactly one packet (one HID report); bulk: as much as fits
    e->xfer_size = (type == 3) ? max_packet : USB_MAX_XFER;
    e->buf = memalign(0x1000, USB_MAX_XFER);
    if (!e->buf) return USB_ERR_NOMEM;

    Result rc = usbHsIfOpenUsbEp(&hd->s, &e->s, 1, e->xfer_size, &e->desc);
    if (R_FAILED(rc)) {
        s_last_rc = rc;
        free(e->buf);
        memset(e, 0, sizeof(*e));
        return USB_ERR_IO;
    }
    e->open = true;
    *out = e;
    return 0;
}

// Waits for e->xfer_id to complete for at most timeout_ms, in 20 ms slices,
// checking for a script stop request in between.
static int wait_xfer(Ep *e, const uint32_t timeout_ms, uint32_t *transferred) {
    Event *ev = usbHsEpGetXferEvent(&e->s);
    uint32_t waited = 0;
    for (;;) {
        uint32_t slice = WAIT_SLICE_MS;
        if (timeout_ms != USB_WAIT_FOREVER && timeout_ms - waited < slice) slice = timeout_ms - waited;

        if (R_SUCCEEDED(eventWait(ev, (u64)slice * 1000000ULL))) {
            eventClear(ev);
            UsbHsXferReport reports[8];
            u32 count = 0;
            Result rc = usbHsEpGetXferReport(&e->s, reports, 8, &count);
            if (R_FAILED(rc)) { s_last_rc = rc; e->pending = false; return USB_ERR_IO; }
            for (u32 i = 0; i < count; i++) {
                if (reports[i].xferId != e->xfer_id) continue;
                e->pending = false;
                if (R_FAILED(reports[i].res)) { s_last_rc = reports[i].res; return USB_ERR_IO; }
                *transferred = reports[i].transferredSize;
                return 0;
            }
            continue;   // the event was not about our request
        }

        waited += slice;
        if (timeout_ms != USB_WAIT_FOREVER && waited >= timeout_ms) return USB_ERR_TIMEOUT;
        app_check_interrupt();   // + and -, Ctrl+C, HOME
    }
}

// ---------- transfers ----------

int usb_hw_ctrl(int h, uint8_t type, uint8_t request, uint16_t value,
                uint16_t index, void *buf, uint16_t len) {
    UsbHandle *hd = get_handle(h);
    if (!hd) return USB_ERR_BAD_HANDLE;
    if (len > 0x1000) return USB_ERR_TOO_BIG;
    if (!s_ctrl_buf) {
        s_ctrl_buf = memalign(0x1000, 0x1000);
        if (!s_ctrl_buf) return USB_ERR_NOMEM;
    }

    bool dir_in = (type & 0x80) != 0;
    if (!dir_in && len) memcpy(s_ctrl_buf, buf, len);

    u32 transferred = 0;
    Result rc = usbHsIfCtrlXfer(&hd->s, type, request, value, index, len, s_ctrl_buf, &transferred);
    if (R_FAILED(rc)) { s_last_rc = rc; return USB_ERR_IO; }
    if (dir_in) memcpy(buf, s_ctrl_buf, transferred);
    return (int)transferred;
}

int usb_hw_read(const int handle, const uint8_t ep, void *buf, const uint32_t max, const uint32_t timeout_ms) {
    UsbHandle *hd = get_handle(handle);
    if (!hd) return USB_ERR_BAD_HANDLE;
    if (!(ep & 0x80)) return USB_ERR_NO_EP;
    Ep *e;
    int err = get_ep(hd, ep, &e);
    if (err) return err;

    // First hand out what is left from the previous transfer
    if (e->rx_off < e->rx_len) {
        uint32_t n = e->rx_len - e->rx_off;
        if (n > max) n = max;
        memcpy(buf, (uint8_t *)e->buf + e->rx_off, n);
        e->rx_off += n;
        return (int)n;
    }

    if (!e->pending) {
        u32 id = 0;
        const Result rc = usbHsEpPostBufferAsync(&e->s, e->buf, e->xfer_size, 0, &id);
        if (R_FAILED(rc)) { s_last_rc = rc; return USB_ERR_IO; }
        e->pending = true;
        e->xfer_id = id;
    }

    uint32_t got = 0;
    err = wait_xfer(e, timeout_ms, &got);
    if (err) return err;   // on timeout the request stays active

    e->rx_len = got;
    const uint32_t n = got < max ? got : max;
    memcpy(buf, e->buf, n);
    e->rx_off = n;
    return (int)n;
}

int usb_hw_write(int h, uint8_t addr, const void *data, uint32_t len, uint32_t timeout_ms) {
    UsbHandle *hd = get_handle(h);
    if (!hd) return USB_ERR_BAD_HANDLE;
    if (addr & 0x80) return USB_ERR_NO_EP;
    Ep *e;
    int err = get_ep(hd, addr, &e);
    if (err) return err;

    // The previous write was interrupted: start from a clean state
    if (e->pending && ((err = ep_reopen(hd, e)))) return err;

    uint32_t sent = 0;
    do {
        uint32_t chunk = len - sent;
        if (chunk > e->xfer_size) chunk = e->xfer_size;
        memcpy(e->buf, (const uint8_t *)data + sent, chunk);

        u32 id = 0;
        Result rc = usbHsEpPostBufferAsync(&e->s, e->buf, chunk, 0, &id);
        if (R_FAILED(rc)) { s_last_rc = rc; return USB_ERR_IO; }
        e->pending = true;
        e->xfer_id = id;

        uint32_t done = 0;
        err = wait_xfer(e, timeout_ms, &done);
        if (err == USB_ERR_TIMEOUT) {
            ep_reopen(hd, e);   // cancel the stuck transfer
            return USB_ERR_TIMEOUT;
        }
        if (err) return err;
        sent += done;
        if (done < chunk) break;
    } while (sent < len);
    return (int)sent;
}
