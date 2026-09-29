"""systab - the "System" tab of the launcher: information about the console.

    import systab
    page = systab.SystemTab()
    scr.add_tab("System", page.layout, update=page.update, on_key=page.key)

Values are refreshed once per second. Y shows/hides the serial number.
"""
import switch
import ui
import sysinfo

REFRESH_MS = 1000
KEY_W = 112                     # width of the name column (small font)
VALUE_CHARS = 16                # width of the value column in characters
NA = "n/a"

CHARGER = {0: "not connected", 1: "connected", 2: "low power", 3: "not supported"}
NET = {0: "not connected", 1: "Wi-Fi", 2: "Ethernet"}


def _gb(n):
    return "%.1f" % (n / 1073741824)


def _space(free, total):
    if free is None or total is None:
        return NA
    return "%s of %s GB" % (_gb(free), _gb(total))


def _temp(v):
    return NA if v is None else "%.1f °C" % v


def _mhz(v):
    return NA if v is None else "%d MHz" % v


def _uptime(s):
    if s is None:
        return NA
    h, m = s // 3600, s // 60 % 60
    return "%d h %d min" % (h, m) if h else "%d min" % m


def _yes_no(v, yes, no):
    return NA if v is None else (yes if v else no)


def _cut(text):
    return text if len(text) <= VALUE_CHARS else text[:VALUE_CHARS - 1] + "~"


class SystemTab:
    def __init__(self):
        self.show_serial = False
        self._next = 0
        self._info = None
        self.values = {}                # field name -> value Label

        columns = [
            [("Console", [("model", "Model"), ("serial", "Serial"), ("nickname", "Name"),
                          ("region", "Region"), ("language", "Language"), ("mode", "Mode")]),
             ("Firmware", [("firmware", "System"), ("atmosphere", "Atmosphere"),
                           ("storage_type", "Storage"), ("unit", "Unit")])],
            [("Power", [("battery", "Battery"), ("health", "Health"), ("charger", "Charger"),
                        ("performance", "Performance")]),
             ("Thermal", [("temp_soc", "SoC"), ("temp_pcb", "Board"), ("fan", "Fan")]),
             ("Clocks", [("cpu", "CPU"), ("gpu", "GPU"), ("mem", "Memory")])],
            [("Storage", [("sd", "SD card"), ("nand", "Internal"), ("ram", "App memory")]),
             ("Network", [("net", "Connection"), ("signal", "Signal"), ("online", "Internet"),
                          ("ip", "IP address")]),
             ("Time", [("date", "Date"), ("time", "Time"), ("uptime", "Uptime")])],
        ]

        root = ui.HBox(spacing=40)
        for sections in columns:
            col = ui.VBox(spacing=12)
            for title, rows in sections:
                col.add(ui.Label(title, color=ui.ACCENT))
                grid = col.add(ui.Grid(spacing=12, row_spacing=2))
                for r, (field, name) in enumerate(rows):
                    grid.add(ui.Label(name, color=ui.MUTED, scale=1, w=KEY_W), r, 0)
                    self.values[field] = grid.add(ui.Label("", w=ui.CHAR_W * VALUE_CHARS), r, 1)
            col.add_stretch()
            root.add(col, stretch=1)
        self.layout = root

    # ---------- tab hooks ----------

    def update(self):
        now = switch.ticks_ms()
        if now < self._next:
            return
        self._next = now + REFRESH_MS
        try:
            self._info = sysinfo.read()
        except Exception as e:
            self._info = None
            self._set("model", "error: %s" % e)
            return
        self._show(self._info)

    def key(self, down):
        if down & switch.Y:
            self.show_serial = not self.show_serial
            if self._info:
                self._show(self._info)
            return True
        return False

    # ---------- formatting ----------

    def _set(self, field, text):
        label = self.values[field]
        text = _cut(text if text else NA)
        if label.text != text:
            label.set_text(text)

    def _show(self, i):
        serial = i["serial"]
        if serial and not self.show_serial:
            serial = serial[:4] + "•" * 6 + " (Y)"   # hidden by default, Y shows it
        self._set("model", i["model"])
        self._set("serial", serial)
        self._set("nickname", i["nickname"])
        self._set("region", i["region"])
        self._set("language", i["language"])
        self._set("mode", _yes_no(i["docked"], "docked", "handheld"))

        self._set("firmware", i["firmware"])
        self._set("atmosphere", i["atmosphere"] or "not detected")
        self._set("storage_type", _yes_no(i["emummc"], "emuMMC", "sysMMC"))
        self._set("unit", _yes_no(i["retail"], "retail", "development"))

        battery = i["battery"]
        charging = i["charger"] in (1, 2)
        self._set("battery", NA if battery is None else "%d %%%s" % (battery, " charging" if charging else ""))
        health = i["battery_health"]
        self._set("health", NA if health is None else "%.0f %%" % health)
        self._set("charger", NA if i["charger"] is None else CHARGER.get(i["charger"], "?"))
        self._set("performance", _yes_no(i["boost"], "boost", "normal"))

        self._set("temp_soc", _temp(i["temp_soc"]))
        self._set("temp_pcb", _temp(i["temp_pcb"]))
        self._set("fan", NA if i["fan"] is None else "%.0f %%" % i["fan"])

        self._set("cpu", _mhz(i["cpu_mhz"]))
        self._set("gpu", _mhz(i["gpu_mhz"]))
        self._set("mem", _mhz(i["mem_mhz"]))

        self._set("sd", _space(i["sd_free"], i["sd_total"]))
        self._set("nand", _space(i["nand_free"], i["nand_total"]))
        used, total = i["ram_used"], i["ram_total"]
        self._set("ram", NA if used is None or total is None
        else "%d of %d MB" % (used // 1048576, total // 1048576))

        net = i["net_type"]
        self._set("net", NA if net is None else NET.get(net, "?"))
        bars = i["wifi_bars"]
        self._set("signal", "●" * bars + "○" * (3 - bars)
        if net == 1 and bars is not None else NA)
        self._set("online", _yes_no(i["online"], "yes", "no"))
        self._set("ip", i["ip"])

        self._set("date", i["date"])
        self._set("time", i["time"])
        self._set("uptime", _uptime(i["uptime"]))