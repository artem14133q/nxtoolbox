"""Black Pill HID demo: talks to firmware/blackpill_hid over USB HID.

Shows the KEY button of the board, the chip temperature and the report rate; controls the
board's LED. Pressing KEY on the board makes the Joy-Con rumble.

The Switch system takes HID-class devices for itself, so the firmware is built with a
vendor-specific interface class (0xFF, see firmware/blackpill_hid/SETUP.md). The script
finds the board either way: as a HID device, or directly through usbhost.
"""
__NXTOOLBOX_MODULE__ = {
    "title": "Black Pill HID",
    "description": "STM32 USB HID demo",
    "version": "1.0",
}

import switch
import ui
import usbhid
import usbhost

VID, PID = 0x0483, 0x5750          # STMicroelectronics, Custom HID (CubeMX defaults)
REPORT = 64
CMD_LED, CMD_BLINK = 1, 2


class VendorDevice:
    """The board with a vendor-specific interface (class 0xFF): the same 64-byte reports
    over its interrupt endpoints, with the same read()/write() as usbhid.HID."""

    def __init__(self, vid, pid):
        for d in usbhost.devices():
            if d["vid"] == vid and d["pid"] == pid:
                break
        else:
            raise OSError("USB device %04x:%04x not found" % (vid, pid))
        self.vid, self.pid = vid, pid
        self._in = self._out = None
        for addr, typ, size in d["eps"]:
            if typ == usbhost.INTERRUPT:
                if addr & 0x80:
                    self._in = addr
                else:
                    self._out = addr
        if self._in is None or self._out is None:
            raise OSError("the device has no interrupt endpoints")
        self._h = usbhost.open(d["id"])

    def read(self, timeout=100):
        return usbhost.read(self._h, self._in, REPORT, timeout)

    def write(self, report):
        return usbhost.write(self._h, self._out, bytes(report)[1:])   # [0] is the report ID 0

    def close(self):
        if self._h is not None:
            usbhost.close(self._h)
            self._h = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def open_board():
    try:
        return usbhid.HID(vid=VID, pid=PID)                # firmware with the HID class
    except OSError:
        return VendorDevice(VID, PID)                       # vendor-specific firmware


def send(dev, *payload):
    buf = bytearray(REPORT + 1)    # buf[0] = report ID 0: not sent, the board gets 64 bytes
    for i, b in enumerate(payload):
        buf[1 + i] = b
    dev.write(bytes(buf))


def parse(r):
    temp = r[2] | r[3] << 8
    if temp >= 0x8000:
        temp -= 0x10000
    return {
        "button": r[0] != 0,
        "led": r[1] != 0,
        "temp": temp / 10,
        "counter": r[4] | r[5] << 8 | r[6] << 16 | r[7] << 24,
        "blink_ms": r[8] | r[9] << 8,
    }


def main():
    try:
        dev = open_board()
    except OSError:
        ui.message("The Black Pill HID demo board was not found.\n\n"
                   "Flash firmware/blackpill_hid and connect the board\n"
                   "to the dock or through a USB-C OTG adapter.", title="No device")
        return

    with dev:
        scr = ui.Screen("Black Pill HID", hint="A: press   Left/Right: blink period   B: exit")

        def set_blink(ms):
            send(dev, CMD_BLINK, ms & 0xFF, ms >> 8)

        form = ui.Grid(spacing=32, row_spacing=16)
        rows = [("KEY button", 16), ("LED", 16), ("Chip temperature", 16), ("Reports", 16)]
        values = []
        for r, (name, chars) in enumerate(rows):
            form.add(ui.Label(name, color=ui.MUTED), r, 0)
            values.append(form.add(ui.Label("-", w=ui.CHAR_W * chars), r, 1))
        button, led, temp, rate = values
        form.add(ui.Label("Blink period, ms", color=ui.MUTED), 4, 0)
        blink = form.add(ui.Slider(value=0, maximum=1000, step=50, on_change=set_blink), 4, 1)
        form.set_column_stretch(1, 1)

        buttons = ui.HBox(spacing=24)
        buttons.add(ui.Button("LED on", on_click=lambda: send(dev, CMD_LED, 1)))
        buttons.add(ui.Button("LED off", on_click=lambda: send(dev, CMD_LED, 0)))
        buttons.add(ui.Button("Blink 200 ms", on_click=lambda: blink.set(200)))
        buttons.add_stretch()

        status = ui.Label("VID %04x PID %04x" % (dev.vid, dev.pid), color=ui.MUTED)
        root = ui.VBox(spacing=36)
        root.add(form)
        root.add(buttons)
        root.add_stretch()
        root.add(status)
        scr.set_layout(root)

        state = {"pressed": False, "t0": switch.ticks_ms(), "c0": None}

        def update():
            last = None
            for _ in range(4):                  # reports come every 10 ms, frames every ~16 ms
                r = dev.read(timeout=0)
                if not r:
                    break
                last = r
            if last is None or len(last) < 10:
                return
            s = parse(last)

            button.set_text("● pressed" if s["button"] else "○ released",
                            ui.ACCENT if s["button"] else ui.TEXT)
            if s["button"] and not state["pressed"]:
                switch.rumble(0.5, 40)
            state["pressed"] = s["button"]
            led.set_text("blinking" if s["blink_ms"] else ("on" if s["led"] else "off"))
            temp.set_text("%.1f °C" % s["temp"])

            if s["blink_ms"] != blink.value and not blink.focused:
                blink.value = s["blink_ms"]     # LED on/off stops blinking on the board
                blink.invalidate()

            now = switch.ticks_ms()
            if state["c0"] is None:
                state["t0"], state["c0"] = now, s["counter"]
            elif now - state["t0"] >= 1000:
                rate.set_text("%d / s" % ((s["counter"] - state["c0"]) * 1000 // (now - state["t0"])))
                state["t0"], state["c0"] = now, s["counter"]

        scr.update = update
        try:
            scr.run()
        finally:
            send(dev, CMD_LED, 0)


main()