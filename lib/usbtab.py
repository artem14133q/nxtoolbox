"""usbtab - the "USB" tab of the launcher: connected USB interfaces and their
endpoints (from the built-in usbhost module), drawn as a tree.

    import usbtab
    page = usbtab.UsbTab()
    scr.add_tab("USB", page.layout, update=page.update, on_key=page.key, hint="Y: refresh")

Devices already open or used by the system (official controllers etc.) are not listed,
see usbhost.devices(). Refreshed once per second; Y refreshes right away.
"""
import switch
import ui

try:
    import usbhost
except ImportError:
    usbhost = None

REFRESH_MS = 1000
LIST_W = 760

TYPES = {0: "control", 1: "iso", 2: "bulk", 3: "interrupt"}
CLASSES = {
    0x01: "audio", 0x02: "CDC comm (serial)", 0x03: "HID", 0x07: "printer",
    0x08: "mass storage", 0x0A: "CDC data (serial)", 0x0E: "video", 0xFF: "vendor-specific",
}


def _tree_lines(devices):
    """Text lines of a tree: device -> interfaces -> endpoints. Interfaces are grouped
    by (bus, dev) in the order usbhost.devices() returned them."""
    groups = []
    by_key = {}
    for d in devices:
        key = (d["bus"], d["dev"])
        group = by_key.get(key)
        if group is None:
            group = by_key[key] = []
            groups.append((key, group))
        group.append(d)

    lines = []
    for gi, ((bus, dev), ifaces) in enumerate(groups):
        vid, pid = ifaces[0]["vid"], ifaces[0]["pid"]
        lines.append("USB %04x:%04x  bus %d dev %d" % (vid, pid, bus, dev))
        for ii, iface in enumerate(ifaces):
            last_iface = ii == len(ifaces) - 1
            cls_name = CLASSES.get(iface["cls"], "0x%02x" % iface["cls"])
            lines.append("%sInterface %d  %02x/%02x/%02x (%s)" % (
                "└─ " if last_iface else "├─ ", iface["iface"],
                iface["cls"], iface["subcls"], iface["proto"], cls_name))
            prefix = "   " if last_iface else "│  "
            eps = iface["eps"]
            for ei, (addr, typ, size) in enumerate(eps):
                lines.append("%s%sep 0x%02x  %-3s  %-9s  %d bytes" % (
                    prefix, "└─ " if ei == len(eps) - 1 else "├─ ", addr,
                    "IN" if addr & 0x80 else "OUT", TYPES.get(typ, "?"), size))
        if gi != len(groups) - 1:
            lines.append("")
    return lines


class UsbTab:
    def __init__(self):
        self._next = 0
        self._devices = None

        self.list = ui.ListBox(rows=8, w=LIST_W)
        self.status = ui.Label("", color=ui.MUTED)

        root = ui.VBox(spacing=12)
        root.add(ui.Label("Connected USB interfaces", color=ui.ACCENT))
        root.add(self.list, stretch=1)
        root.add(self.status)
        self.layout = root

        self.refresh()

    # ---------- tab hooks ----------

    def update(self):
        now = switch.ticks_ms()
        if now < self._next:
            return
        self._next = now + REFRESH_MS
        self.refresh()

    def key(self, down):
        if down & switch.Y:
            self._next = 0
            self.refresh()
            return True
        return False

    # ---------- data ----------

    def refresh(self):
        if usbhost is None:
            self.list.set_items(["usbhost module is not available"])
            self.status.set_text("")
            return
        try:
            devices = usbhost.devices()
        except OSError as e:
            self.list.set_items(["Error: %s" % e])
            self.status.set_text("")
            return
        if devices == self._devices:
            return
        self._devices = devices
        if not devices:
            self.list.set_items(["No available USB interfaces."])
            self.status.set_text("Devices used by the system itself are not listed")
            return
        self.list.set_items(_tree_lines(devices))
        self.status.set_text("%d interface(s)" % len(devices))
