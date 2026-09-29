# NXToolBox

**English** | [Русский](README.ru.md)

A Python toolbox for the Nintendo Switch (homebrew, Atmosphere). NXToolBox runs
MicroPython scripts on the console and gives them access to the hardware: buttons,
sticks, touch screen, rumble, 1280x720 graphics, files, the network, serial ports and
other USB devices, and a USB keyboard and mouse. Scripts are started from a
touch-friendly start screen on the console, edited in a built-in editor, or sent from a
computer with their output shown live in the terminal.

## Features

- **Start screen** written in Python: scripts as tiles with icons, a **System** tab with
  console information, a **USB** tab with connected USB interfaces as a tree, a
  **USB Drive** tab that browses a FAT-formatted flash drive and copies files onto the SD
  card, a **Settings** tab, a **Docs** tab (guide and module reference, rendered from
  Markdown, with a page list on the left) and an **About** tab, tabs switched with L and
  R. Patch it without rebuilding the app.
- **Themes**: dark and light (JetBrains colors) or your own ini files; smooth rounded
  corners with an adjustable radius.
- **Script editor** on the console: syntax highlighting, line numbers, auto-indent, undo,
  run with F5 and see the output in a panel on the right; errors jump to their line.
- **Remote run and upload** from Windows, macOS or Linux (`send.py`, no dependencies),
  with live output and Ctrl+C to stop.
- **Get scripts**: install scripts from GitHub, any URL, or script catalogs.
- **Online updates** of the start screen and libraries from your repository.
- **Stop any script**: `+` and `-` together on the console, Ctrl+C on the computer, or HOME.
- **Password protection** (HMAC-SHA256 challenge-response; the password never crosses the network).
- **Script API**: hardware (`switch`), graphics (`gfx`, `image`), GUI with Qt-like layouts
  (`ui`, `tabs`), USB keyboard and mouse (`keys`), HTTP(S) (`requests`), serial ports and
  USB devices (`usbserial`, `usbhid`, `usbhost`), USB flash drives (`usbmsc`, `fat`),
  console information (`sysinfo`), files and
  `import`.

## Contents

