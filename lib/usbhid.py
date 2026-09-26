"""USB HID for nxtest: reading and sending HID reports.

Suitable for custom HID devices (microcontrollers), gamepads,
button panels and so on. Devices the Switch system uses itself
(official controllers, probably keyboards and mice) may be unavailable.

Report format as in hidapi: when writing, the first byte is the Report ID
(0 if the device does not use IDs).

Example:
    import usbhid
    with usbhid.HID(vid=0x1234) as dev:
        report = dev.read(timeout=500)     # bytes or None
        dev.write(bytes([0, 1, 2, 3]))     # Report ID 0 + data
"""
import usbhost

CLASS_HID = 0x03

# HID class requests
GET_REPORT = 0x01
SET_REPORT = 0x09
REPORT_INPUT = 0x01
REPORT_OUTPUT = 0x02
REPORT_FEATURE = 0x03


def devices():
    """HID interfaces available to open (entries from usbhost.devices())."""
    return [d for d in usbhost.devices() if d["cls"] == CLASS_HID]


class HID:
    """Opens a HID interface.

    vid, pid - vendor/product filter (None matches any)
    index    - which one of the matching devices
    """

    def __init__(self, vid=None, pid=None, index=0):
        found = [d for d in devices()
                 if (vid is None or d["vid"] == vid) and (pid is None or d["pid"] == pid)]
        if len(found) <= index:
            raise OSError("USB HID device not found")
        d = found[index]
        self.info = d
        self.vid = d["vid"]
        self.pid = d["pid"]
        self._iface = d["iface"]
        self._ep_in = None
        self._ep_out = None
        self.report_size = 64
        for addr, typ, size in d["eps"]:
            if typ == usbhost.INTERRUPT:
                if addr & 0x80:
                    self._ep_in = addr
                    self.report_size = size
                else:
                    self._ep_out = addr
        self._h = usbhost.open(d["id"])

    # ---------- input reports (from the device) ----------

    def read(self, timeout=100):
        """Next input report (bytes), or None if nothing arrived within timeout ms."""
        if self._ep_in is None:
            raise OSError("HID device has no input endpoint")
        return usbhost.read(self._h, self._ep_in, self.report_size, timeout)

    def get_input(self, report_id=0, size=None):
        """Request an input report over the control pipe (not all devices support it)."""
        return usbhost.ctrl(self._h, 0xA1, GET_REPORT, (REPORT_INPUT << 8) | report_id,
                            self._iface, size or self.report_size)

    # ---------- output reports (to the device) ----------

    def write(self, report, timeout=1000):
        """Send an output report. report[0] is the Report ID (0 if IDs are not used)."""
        report = self._as_bytes(report)
        rid = report[0]
        payload = report[1:] if rid == 0 else report
        if self._ep_out is not None:
            return usbhost.write(self._h, self._ep_out, payload, timeout)
        # No OUT endpoint: send over the control pipe (SET_REPORT)
        return usbhost.ctrl(self._h, 0x21, SET_REPORT, (REPORT_OUTPUT << 8) | rid,
                            self._iface, payload)

    # ---------- feature reports (device settings) ----------

    def get_feature(self, report_id, size):
        return usbhost.ctrl(self._h, 0xA1, GET_REPORT, (REPORT_FEATURE << 8) | report_id,
                            self._iface, size)

    def set_feature(self, report):
        """report[0] is the Report ID (0 if IDs are not used)."""
        report = self._as_bytes(report)
        rid = report[0]
        payload = report[1:] if rid == 0 else report
        return usbhost.ctrl(self._h, 0x21, SET_REPORT, (REPORT_FEATURE << 8) | rid,
                            self._iface, payload)

    # ---------- device description ----------

    def report_descriptor(self, size=1024):
        """HID Report Descriptor: describes the format of the device reports."""
        return usbhost.ctrl(self._h, 0x81, 0x06, 0x2200, self._iface, size)

    # ---------- helpers ----------

    @staticmethod
    def _as_bytes(report):
        if isinstance(report, str):
            report = report.encode()
        report = bytes(report)
        if not report:
            raise ValueError("report must contain at least the Report ID byte")
        return report

    def close(self):
        if self._h is not None:
            try:
                usbhost.close(self._h)
            except OSError:
                pass
            self._h = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
