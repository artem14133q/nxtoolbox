# nxtest

Run Python scripts on a Nintendo Switch (homebrew, embedded MicroPython) - from an
on-console menu or from your computer over Wi-Fi, with live output like the Arduino
IDE serial monitor. Scripts can use the buttons, sticks, touch screen, rumble,
1280x720 graphics, files on the SD card and USB devices (USB-Serial and HID).

## Features

- **Start screen written in Python** (`app/launcher.py`): change it and upload it, no rebuild.
  A built-in text menu is the fallback if the launcher is missing or broken.
- **Remote run and upload** from Windows, macOS or Linux (`send.py`, no dependencies).
- **Live output** on the Switch screen and in your terminal.
- **Stop any script**: Ctrl+C on the computer, `+` and `-` together on the console, or HOME.
- **Password protection** (HMAC-SHA256 challenge-response, the password never goes over the network).
- **Filesystem**: `open()`, `os`, `import` of your own modules from the SD card.
- **Hardware module `switch`**: buttons, sticks, touch, rumble, battery, timing.
- **Graphics module `gfx`**: 1280x720, shapes, text (Latin and Cyrillic), sprites, ~60 fps.
- **GUI library `ui`**: buttons, checkboxes, sliders, lists, progress bars and dialogs;
  D-pad, A/B and touch control.
- **USB host**: `usbhost` (low level), `usbserial` (CDC-ACM and CH340), `usbhid`.
- **HTTP(S)**: `http` / `requests` for scripts; **Get scripts** installs scripts from GitHub,
  any URL, or script catalogs.

## Project layout

```
nxtest/
├── source/                 app sources (C, libnx)
│   ├── main.c              menu, network server, script runner
│   ├── mp_glue.c           script interruption glue for MicroPython
│   ├── switch_hw.c         buttons, sticks, touch, rumble (libnx)
│   ├── usb_hw.c            USB host (libnx usbHs)
│   ├── gfx_hw.c            graphics mode (libnx framebuffer)
│   ├── mpconfigport.h      MicroPython configuration
│   └── micropython_embed.mk
├── modules/switch/         MicroPython C modules: switch, usbhost, gfx, nxapp, http
├── app/launcher.py         the start screen (uploaded to /switch/nxtest/launcher.py)
├── lib/                    Python libraries: ui, requests, installer, store, usbserial, usbhid
├── examples/               example and test scripts
├── arduino/serial_echo/    test sketch for USB-Serial
├── stubs/                  .pyi files for IDE completion
├── tools/                  bundle.py, gen_compile_commands.py, make_font.py, make_catalog.py
├── update.json             online update manifest (written by tools/bundle.py, commit it)
├── update_url.txt          optional: raw URL of update.json in your repository
├── licenses/               third-party licenses (font)
├── gen.sh                  generates micropython_embed/
├── send.py                 run scripts / upload files from a computer
└── Makefile                devkitPro application Makefile (see below)
```

## Requirements