- [Requirements](#requirements)
- [Building](#building)
- [First start](#first-start)
- [Using NXToolBox](#using-nxtoolbox)
- [Running scripts from a computer](#running-scripts-from-a-computer)
- [Writing scripts](#writing-scripts)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Safety notes](#safety-notes)
- [Third-party software](#third-party-software)

## Requirements

- A Switch that runs homebrew with Atmosphere. Use emuMMC and stay offline with CFW.
- [devkitPro](https://devkitpro.org) with `switch-dev` and `switch-curl`
  (`sudo dkp-pacman -S switch-dev switch-curl`), `DEVKITPRO` set (usually `/opt/devkitpro`).
- [MicroPython](https://github.com/micropython/micropython) 1.20 or newer, cloned next to
  this project (`../micropython`) or anywhere else with `MICROPYTHON_DIR` set.
- Python 3.8+ on the computer.

## Building

### One-time setup

1. **stb_image** (raster image decoding for tile icons) and **nanosvg** (SVG icons) into
   `source/`:
   ```
   curl -L -o source/stb_image.h https://raw.githubusercontent.com/nothings/stb/master/stb_image.h
   curl -L -o source/nanosvg.h https://raw.githubusercontent.com/memononen/nanosvg/master/src/nanosvg.h
   curl -L -o source/nanosvgrast.h https://raw.githubusercontent.com/memononen/nanosvg/master/src/nanosvgrast.h
   ```
2. **cacert.pem** (trusted certificate authorities for HTTPS; the console's own store lacks
   some current root certificates) into the project root, from
   https://curl.se/docs/caextract.html. It is packed into the app and updated online.
3. **update_url.txt** (optional, enables online updates): one line with the raw URL of
   `update.json` in your repository, e.g.
   ```
   https://raw.githubusercontent.com/artem14133q/nxtoolbox/refs/heads/master/update.json
   ```
4. **Makefile**: copy the devkitPro template
   (`cp $DEVKITPRO/examples/switch/templates/application/Makefile .`) and change:
   ```make
   TARGET   := NXToolBox
   SOURCES  := source modules/switch micropython_embed/py micropython_embed/extmod micropython_embed/shared/runtime micropython_embed/port
   INCLUDES := source modules/switch micropython_embed
   LIBS     := -lcurl -lz -lnx -lm
   ROMFS    := romfs
   ```
   and make the build pack the Python files first:
   ```make
   $(BUILD): bundle
   	@[ -d $@ ] || mkdir -p $@
   	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

   .PHONY: bundle
   bundle:
   	@python3 tools/bundle.py
   ```

### Build

```
./gen.sh                  # MicroPython core; again after changing modules/ or mpconfigport.h
make clean && make        # -> NXToolBox.nro
```

After changes to `source/*.c` only, `make` is enough. After changes to Python files in
`app/` or `lib/`, `make` repacks them.

Copy `NXToolBox.nro` to `/switch/` on the SD card and start it from the homebrew menu,
preferably by holding R while launching a game: the app then gets more memory and the
system keyboard works.

## First start

- The app creates a password, shows it on the System tab and in the text menu, and saves
  it to `/switch/NXToolBox/password.txt` (delete the file to get a new one).
- The start screen and the libraries packed into the .nro are installed into
  `/switch/NXToolBox/sys/`. A newer build replaces them automatically; a version installed
  online is kept even if an older .nro is started later.

## Using NXToolBox

### Start screen

Three tabs under the title, switched with **L** and **R**:

- **Files**: scripts in `/switch/NXToolBox/scripts` as tiles; folders open, scripts run.
- **System**: model, serial number (Y shows it), firmware and Atmosphere version, emuMMC or
  sysMMC, battery charge and health, temperatures, fan, clocks, storage, network, time.
- **Settings**: the theme and the corner rounding (applied right away).

| Button | Files tab | While a script runs | After a script |
|---|---|---|---|
| D-pad / touch | select | | |
| A | open folder / run script | | |
| B | parent folder | | back to the start screen |
| ZR | edit the selected script | | |
| ZL | create a new script | | |
| Y | refresh | | |
| X | delete the selected file | | |
| L / R | switch tabs | | |
| + | exit the app | | |
| + and - together | | stop the script | |

**Get scripts...** (button on the Files tab) installs scripts from a GitHub file, folder
(`.../tree/BRANCH/folder`) or repository link, any direct link, or a script catalog.

If the start screen fails, the error is shown and the app falls back to a built-in text
menu; **X** there tries the start screen again. Hold **-** while starting the app to skip
the start screen.

### Tiles

A script describes its tile with a variable; the file is not executed to read it, only
literals are allowed:

```python
__NXTOOLBOX_MODULE__ = {
    "title": "Snake",
    "description": "Classic snake game",
    "icon": "snake.png",      # relative to the script: PNG, JPEG, BMP, GIF or SVG
    "version": "1.0",
}
```

Scripts without an icon get a colored letter; a folder shows its `icon.png` if it has one.

### Script editor

ZR opens the selected script, ZL creates a new one from a template.

- **F5** runs the text right in the editor: `print` goes to the output panel on the right,
  an error highlights its line and moves the cursor there.
- **Ctrl+F5** saves and runs the script full screen in a clean interpreter: use it for
  scripts with graphics, their own screens or USB devices, and after editing modules the
  script imports (F5 reuses already imported modules).
- USB keyboard: arrows, Home/End, PgUp/PgDn, Ctrl+S save, Ctrl+Z undo, Ctrl+plus/minus zoom,
  Esc close. The mouse places the cursor and scrolls.
- Joy-Con only: D-pad moves, A edits the line with the system keyboard, Y adds a line,
  X deletes it, ZR runs, ZL undoes, `+` saves, B closes.

### Themes

The built-in themes are **Dark** and **Light** (JetBrains New UI colors, including the
editor's syntax colors). A theme is an ini file; copy `themes/dark.ini` to
`/switch/NXToolBox/themes/<name>.ini`, change the colors you want (the rest come from the
dark theme) and choose it on the Settings tab:

```ini
[theme]
name = My theme
radius = 8

[colors]
accent = #E06C75

[editor]
keyword = #C678DD
```

The choice is stored in `/switch/NXToolBox/settings.ini` (`theme`, `radius`; radius 0 gives
square corners). Scripts use the same look through `ui`: `ui.ACCENT`, `ui.TEXT`...,
`ui.box(x, y, w, h, color)` for rounded panels and `ui.set_rounded(r)`.

### Script catalogs

A catalog is an `index.json` on any web server. Build one from a folder of scripts
(one subfolder or `.py` file per package, optional `nxtoolbox.json` with title, version,
description and main file):

```
python3 tools/make_catalog.py my-catalog --name "My scripts"
```

Host it on GitHub (`https://raw.githubusercontent.com/OWNER/REPO/main/index.json`) or
locally (`python3 -m http.server 8000` in the folder), then add its URL under
Get scripts -> Add a catalog. The Switch shows titles, versions and descriptions, installs
and updates packages and can run them right away.

### Online updates

Once per app start the start screen checks `update_url.txt` and offers newer versions of
the start screen, the libraries and `cacert.pem`. To publish an update: build (this
rewrites `update.json` with a version made from the newest modification time), then commit
and push `update.json`, `cacert.pem`, `app/launcher.py` and `lib/`.

### SD card layout

```
/switch/NXToolBox/
├── sys/            bundled launcher.py, lib/, themes/, cacert.pem, VERSION (managed by the app)
├── launcher.py     optional: your start screen, overrides sys/launcher.py
├── lib/            your modules, override sys/lib (quick patches without rebuilding)
├── scripts/        scripts shown on the start screen; working folder of a running script
├── themes/         your themes (<name>.ini)
├── settings.ini    selected theme and corner radius
├── catalogs.txt    script catalogs ("Name | URL" per line)
├── installed.json  installed catalog packages and their versions
└── password.txt    delete it to generate a new password
```

In scripts `/` is the SD card root (`sdmc:/` paths do not work).

## Running scripts from a computer

Set the address and the password once:

```
# macOS / Linux (~/.zshrc or ~/.bashrc)
export NXTOOLBOX_HOST=192.168.1.42
export NXTOOLBOX_PASSWORD=yourpassword

# Windows
setx NXTOOLBOX_HOST 192.168.1.42
setx NXTOOLBOX_PASSWORD yourpassword
```

Then (`py` instead of `python3` on Windows):

```
python3 send.py run examples/hwtest.py        # run and watch the output; Ctrl+C stops it
python3 send.py upload game.py                # -> /switch/NXToolBox/scripts
python3 send.py upload mylib --to lib         # modules for import
python3 send.py upload app/launcher.py --to . # quick patch of the start screen
python3 send.py screenshot -o shot.png        # save a PNG of whatever is on screen now
python3 send.py input button A --hold 100     # fake pressing A for 100 ms
python3 send.py input tap 640 360             # fake a touch at (640, 360)
python3 send.py input swipe 640 600 640 200   # fake a drag (e.g. to scroll a list)
python3 send.py input release                 # cancel any pending fake input right away
```

Uploading `launcher.py` or `lib/ui.py` restarts the start screen right away. Delete your
copies in `/switch/NXToolBox/` to go back to the bundled versions.

`screenshot` needs graphics mode to be active (the start screen or a script with a GUI) -
it reads the frame buffer directly in C, so it works no matter what the interpreter is
doing at that moment.

`input` fakes button presses and touches for automated testing: drive the UI with
`input`, capture the result with `screenshot`. It is layered on top of the real
buttons/touches (`switch.buttons()`, `switch.touches()`, ...), not a replacement for
them, so real input keeps working at the same time. The one exception on purpose: the
physical **+ and - together** panic combo that stops a stuck script always reads the
real hardware directly and cannot be faked over the network - a human at the console
can always regain control.

## Writing scripts

Full signatures and documentation are in `stubs/*.pyi` (IDE hints) and at the top of each
file in `lib/`.

### Hardware (`switch`)

```python
import switch

switch.buttons()            # held buttons: switch.buttons() & switch.A
switch.buttons_down()       # pressed since the previous call
switch.stick(0)             # (x, y) of the left stick, -1.0..1.0; 1 = right stick
switch.touches()            # [(x, y), ...] in handheld mode
switch.rumble(0.5, 300)     # strength, duration in ms (0 = until rumble(0))
switch.keyboard("", "Name") # system keyboard -> str or None
switch.battery()            # percent
switch.ticks_ms()           # milliseconds since power on
switch.sleep_ms(16)         # interruptible pause
switch.running()            # call in every loop; False when the app must exit
```

### Graphics (`gfx`, `image`)

```python
import gfx, image

while switch.running():
    gfx.clear(gfx.rgb(20, 24, 40))
    gfx.fill_circle(640, 360, 50, gfx.RED)
    gfx.text(20, 20, "Hello / Привет", gfx.WHITE, scale=2)
    w, h, rgba = image.load("logo.png", 256, 256)   # PNG/JPEG/BMP/GIF/SVG, scaled to fit
    gfx.blit(100, 100, w, h, rgba)
    gfx.present()                                   # show the frame, ~60 fps
```

The first drawing call switches the screen to graphics mode; when the script ends, the text
console comes back with everything the script printed.

### GUI (`ui`, `tabs`)

```python
import ui

scr = ui.Screen("Settings")
form = ui.Grid()
form.add(ui.Label("Volume"), 0, 0)
level = form.add(ui.Slider(value=30, maximum=100), 0, 1)
form.set_column_stretch(1, 1)

buttons = ui.HBox()
buttons.add(ui.Button("Save", on_click=lambda: ui.message("Saved: %d" % level.value)))
buttons.add_stretch()

root = ui.VBox()
root.add(form)
root.add(buttons)
root.add_stretch()
scr.set_layout(root)
scr.run()

ui.confirm("Delete the file?")            # True / False
ui.choose("Pick one", ["A", "B", "C"])    # index or None
```

Widgets: `Label`, `Button`, `Checkbox`, `Slider`, `ProgressBar`, `ListBox`, and `TileGrid`
(`lib/tiles.py`). Layouts: `VBox`, `HBox`, `Grid`, nested as needed. `tabs.TabScreen` adds
tabs switched with L and R. D-pad, A/B and touch work everywhere. Colors and rounding follow
the selected theme; `ui.box()` and `ui.circle()` draw smooth rounded shapes.

### USB keyboard and mouse (`keys`)

```python
import keys

kb, mouse = keys.Keyboard(), keys.Mouse()   # US and Russian layouts, Alt+Shift switches
while switch.running():
    for ev in kb.poll():                    # presses and auto-repeat
        if ev.char:
            text += ev.char
        elif ev.code == keys.ENTER:
            ...
    m = mouse.poll()                        # x, y, dx, dy, wheel, buttons, pressed, released
```

Built on the system's own keyboard/mouse support (`usbinput`), which only sees devices
connected to the dock's USB ports - a USB-C OTG adapter in handheld mode is not recognized.

### Network (`requests`, `installer`)

```python
import requests
r = requests.get("https://api.github.com/repos/micropython/micropython")
print(r.status_code, r.json()["stargazers_count"])
requests.download("https://example.com/data.bin", "data.bin")

import installer
installer.install_url("https://github.com/OWNER/REPO/tree/main/tools")
```

### Serial ports and USB devices (`usbserial`, `usbhid`, `usbhost`)

```python
from usbserial import Serial
with Serial(baudrate=115200) as port:   # USB-Serial: CDC-ACM or CH340
    port.write("on\n")
    print(port.readline(timeout=1000))

import usbhid
with usbhid.HID(vid=0x1234) as dev:
    report = dev.read(timeout=100)

import usbhost                          # any other available device: control,
print(usbhost.devices())                # bulk and interrupt transfers
```

Connect devices to the dock USB ports, or through a USB-C OTG adapter in handheld mode.
Not every USB device is available to scripts: the system keeps HID-class devices
(keyboards, mice, gamepads and other HID devices) and anything sys-con recognizes for
itself. Devices with a vendor-specific interface (class 0xFF) work through `usbhost`.

### USB flash drives (`usbmsc`, `fat`)

The system does not claim USB mass storage devices either, so scripts can read them
directly: `usbmsc` speaks SCSI over Bulk-Only Transport (block-level, read-only) and
`fat` is a pure-Python, read-only FAT12/16/32 reader (no exFAT) built on top of it. The
launcher's **USB Drive** tab uses the same two modules to browse a flash drive and copy
files onto the SD card.

```python
import usbmsc, fat

drive = usbmsc.Drive(usbmsc.drives()[0])
vol = fat.mount(drive)                  # reads the MBR/boot sector, detects FAT12/16/32
for entry in vol.listdir():             # [{"name", "dir", "size"}, ...]
    print(entry["name"], entry["size"])
with vol.open("DCIM/100GOPRO/photo.jpg") as f:
    data = f.read()
vol.close()
```

### Console information (`sysinfo`)

`sysinfo.read()` returns a dict with the model, firmware, battery, temperatures, clocks,
storage, network and time; unknown values are `None`.

### Examples

| Script | What it shows |
|---|---|
| `examples/hwtest.py` | battery, buttons, sticks, touch, rumble |
| `examples/buttons.py` | simple button handling |
| `examples/files.py` | files and imports |
| `examples/forever.py` | an endless loop to test stopping |
| `examples/gfx_demo.py` | graphics: bouncing balls, stick control, FPS |
| `examples/gfx_paint.py` | finger painting on the touch screen |
| `examples/ui_demo.py` | GUI widgets, layouts and dialogs |
| `examples/kbm_test.py` | USB keyboard and mouse |
| `examples/usb_list.py` | available USB interfaces |
| `examples/usb_serial_test.py` | a serial port: sends commands, prints the replies |
| `examples/usb_hid_test.py` | prints HID reports |
| `examples/usb_drive_test.py` | mounts a USB flash drive, prints its files as a tree |

## Development

### Project layout

```
NXToolBox/
├── source/                 C sources (libnx): main.c, *_hw.c, mp_glue.c, mpconfigport.h
├── modules/switch/         MicroPython C modules: switch, usbhost, gfx, nxapp, http,
│                           sysinfo, image, usbinput (+ gfx_font.h)
├── app/launcher.py         the start screen
├── lib/                    Python libraries: ui, theme, tabs, tiles, systab, usbtab, usbdisk_tab,
│                           usbmsc, fat, settings_tab, docs_tab, about_tab, markdown, textview, editor, keys,
│                           modinfo, requests, installer, store, usbserial, usbhid
├── themes/                 dark.ini, light.ini (packed into the app)
├── examples/               example and test scripts
├── stubs/                  .pyi files for IDE completion
├── tools/                  bundle.py, make_catalog.py, make_font.py,
│                           gen_compile_commands.py
├── licenses/               third-party licenses
├── gen.sh                  generates micropython_embed/
├── send.py                 run scripts / upload files from a computer
├── update.json             online update manifest (written by tools/bundle.py)
└── update_url.txt          raw URL of update.json in your repository
```

C code uses C23 (GCC 15 in devkitA64 defaults to `gnu23`). New C modules go into
`modules/switch/mod*.c` (MicroPython side, no libnx headers) plus `source/*_hw.c` (libnx
side); add them to `modules/switch/micropython.mk` and run `./gen.sh`.

### CLion

```
python3 tools/gen_compile_commands.py
```

Then **File -> Open -> compile_commands.json -> Open as Project**. After `./gen.sh` or new
`.c` files, run the script again and use **Tools -> Compilation Database -> Reload**. Mark
`stubs/` as a Sources Root for Python completion.

### Protocol

`send.py` talks to the app over TCP port 5555. The Switch sends a random nonce, the client
answers with HMAC-SHA256(password, nonce) and a command: `R` (run a script, output streams
back; closing the sending side raises KeyboardInterrupt) or `U` (upload a file relative to
`/switch/NXToolBox`, written to a temporary file and renamed when complete).

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| HTTPS: "SSL peer certificate ... was not OK" | Check the console date and time; put `cacert.pem` into the project root and rebuild (or upload it to `/switch/NXToolBox/`). |
| A USB device is not listed | sys-con or the system took it. Disable sys-con (`/atmosphere/contents/690000000000000D/flags/boot2.flag`); HID-class devices stay with the system, use a device with a vendor-specific interface. |
| The system keyboard does not open | Start the homebrew menu by holding R on a game, not from the Album. |
| Cyrillic text is cut in the middle of letters | Enable `MICROPY_PY_BUILTINS_STR_UNICODE` in `source/mpconfigport.h` and rebuild. |
| "invalid syntax" on a `"\u..."` string | Without Unicode support only codes below 256 work; write the character itself. |
| The start screen does not start | Hold `-` while starting the app, fix `launcher.py`, press X in the text menu. |
| `undefined reference` after adding a module | Add it to `micropython.mk`, run `./gen.sh`, then `make clean && make`. |

## Safety notes

- Uploads and downloads are limited to `/switch/NXToolBox/`; paths with `..` are rejected.
- Scripts can access the whole SD card. Do not write to `atmosphere/`, `emuMMC/` or `Nintendo/`.
- The password protects against running code, but scripts and output are not encrypted.
- Scripts from the internet are ordinary code: install only what you trust. Tiles read
  `__NXTOOLBOX_MODULE__` without running the script.

## Third-party software

- [MicroPython](https://micropython.org) - MIT license, fetched separately.
- [libnx](https://github.com/switchbrew/libnx) and devkitPro tools - ISC and other licenses.
- [libcurl](https://curl.se) (devkitPro `switch-curl`) - curl license.
- [stb_image](https://github.com/nothings/stb) - public domain / MIT, fetched separately.
- [nanosvg](https://github.com/memononen/nanosvg) - zlib license, fetched separately,
  see `licenses/NANOSVG.txt`.
- Font glyphs from [GNU Unifont](https://unifoundry.com/unifont/) - SIL OFL 1.1 /
  GPLv2+ with the font embedding exception, see `licenses/UNIFONT.txt`.
- `cacert.pem` - the Mozilla CA certificate list as published by the curl project.
