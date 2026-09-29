"""docs_tab - the "Docs" tab of the launcher: a short guide plus a module API
reference, in one tab with a page list on the left (like a small docs site) instead of
two separate tabs to scroll through - written in Markdown, rendered with
lib/markdown.py + lib/textview.py.

    import docs_tab
    page = docs_tab.DocsTab()
    scr.add_tab("Docs", page.layout, hint="A: open page   Up/Down or drag: scroll")
"""
import ui
import markdown
import textview

SIDEBAR_W = 270

GUIDE = """
# NXToolBox

A launcher and MicroPython runtime for the Nintendo Switch: run, edit and manage
scripts on the console, or from a computer with send.py - see the Files tab for the
network address and password.

## Controls

- D-pad: move, A: open / run, B: back, L / R: switch tabs
- ZR: edit the selected script, ZL: new script, Y: refresh (or a tab's own shortcut)
- Touch works everywhere too; drag a finger to scroll a list

## Tabs

- **Files** - scripts as tiles. A opens a folder or runs a script, X deletes it,
  ZR edits it. "Get scripts..." installs more from GitHub or a catalog.
- **System** - console model, firmware, battery, storage, network, date and time.
- **USB** - USB interfaces the console is not using itself, as a tree with their
  endpoints (keyboards, serial adapters, vendor-specific devices, ...).
- **USB Drive** - browse a FAT12/16/32 USB flash drive and copy files onto the SD
  card, into /switch/NXToolBox/downloads.
- **Settings** - pick a theme (light, dark, ...) and adjust corner rounding.
- **Docs** - this page: pick a topic on the left.
- **About** - version and credits.

## The editor

ZR on a script opens it on the console: syntax highlighting, line numbers,
auto-indent, undo. F5 runs it full screen and shows the output; errors jump to
their line.

## From a computer

```
python3 send.py upload myscript.py
python3 send.py run myscript.py
```

Uploading launcher.py or lib/ui.py restarts the launcher right away, so quick
changes to the app itself show up without rebuilding it.

## Stopping a script

Press + and - together on the console (or Ctrl+C from a computer) to stop
whatever is running and come back here.
"""

SWITCH = """
# switch

Buttons, sticks, touch, rumble, timing. Every function here also has a full
docstring in `stubs/switch.pyi`, read by your editor for autocomplete.

- `switch.buttons()` / `buttons_down()` - bitmask held / newly pressed: A, B, X, Y,
  L, R, ZL, ZR, PLUS, MINUS, UP, DOWN, LEFT, RIGHT, LSTICK, RSTICK
- `switch.stick(index)` - `(x, y)` from -1.0 to 1.0, 0 is the left stick
- `switch.touches()` - `[(x, y), ...]`, handheld mode only
- `switch.rumble(amp, ms=0, low=160, high=320)`
- `switch.battery()`, `switch.ticks_ms()`, `switch.sleep_ms(ms)`
- `switch.running()` - call every loop; False means the app should exit
- `switch.keyboard(text, prompt)` - the on-screen keyboard, returns str or None

```
import switch
while switch.running():
    if switch.buttons_down() & switch.A:
        switch.rumble(0.6, 120)
```

| Constant | Where | Constant | Where |
| --- | --- | --- | --- |
| `A` `B` `X` `Y` | face buttons | `L` `R` `ZL` `ZR` | shoulder / triggers |
| `PLUS` `MINUS` | `+` / `-` | `LSTICK` `RSTICK` | stick clicks |
| `UP` `DOWN` `LEFT` `RIGHT` | D-pad | | |

> Combine several with `|`: `switch.PLUS | switch.MINUS` is the panic combo that stops
> a stuck script - the console always reads it from real hardware, so it works even if
> a script (or `send.py input`, see the nxapp page) has the buttons in a strange state.
"""

GFX = """
# gfx

1280x720 graphics; the first drawing call switches to graphics mode.

- `gfx.clear(color=BLACK)`, `gfx.present()` - show the frame, waits for ~60 fps
- `gfx.rgb(r, g, b, a=255)` and the BLACK / WHITE / RED / GREEN / BLUE / ... constants
- `gfx.pixel`, `gfx.line`, `gfx.rect`, `gfx.fill_rect`, `gfx.circle`, `gfx.fill_circle`
- `gfx.fill_gradient(x, y, w, h, color1, color2, vertical=True)`
- `gfx.text(x, y, text, color, scale)` -> width; `gfx.text_width(text, scale)`
- `gfx.blit(x, y, w, h, rgba_bytes)` - draw an image (image.load() decodes one)
"""

