// Python module `usbhost`: low-level access to USB devices connected to the Switch.
// No libnx headers here, only usb_hw.h.
#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "usb_hw.h"

static usb_if_info_t s_list[USB_MAX_LIST];
static uint8_t s_io_buf[USB_MAX_XFER];

static void raise_usb(int err) {
    const char *msg;
    switch (err) {
        case USB_ERR_TIMEOUT:    msg = "timed out"; break;
        case USB_ERR_NOT_READY:  msg = "USB host service is not available"; break;
        case USB_ERR_BAD_HANDLE: msg = "invalid or closed handle"; break;
        case USB_ERR_NO_EP:      msg = "no such bulk/interrupt endpoint on this interface"; break;
        case USB_ERR_NOT_FOUND:  msg = "interface not found (unplugged or already open)"; break;
        case USB_ERR_TOO_MANY:   msg = "too many open interfaces or endpoints"; break;
        case USB_ERR_NOMEM:      msg = "out of memory"; break;
        case USB_ERR_TOO_BIG:    msg = "transfer too large"; break;
        default:                 msg = "transfer failed"; break;
    }
    if (err == USB_ERR_IO || err == USB_ERR_NOT_READY) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("usb: %s (0x%x)"), msg,
                          (unsigned)usb_hw_last_result());
    }
    mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("usb: %s"), msg);
}

static int check(const int r) {
    if (r < 0) raise_usb(r);
    return r;
}

static mp_obj_t new_small(mp_int_t v) {
    return MP_OBJ_NEW_SMALL_INT(v);
}

// usbhost.devices() -> [dict, ...]
// Keys: id, vid, pid, bus, dev, path, iface, cls, subcls, proto,
//       eps - list of (address, type, packet size); type: 2 bulk, 3 interrupt
static mp_obj_t mod_devices() {
    int n = check(usb_hw_list(s_list, USB_MAX_LIST));
    mp_obj_t result = mp_obj_new_list(0, nullptr);
    for (int i = 0; i < n; i++) {
        usb_if_info_t *it = &s_list[i];
        mp_obj_t d = mp_obj_new_dict(11);
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_id),     mp_obj_new_int(it->id));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_vid),    new_small(it->vid));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_pid),    new_small(it->pid));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_bus),    mp_obj_new_int_from_uint(it->bus));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_dev),    mp_obj_new_int_from_uint(it->dev));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_path),   mp_obj_new_str(it->path, strlen(it->path)));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_iface),  new_small(it->iface));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_cls),    new_small(it->cls));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_subcls), new_small(it->subcls));
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_proto),  new_small(it->proto));

        // ReSharper disable once CppLocalVariableMayBeConst
        mp_obj_t eps = mp_obj_new_list(0, nullptr);
        for (int j = 0; j < it->n_eps; j++) {
            const mp_obj_t t[3] = {
                new_small(it->eps[j].addr),
                new_small(it->eps[j].type),
                new_small(it->eps[j].max_packet),
            };
            mp_obj_list_append(eps, mp_obj_new_tuple(3, t));
        }
        mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_eps), eps);
        mp_obj_list_append(result, d);
    }
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_devices_obj, mod_devices);

// usbhost.open(id) -> handle
static mp_obj_t mod_open(mp_obj_t id_in) {
    return new_small(check(usb_hw_open((int32_t)mp_obj_get_int(id_in))));
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_open_obj, mod_open);

// usbhost.close(handle)
// ReSharper disable once CppParameterMayBeConst
static mp_obj_t mod_close(mp_obj_t h_in) {
    check(usb_hw_close((int)mp_obj_get_int(h_in)));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_close_obj, mod_close);

