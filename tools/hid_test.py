#!/usr/bin/env python3
"""Checks the Black Pill demo firmware from the computer (firmware/blackpill_hid).

Works with both builds of the firmware:
  * vendor-specific interface (class 0xFF, the one the Switch can use):
        brew install libusb && pip install pyusb
  * HID interface:
        pip install hidapi

    python3 tools/hid_test.py

Prints the reports from the board for a few seconds and blinks its LED.
Press the KEY button on the board to see the button value change.
"""
import sys
import time

VID, PID = 0x0483, 0x5750
REPORT = 64
CMD_LED, CMD_BLINK = 1, 2


class HidBoard:
    """The board as a HID device (hidapi)."""

    def __init__(self):
        import hid
        if not hid.enumerate(VID, PID):
            raise LookupError
        self.dev = hid.device()
        self.dev.open(VID, PID)
        self.kind = "HID (hidapi)"

    def write(self, report):
        self.dev.write(b"\x00" + report)          # leading 0 = no report ID

    def read(self, timeout_ms):
        return bytes(self.dev.read(REPORT, timeout_ms))

    def close(self):
        self.dev.close()


class VendorBoard:
    """The board with a vendor-specific interface (libusb via pyusb)."""

    def __init__(self):
        import usb.core
        import usb.util
        self.core = usb.core
        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is None:
            raise LookupError
        dev.set_configuration()
        intf = dev.get_active_configuration()[(0, 0)]
        self.ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        self.dev = dev
        self.kind = "vendor-specific (libusb), class 0x%02x" % intf.bInterfaceClass

    def write(self, report):
        self.ep_out.write(report)

    def read(self, timeout_ms):
        try:
            return bytes(self.ep_in.read(REPORT, timeout_ms))
        except self.core.USBTimeoutError:
            return b""

    def close(self):
        import usb.util
        usb.util.dispose_resources(self.dev)


def open_board():
    errors = []
    for cls in (VendorBoard, HidBoard):
        try:
            return cls()
        except ImportError as e:
            errors.append("%s: missing package (%s)" % (cls.__name__, e.name))
        except LookupError:
            errors.append("%s: not found" % cls.__name__)
        except Exception as e:                       # e.g. libusb backend not installed
            errors.append("%s: %s" % (cls.__name__, e))
    sys.exit("no device %04x:%04x\n  " % (VID, PID) + "\n  ".join(errors))


def send(board, *payload):
    board.write(bytes(payload) + bytes(REPORT - len(payload)))


def parse(r):
    temp = r[2] | r[3] << 8
    if temp >= 0x8000:
        temp -= 0x10000
    return {
        "button": bool(r[0]),
        "led": bool(r[1]),
        "temp": temp / 10,
        "counter": r[4] | r[5] << 8 | r[6] << 16 | r[7] << 24,
        "blink_ms": r[8] | r[9] << 8,
    }


def main():
    board = open_board()
    print("found:", board.kind)
    try:
        print("blinking every 200 ms...")
        send(board, CMD_BLINK, 200 & 0xFF, 200 >> 8)
        start = time.time()
        first = last = None
        while time.time() - start < 5:
            data = board.read(100)
            if len(data) < 10:
                continue
            state = parse(data)
            if first is None:
                first = (time.time(), state["counter"])
            last = (time.time(), state["counter"])
            print("\rbutton %-5s led %-5s temp %5.1f C  counter %8d  blink %4d ms" % (
                state["button"], state["led"], state["temp"], state["counter"], state["blink_ms"]),
                  end="", flush=True)
        print()
        if first and last and last[0] > first[0]:
            print("report rate: %.0f per second" % ((last[1] - first[1]) / (last[0] - first[0])))
        send(board, CMD_LED, 0)
        print("LED off. Done.")
    finally:
        board.close()


if __name__ == "__main__":
    main()