UI_MOD = """
# ui, tabs, tiles

A small GUI toolkit built on gfx, with Qt-like layouts (`VBox`, `HBox`, `Grid`).

- `ui.Screen(title, hint, on_back, on_key).run()` - a screen with an event loop
- Widgets: `Label`, `Button`, `Checkbox`, `Slider`, `ProgressBar`, `ListBox`
- `ui.message(text)`, `ui.confirm(text)`, `ui.choose(title, items)` - quick dialogs
- `tabs.TabScreen` - a Screen with tabs switched by L/R (`add_tab(title, layout, ...)`)
- `tiles.TileGrid` - a grid of icon tiles, used by the Files tab

See `lib/ui.py`'s own docstring for the complete widget and layout reference.
"""

USBHOST = """
# usbhost, usbserial, usbhid

Low-level and convenience access to USB devices the system is not using itself.

- `usbhost.devices()` - available interfaces; `open(id)`, `close(handle)`
- `usbhost.ctrl/read/write(handle, ...)` - control and bulk/interrupt transfers
- `usbserial.Serial(vid=None, pid=None, baudrate=115200)` - CDC-ACM or CH340 serial
- `usbhid.HID(vid=None, pid=None)` - raw HID reports, `.read(timeout)` / `.write(data)`

```
from usbserial import Serial
with Serial(baudrate=115200) as port:
    port.write("hello\\n")
    print(port.readline(timeout=1000))
```
"""

USBMSC = """
# usbmsc, fat

Block-level, read-only access to a USB flash drive (also not claimed by the system).

- `usbmsc.drives()` - mass storage interfaces; `usbmsc.Drive(info)` opens one
- `drive.read_blocks(lba, count)`, `.block_size`, `.block_count`
- `fat.mount(drive)` -> `FatVolume` (FAT12/16/32, auto-detects an MBR partition)
- `vol.listdir(path)` -> `[{"name", "dir", "size"}, ...]`; `vol.open(path)` -> file
"""

SYSINFO = """
# sysinfo

- `sysinfo.read()` -> dict: model, serial, firmware, atmosphere, battery,
  battery_health, temp_soc, temp_pcb, cpu_mhz, gpu_mhz, sd_free, sd_total, net_type,
  online, ip, date, time, uptime, ... (None for anything unavailable)
"""

NET = """
# requests, installer

- `requests.get/post(url, ...)`, `requests.download(url, path)` - HTTPS via libcurl
- `installer.install_url(github_url)` - install scripts from a GitHub repo or folder
"""

LOWLEVEL = """
# image, font, draw

Lower-level modules the GUI itself is built on.

- `image.load(path, max_w=0, max_h=0, bg=None)` -> `(w, h, rgba)` for `gfx.blit()`
- `font.load(path)` -> font id; `font.text(font, x, y, text, color, size)` - smooth
  TrueType text, antialiased
- `draw.rect(x, y, w, h, color, radius=0, border=None)` - alpha-blended rounded
  rectangles (unlike `gfx.fill_rect`, transparent colors really blend)
"""

NXAPP = """
# nxapp

Talks to the launcher itself: `nxapp.run(path)`, `nxapp.quit()`, `nxapp.restart()`,
`nxapp.info()` -> `{"ip", "port", "password", "network"}`.

`send.py screenshot` and `send.py input` (buttons, taps, swipes - for automated
testing) only work while something calls `nxapp.poll()` every frame, which only the
real Launcher does automatically; a plain `ui.Screen` needs to do it itself:

```
scr.update = nxapp.poll
```
"""

PAGES = [
    ("Guide", GUIDE),
    ("switch", SWITCH),
    ("gfx", GFX),
    ("ui, tabs, tiles", UI_MOD),
    ("USB devices", USBHOST),
    ("usbmsc, fat", USBMSC),
    ("sysinfo", SYSINFO),
    ("requests, installer", NET),
    ("image, font, draw", LOWLEVEL),
    ("nxapp", NXAPP),
]


class DocsTab:
    def __init__(self):
        self.list = ui.ListBox([title for title, _ in PAGES], rows=len(PAGES),
                               w=SIDEBAR_W, on_select=self._select)
        self.content = textview.TextView(markdown.parse(PAGES[0][1]), rows=14, w=900)
        root = ui.HBox(spacing=16)
        root.add(self.list)
        root.add(self.content, stretch=1)
        self.layout = root

    def _select(self, index, _title):
        self.content.set_blocks(markdown.parse(PAGES[index][1]))