// usbhost.ctrl(handle, bmRequestType, bRequest, wValue, wIndex, data_or_length)
//   IN  (bmRequestType & 0x80): the last argument is a length, returns bytes
//   OUT: the last argument is bytes (b"" allowed), returns the number of bytes sent
static mp_obj_t mod_ctrl(size_t n_args, const mp_obj_t *args) {
    const int h = (int)mp_obj_get_int(args[0]);
    const uint8_t type = (uint8_t)mp_obj_get_int(args[1]);
    const uint8_t req = (uint8_t)mp_obj_get_int(args[2]);
    const uint16_t value = (uint16_t)mp_obj_get_int(args[3]);
    const uint16_t index = (uint16_t)mp_obj_get_int(args[4]);

    if (type & 0x80) {
        const mp_int_t len = n_args > 5 ? mp_obj_get_int(args[5]) : 0;
        if (len < 0 || len > 0x1000) raise_usb(USB_ERR_TOO_BIG);
        const int n = check(usb_hw_ctrl(h, type, req, value, index, s_io_buf, (uint16_t)len));
        return mp_obj_new_bytes(s_io_buf, n);
    }

    mp_buffer_info_t bi = { .buf = NULL, .len = 0 };
    if (n_args > 5) mp_get_buffer_raise(args[5], &bi, MP_BUFFER_READ);
    if (bi.len > 0x1000) raise_usb(USB_ERR_TOO_BIG);
    int n = check(usb_hw_ctrl(h, type, req, value, index, bi.buf, (uint16_t)bi.len));
    return new_small(n);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_ctrl_obj, 5, 6, mod_ctrl);

// usbhost.read(handle, ep, size=512, timeout_ms=100) -> bytes, or None on timeout
static mp_obj_t mod_read(size_t n_args, const mp_obj_t *args) {
    const int h = (int)mp_obj_get_int(args[0]);
    const uint8_t ep = (uint8_t)mp_obj_get_int(args[1]);
    const mp_int_t size = n_args > 2 ? mp_obj_get_int(args[2]) : 512;
    const mp_int_t timeout = n_args > 3 ? mp_obj_get_int(args[3]) : 100;
    if (size <= 0 || size > USB_MAX_XFER) raise_usb(USB_ERR_TOO_BIG);

    int n = usb_hw_read(h, ep, s_io_buf, (uint32_t)size,
                        timeout < 0 ? USB_WAIT_FOREVER : (uint32_t)timeout);
    if (n == USB_ERR_TIMEOUT) return mp_const_none;
    check(n);
    return mp_obj_new_bytes(s_io_buf, n);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_read_obj, 2, 4, mod_read);

// usbhost.write(handle, ep, data, timeout_ms=1000) -> number of bytes sent
static mp_obj_t mod_write(size_t n_args, const mp_obj_t *args) {
    const int h = (int)mp_obj_get_int(args[0]);
    const uint8_t ep = (uint8_t)mp_obj_get_int(args[1]);
    mp_buffer_info_t bi;
    mp_get_buffer_raise(args[2], &bi, MP_BUFFER_READ);
    const mp_int_t timeout = n_args > 3 ? mp_obj_get_int(args[3]) : 1000;
    int n = check(usb_hw_write(h, ep, bi.buf, (uint32_t)bi.len,
                               timeout < 0 ? USB_WAIT_FOREVER : (uint32_t)timeout));
    return new_small(n);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_write_obj, 3, 4, mod_write);

static const mp_rom_map_elem_t usbhost_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_usbhost) },
    { MP_ROM_QSTR(MP_QSTR_devices),  MP_ROM_PTR(&mod_devices_obj) },
    { MP_ROM_QSTR(MP_QSTR_open),     MP_ROM_PTR(&mod_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_close),    MP_ROM_PTR(&mod_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_ctrl),     MP_ROM_PTR(&mod_ctrl_obj) },
    { MP_ROM_QSTR(MP_QSTR_read),     MP_ROM_PTR(&mod_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_write),    MP_ROM_PTR(&mod_write_obj) },

    // Endpoint types
    { MP_ROM_QSTR(MP_QSTR_BULK),      MP_ROM_INT(2) },
    { MP_ROM_QSTR(MP_QSTR_INTERRUPT), MP_ROM_INT(3) },
};
static MP_DEFINE_CONST_DICT(usbhost_module_globals, usbhost_module_globals_table);

// ReSharper disable once CppUseInternalLinkage
const mp_obj_module_t usbhost_user_cmodule = { // NOLINT(*-interfaces-global-init)
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&usbhost_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_usbhost, usbhost_user_cmodule);
