"""USB-Serial for nxtest: a "COM port" over USB.

Supported:
  * the standard CDC-ACM class: ESP32-C3/S2/S3 (native USB), STM32 with USB CDC,
    RP2040, original Arduino Uno/Mega (16U2 chip), Leonardo/Micro, etc.;
  * the CH340/CH341 chip: Arduino clones and cheap USB-UART adapters.

Example:
    from usbserial import Serial
    with Serial(baudrate=115200) as port:
        port.write("hello\\n")
        print(port.readline(timeout=1000))
"""
import usbhost
import switch

CLASS_COMM = 0x02
SUBCLASS_ACM = 0x02
CLASS_DATA = 0x0A

SET_LINE_CODING = 0x20
SET_CONTROL_LINE_STATE = 0x22

# Arduino boards with auto-reset: they reboot when the port is opened
_ARDUINO_VIDS = (0x2341, 0x2A03)

# CH340/CH341 (protocol as in the Linux ch341.c driver)
CH340_IDS = ((0x1A86, 0x7523), (0x1A86, 0x7522), (0x1A86, 0x5523))
_CH_REQ_READ_VERSION = 0x5F
_CH_REQ_WRITE_REG = 0x9A
_CH_REQ_SERIAL_INIT = 0xA1
_CH_REQ_MODEM_CTRL = 0xA4
_CH_REG_PRESCALER = 0x12
_CH_REG_DIVISOR = 0x13
_CH_REG_LCR = 0x18
_CH_REG_LCR2 = 0x25
_CH_BIT_DTR = 1 << 5
_CH_BIT_RTS = 1 << 6
_CH_CLKRATE = 48000000


def _ch340_divisor(speed):
    """Divisor register value for the given speed (algorithm from ch341.c)."""
    def clk_div(ps, fact):
        return 1 << (12 - 3 * ps - fact)

    speed = max(47, min(speed, 3000000))
    fact = 1
    ps = 3
    while ps >= 0:
        if speed > _CH_CLKRATE // (clk_div(ps, 1) * 512):
            break
        ps -= 1
    if ps < 0:
        raise ValueError("unsupported baudrate")
    cd = clk_div(ps, fact)
    div = _CH_CLKRATE // (cd * speed)
    if div < 9 or div > 255:
        div //= 2
        cd *= 2
        fact = 0
    if div < 2:
        raise ValueError("unsupported baudrate")
    # Take the next divisor if it gives a speed closer to the requested one
    if 16 * _CH_CLKRATE // (cd * div) - 16 * speed >= 16 * speed - 16 * _CH_CLKRATE // (cd * (div + 1)):
        div += 1
    if fact == 1 and div % 2 == 0:
        div //= 2
        fact = 0
    return ((0x100 - div) << 8) | (fact << 2) | ps


def _same_device(a, b):
    return a["bus"] == b["bus"] and a["dev"] == b["dev"]


def ports():
    """Found USB-Serial devices: [{'vid', 'pid', 'kind', 'comm', 'data'}, ...].
    kind is "cdc" or "ch340"; comm and data are entries from usbhost.devices()
    (CH340 has a single interface, comm = None)."""
    devs = usbhost.devices()
    result = []
    for d in devs:
        if (d["vid"], d["pid"]) in CH340_IDS:
            result.append({"vid": d["vid"], "pid": d["pid"], "kind": "ch340", "comm": None, "data": d})
    for comm in devs:
        if comm["cls"] != CLASS_COMM or comm["subcls"] != SUBCLASS_ACM:
            continue
        # Data interface of the same device, closest by number (usually the next one)
        data = None
        for d in devs:
            if d["cls"] == CLASS_DATA and _same_device(d, comm):
                if data is None or abs(d["iface"] - comm["iface"]) < abs(data["iface"] - comm["iface"]):
                    data = d
        if data is not None:
            result.append({"vid": comm["vid"], "pid": comm["pid"], "kind": "cdc",
                           "comm": comm, "data": data})
    return result