- A Switch that can run homebrew (Atmosphère CFW). Use emuMMC and stay offline with CFW.
- [devkitPro](https://devkitpro.org) with the `switch-dev` package (`DEVKITPRO` set, usually `/opt/devkitpro`).
- The [MicroPython](https://github.com/micropython/micropython) repository (1.20 or newer),
  by default next to this project: `../micropython`. Another location: set `MICROPYTHON_DIR`.
- Python 3.8+ on the computer (for `gen.sh` and `send.py`).

## Build

### Makefile (first time only)

Install libcurl for HTTPS (it uses the console's own TLS service):

```
sudo dkp-pacman -S switch-curl
```

Copy the devkitPro template and change these lines:

```
cp $DEVKITPRO/examples/switch/templates/application/Makefile .
```

```make
TARGET   := nxtest
SOURCES  := source modules/switch micropython_embed/py micropython_embed/extmod micropython_embed/shared/runtime micropython_embed/port
INCLUDES := source modules/switch micropython_embed
LIBS     := -lcurl -lz -lnx -lm
ROMFS    := romfs
```

and make the build run `tools/bundle.py` first (it packs `app/launcher.py` and `lib/*.py`
into the .nro):

```make
$(BUILD): bundle
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

.PHONY: bundle
bundle:
	@python3 tools/bundle.py
```

### Generate MicroPython and build

```
./gen.sh                  # after cloning, after changing modules/ or source/mpconfigport.h
make clean && make        # produces nxtest.nro
```

If you only changed `source/*.c`, plain `make` is enough.

Copy `nxtest.nro` to `/switch/` on the SD card and start it from the homebrew menu
(preferably by holding R while launching a game, which gives the app more memory).

## Using it

On the first start the app creates a password, shows it on the screen and saves it to
`/switch/nxtest/password.txt`. Set up the computer once:

```
# macOS / Linux (~/.zshrc or ~/.bashrc)
export NXTEST_HOST=192.168.1.42
export NXTEST_PASSWORD=yourpassword

# Windows
setx NXTEST_HOST 192.168.1.42
setx NXTEST_PASSWORD yourpassword
```

The start screen (`app/launcher.py`) and the libraries (`lib/*.py`) are packed into
`nxtest.nro` and installed into `/switch/nxtest/sys/` automatically. Files you upload to
`/switch/nxtest/launcher.py` or `/switch/nxtest/lib/` take priority over them (quick
patches without rebuilding); delete them to go back to the bundled versions.

HTTPS certificates are checked against the console's certificate store. A
`/switch/nxtest/cacert.pem`, if present, is used as well (e.g. for a private CA);
`verify=False` disables the check.

Then (use `py` instead of `python3` on Windows):

```
python3 send.py run examples/hwtest.py            # run and watch the output
python3 send.py upload game.py                    # -> /switch/nxtest/scripts (menu)
python3 send.py upload mylib --to lib             # modules for import
python3 send.py upload config.json --to .         # -> /switch/nxtest
python3 send.py upload lib/ui.py lib/usbserial.py lib/usbhid.py --to lib
```

### On the console

| Button | Start screen | While a script runs | After a script |
|---|---|---|---|
| D-pad / touch | select | | |
| A | open folder / run script | | |
| B | parent folder | | back to the start screen |
| Y | refresh the list | | |
| X | delete the selected file | | |
| R | Get scripts (download) | | |
| + | exit the app | | |
| + and - together | | stop the script | |

### Start screen (launcher)

The start screen is `/switch/nxtest/launcher.py`, an ordinary script built with `lib/ui.py`
that talks to the app through the `nxapp` module (see `stubs/nxapp.pyi`). To change it,
edit `app/launcher.py` and upload it with `--to .`: the running launcher reloads itself
when `launcher.py` or `lib/ui.py` is uploaded.

If the launcher is missing or fails (its error is shown on the screen), the app uses the
built-in text menu; press X there to try the launcher again. Hold `-` while starting the
app to skip the launcher. `+` and `-` together also stop the launcher.

### SD card layout

```
/switch/nxtest/
├── sys/           bundled launcher.py, lib/ and VERSION (managed by the app)
├── launcher.py    optional: your start screen, overrides sys/launcher.py
├── lib/           your modules (override sys/lib)
├── scripts/       scripts shown on the start screen; working folder of the running script
└── password.txt   delete it to generate a new password
```

In scripts `/` is the SD card root; `sdmc:/` paths do not work.

## Script API (short)

```python
import switch

switch.buttons()            # mask of held buttons: switch.buttons() & switch.A
switch.buttons_down()       # pressed since the previous call
switch.stick(0)             # (x, y) of the left stick, -1.0..1.0; 1 = right stick
switch.touches()            # [(x, y), ...] in handheld mode
switch.rumble(0.5, 300)     # strength, duration in ms (0 = until rumble(0))
switch.battery()            # percent
switch.ticks_ms()           # milliseconds since power on
switch.sleep_ms(16)         # interruptible pause
switch.running()            # call in every loop; False when the app must exit

from usbserial import Serial
with Serial(baudrate=115200) as port:   # CDC-ACM (ESP32-C3, STM32, Uno R3) or CH340 clones
    port.write("on\n")
    print(port.readline(timeout=1000))  # str or None

import usbhid
with usbhid.HID(vid=0x1234) as dev:
    report = dev.read(timeout=100)      # bytes or None
    dev.write(bytes([0, 1, 2]))         # Report ID + data

import gfx                              # the first drawing call switches to graphics mode
while switch.running():
    gfx.clear(gfx.rgb(20, 24, 40))
    gfx.fill_circle(640, 360, 50, gfx.RED)
    gfx.text(20, 20, "Hello / Привет", gfx.WHITE, scale=2)
    gfx.present()                       # show the frame, ~60 fps
# gfx.line, rect, fill_rect, circle, pixel, text_width, blit(x, y, w, h, rgba_bytes)
```

When a script that used graphics ends, the text console comes back and shows everything
the script printed in the meantime (including errors).

### GUI (`lib/ui.py`)

Widgets are placed by layouts, like in Qt:

```python
import ui

scr = ui.Screen("Settings")

form = ui.Grid()                                  # labels | controls
form.add(ui.Label("Volume"), 0, 0)
level = form.add(ui.Slider(value=30, maximum=100), 0, 1)
form.add(ui.Label("Sound"), 1, 0)
sound = form.add(ui.Checkbox("Enabled", checked=True), 1, 1)
form.set_column_stretch(1, 1)                     # the controls column takes the free width

buttons = ui.HBox()
buttons.add(ui.Button("Save", on_click=lambda: ui.message("Saved: %d" % level.value)))
buttons.add(ui.Button("Cancel", on_click=scr.close))
buttons.add_stretch()                             # push the buttons to the left

root = ui.VBox()
root.add(form)
root.add(buttons)
root.add_stretch()
scr.set_layout(root)
scr.run()                      # returns when the screen is closed (B by default)

ui.confirm("Delete the file?")            # True / False
ui.choose("Pick one", ["A", "B", "C"])    # index or None
```

- Widgets: `Label`, `Button`, `Checkbox`, `Slider`, `ProgressBar`, `ListBox`. The content
  comes first; the position is optional (`x=`, `y=` or `.move(x, y)`) for screens without layouts.
- Layouts: `VBox`, `HBox` (`add(item, stretch=0, align="left")`, `add_stretch()`,
  `add_spacing(px)`) and `Grid` (`add(item, row, col, rowspan=1, colspan=1)`,
  `set_column_stretch()`, `set_row_stretch()`). Layouts can be nested.
- Free space goes to items with a stretch factor, or else to expanding widgets: `Slider` and
  `ProgressBar` grow in width, `ListBox` in width and height. `widget.expanding()` makes any
  widget grow. A `Label` with `w=` reserves width for changing text (`align="right"` etc.).
- The D-pad moves the focus to the nearest widget in that direction, A activates, B closes
  the screen (`on_back` changes that), touch works everywhere. Assign `scr.update` to a
  function to refresh widgets every frame (e.g. from USB data). Only changed widgets are redrawn.

### Updates of the launcher and libraries

- **New .nro:** the bundled files are installed when their version (the newest modification
  time of the sources, `YYYYMMDDHHMMSS`) is newer than the installed one.
- **Online:** put the raw URL of `update.json` in your repository into `update_url.txt`
  (see `update_url.txt.example`) before building. Once per app start the launcher checks it
  and offers to install a newer version. To publish an update: build (this rewrites
  `update.json`), then commit and push `update.json`, `app/launcher.py` and `lib/`.
  A version installed online is kept even if an older .nro is started later.

### Downloading scripts (Get scripts)

Press R on the start screen (or the "Get scripts..." button):

- **Download from a GitHub or file URL** - type a link with the system keyboard. A file
  (`github.com/OWNER/REPO/blob/BRANCH/file.py`), a folder (`.../tree/BRANCH/folder`), a whole
  repository (`github.com/OWNER/REPO`) or any direct link. Folders keep their structure
  under `scripts/`.
- **Catalogs** - an `index.json` listing packages on any web server; the Switch shows titles,
  versions and descriptions, installs and updates packages and can run them right away.
  Build one with `tools/make_catalog.py` (see the comment at the top of that file) and host it
  on GitHub (`https://raw.githubusercontent.com/OWNER/REPO/main/index.json`) or locally
  (`python3 -m http.server 8000` in the catalog folder). Catalogs are stored in
  `/switch/nxtest/catalogs.txt` ("Name | URL" per line).

The system keyboard may be unavailable when the homebrew menu is started from the Album;
start it by holding R while launching a game.

From scripts:

```python
import requests
r = requests.get("https://api.github.com/repos/micropython/micropython")
print(r.status_code, r.json()["stargazers_count"])
requests.download("https://example.com/data.bin", "data.bin")

import installer
installer.install_url("https://github.com/OWNER/REPO/tree/main/tools")
```

## Examples

| Script | What it shows |
|---|---|
| `examples/hwtest.py` | battery, buttons, sticks, touch, rumble step by step |
| `examples/buttons.py` | simple button handling |
| `examples/files.py` | files and imports |
| `examples/forever.py` | endless loop to test stopping |
| `examples/usb_list.py` | available USB interfaces |
| `examples/usb_serial_test.py` | talks to `arduino/serial_echo` |
| `examples/usb_hid_test.py` | prints HID reports |
| `examples/gfx_demo.py` | graphics: bouncing balls, stick control, FPS |
| `examples/gfx_paint.py` | finger painting on the touch screen |
| `examples/ui_demo.py` | all GUI widgets and dialogs |

## CLion

```
python3 tools/gen_compile_commands.py
```

Then **File → Open → compile_commands.json → Open as Project**. After `./gen.sh` or adding
`.c` files, re-run the script and use **Tools → Compilation Database → Reload**. For Python,
mark `stubs/` as a Sources Root.

## Safety notes

- Uploads are limited to `/switch/nxtest/`; paths with `..` are rejected.
- Scripts can access the whole SD card. Do not write to `atmosphere/`, `emuMMC/` or `Nintendo/`.
- The password protects against running code, but scripts and output are not encrypted.

## Third-party

- [MicroPython](https://micropython.org) (MIT), fetched separately.
- Font glyphs from [GNU Unifont](https://unifoundry.com/unifont/), see `licenses/UNIFONT.txt`.