# nxtest

Run Python scripts on a Nintendo Switch (homebrew, embedded MicroPython) - from an
on-console menu or from your computer over Wi-Fi, with live output like the Arduino
IDE serial monitor. Scripts can use the buttons, sticks, touch screen, rumble,
files on the SD card and USB devices (USB-Serial and HID).

## Features

- **On-console menu** with folders: browse `/switch/nxtest/scripts`, run with A.
- **Remote run and upload** from Windows, macOS or Linux (`send.py`, no dependencies).
- **Live output** on the Switch screen and in your terminal.
- **Stop any script**: Ctrl+C on the computer, `+` and `-` together on the console, or HOME.
- **Password protection** (HMAC-SHA256 challenge-response, the password never goes over the network).
- **Filesystem**: `open()`, `os`, `import` of your own modules from the SD card.
- **Hardware module `switch`**: buttons, sticks, touch, rumble, battery, timing.
- **USB host**: `usbhost` (low level), `usbserial` (CDC-ACM and CH340), `usbhid`.

## Project layout

```
nxtest/
├── source/                 app sources (C, libnx)
│   ├── main.c              menu, network server, script runner
│   ├── mp_glue.c           script interruption glue for MicroPython
│   ├── switch_hw.c         buttons, sticks, touch, rumble (libnx)
│   ├── usb_hw.c            USB host (libnx usbHs)
│   ├── mpconfigport.h      MicroPython configuration
│   └── micropython_embed.mk
├── modules/switch/         MicroPython C modules: switch, usbhost
├── lib/                    Python libraries: usbserial.py, usbhid.py
├── examples/               example and test scripts
├── arduino/serial_echo/    test sketch for USB-Serial
├── stubs/                  .pyi files for IDE completion
├── tools/                  gen_compile_commands.py (for CLion)
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

Copy the devkitPro template and change four lines:

```
cp $DEVKITPRO/examples/switch/templates/application/Makefile .
```

```make
TARGET   := nxtest
SOURCES  := source modules/switch micropython_embed/py micropython_embed/extmod micropython_embed/shared/runtime micropython_embed/port
INCLUDES := source modules/switch micropython_embed
LIBS     := -lnx -lm
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

Then (use `py` instead of `python3` on Windows):

```
python3 send.py run examples/hwtest.py            # run and watch the output
python3 send.py upload game.py                    # -> /switch/nxtest/scripts (menu)
python3 send.py upload mylib --to lib             # modules for import
python3 send.py upload config.json --to .         # -> /switch/nxtest
python3 send.py upload lib/usbserial.py lib/usbhid.py --to lib
```

### On the console

| Button | In the menu | While a script runs | After a script |
|---|---|---|---|
| Up/Down | select | | |
| A | open folder / run script | | |
| B | parent folder | | back to the menu |
| Y | refresh the list | | |
| + | exit the app | | |
| + and - together | | stop the script | |

### SD card layout

```
/switch/nxtest/
├── scripts/       scripts shown in the menu; working folder of the running script
├── lib/           modules for import (available to every script)
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
```

Full signatures and documentation are in `stubs/*.pyi`. USB devices are connected to the
dock USB ports, or through a USB-C OTG adapter in handheld mode. Everything a script opens
(USB devices, rumble) is released automatically when it ends.

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