class Serial:
    """Opens a USB-Serial device.

    vid, pid  - vendor/product filter (None matches any)
    index     - which one of the matching devices (if there are several)
    baudrate  - speed; usually irrelevant for devices with native USB
    reset_wait_ms - delay after opening; defaults to 2000 for Arduino and CH340
                    (Arduino boards reboot when the port is opened), otherwise 0
    """

    def __init__(self, vid=None, pid=None, index=0, baudrate=115200,
                 dtr=True, rts=False, reset_wait_ms=None):
        found = [p for p in ports()
                 if (vid is None or p["vid"] == vid) and (pid is None or p["pid"] == pid)]
        if len(found) <= index:
            raise OSError("USB serial device not found")
        p = found[index]
        self.vid = p["vid"]
        self.pid = p["pid"]
        self.kind = p["kind"]
        self._comm_iface = p["comm"]["iface"] if p["comm"] else 0
        self._ch_version = 0
        self._comm = None
        self._data = None
        self._rx = b""

        self._ep_in = None
        self._ep_out = None
        for addr, typ, size in p["data"]["eps"]:
            if typ == usbhost.BULK:
                if addr & 0x80:
                    self._ep_in = addr
                else:
                    self._ep_out = addr
        if self._ep_in is None or self._ep_out is None:
            raise OSError("USB serial device has no bulk endpoints")

        try:
            if self.kind == "cdc":
                self._comm = usbhost.open(p["comm"]["id"])
            self._data = usbhost.open(p["data"]["id"])
            if self.kind == "ch340":
                self._ch340_init()
            self.set_baudrate(baudrate)
            self.set_lines(dtr, rts)
        except BaseException:
            self.close()
            raise

        if reset_wait_ms is None:
            reset_wait_ms = 2000 if (self.vid in _ARDUINO_VIDS or self.kind == "ch340") else 0
        if reset_wait_ms:
            switch.sleep_ms(reset_wait_ms)

    # ---------- settings ----------

    def _ch340_init(self):
        version = usbhost.ctrl(self._data, 0xC0, _CH_REQ_READ_VERSION, 0, 0, 2)
        self._ch_version = version[0] if version else 0
        usbhost.ctrl(self._data, 0x40, _CH_REQ_SERIAL_INIT, 0, 0, b"")

    def _ch340_set_baudrate(self, baudrate, databits, parity, stopbits):
        val = _ch340_divisor(int(baudrate))
        # Without bit 7 the chip buffers data until a full 32-byte packet
        if self._ch_version > 0x27:
            val |= 0x80
        usbhost.ctrl(self._data, 0x40, _CH_REQ_WRITE_REG,
                     (_CH_REG_DIVISOR << 8) | _CH_REG_PRESCALER, val, b"")
        if self._ch_version >= 0x30:
            lcr = 0xC0 | (databits - 5)          # RX and TX enabled + word length
            if parity:
                lcr |= 0x08 | (0x10 if parity == 2 else 0)
            if stopbits == 2:
                lcr |= 0x04
            usbhost.ctrl(self._data, 0x40, _CH_REQ_WRITE_REG,
                         (_CH_REG_LCR2 << 8) | _CH_REG_LCR, lcr, b"")

    def set_baudrate(self, baudrate, databits=8, parity=0, stopbits=0):
        """parity: 0 none, 1 odd, 2 even; stopbits: 0 - 1 bit, 2 - 2 bits."""
        if self.kind == "ch340":
            self._ch340_set_baudrate(baudrate, databits, parity, stopbits)
            return
        b = int(baudrate)
        coding = bytes([b & 0xFF, (b >> 8) & 0xFF, (b >> 16) & 0xFF, (b >> 24) & 0xFF,
                        stopbits, parity, databits])
        try:
            usbhost.ctrl(self._comm, 0x21, SET_LINE_CODING, 0, self._comm_iface, coding)
        except OSError:
            pass  # some devices with native USB do not need a baud rate

    def set_lines(self, dtr=True, rts=False):
        """Control lines. Many devices treat DTR=1 as "port open".
        On Arduino boards toggling DTR reboots the board."""
        if self.kind == "ch340":
            ctl = (_CH_BIT_DTR if dtr else 0) | (_CH_BIT_RTS if rts else 0)
            usbhost.ctrl(self._data, 0x40, _CH_REQ_MODEM_CTRL, (~ctl) & 0xFFFF, 0, b"")
            return
        value = (1 if dtr else 0) | (2 if rts else 0)
        usbhost.ctrl(self._comm, 0x21, SET_CONTROL_LINE_STATE, value, self._comm_iface, b"")

    # ---------- data transfer ----------

    def write(self, data, timeout=1000):
        """Send str or bytes. Returns the number of bytes sent."""
        if isinstance(data, str):
            data = data.encode()
        return usbhost.write(self._data, self._ep_out, data, timeout)

    def read(self, size=512, timeout=100):
        """Up to size bytes; b"" if nothing arrived within timeout ms."""
        if self._rx:
            chunk, self._rx = self._rx[:size], self._rx[size:]
            return chunk
        chunk = usbhost.read(self._data, self._ep_in, 512, timeout)
        if not chunk:
            return b""
        if len(chunk) > size:
            self._rx = chunk[size:]
            chunk = chunk[:size]
        return chunk

    def readline(self, timeout=1000):
        """A line without '\\r\\n', or None if no complete line arrived within timeout ms."""
        deadline = switch.ticks_ms() + timeout
        while True:
            i = self._rx.find(b"\n")
            if i >= 0:
                line = self._rx[:i]
                self._rx = self._rx[i + 1:]
                if line.endswith(b"\r"):
                    line = line[:-1]
                try:
                    return line.decode()
                except Exception:
                    return str(line)
            left = deadline - switch.ticks_ms()
            if left <= 0:
                return None
            chunk = usbhost.read(self._data, self._ep_in, 512, min(left, 100))
            if chunk:
                self._rx += chunk

    def flush_input(self):
        """Discard everything that has arrived but has not been read."""
        self._rx = b""
        while usbhost.read(self._data, self._ep_in, 512, 0):
            pass

    # ---------- closing ----------

    def close(self):
        for h in (self._data, self._comm):
            if h is not None:
                try:
                    usbhost.close(h)
                except OSError:
                    pass
        self._data = None
        self._comm = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
