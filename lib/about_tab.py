"""about_tab - the "About" tab of the launcher: version and credits, rendered from
Markdown with lib/markdown.py + lib/textview.py.

    import about_tab
    page = about_tab.AboutTab()
    scr.add_tab("About", page.layout, hint="Up/Down or drag: scroll")
"""
import ui
import markdown
import textview

VERSION_FILE = "/switch/NXToolBox/sys/VERSION"

TEXT = """
# NXToolBox

A Python toolbox for the Nintendo Switch (homebrew, Atmosphere): run, edit and manage
MicroPython scripts on the console, or from a computer with `send.py`.

- **Version:** %s
- **Repository:** github.com/artem14133q/nxtoolbox
- Hold **-** while starting the app to skip the start screen and go straight to the
  built-in text menu.

## Built with

- [MicroPython](https://micropython.org) - MIT license
- [libnx](https://github.com/switchbrew/libnx) and devkitPro tools - ISC and other licenses
- [libcurl](https://curl.se) - curl license
- [stb_image](https://github.com/nothings/stb) - public domain / MIT
- **Inter** font - SIL Open Font License 1.1, see `licenses/INTER_FONT.txt`
- **JetBrains Mono** font - SIL Open Font License 1.1, see `licenses/JETBRAINS_FONT.txt`
- GNU Unifont (the built-in pixel font) - SIL OFL 1.1 / GPLv2+, see `licenses/UNIFONT.txt`
- `cacert.pem` - the Mozilla CA certificate list, as published by the curl project

## Safety notes

> Scripts can access the whole SD card - do not write to `atmosphere/`, `emuMMC/` or
> `Nintendo/`. Scripts from the internet are ordinary code: install only what you trust.

The password protects against running code over the network, but scripts and their
output are not encrypted. Uploads and downloads are limited to `/switch/NXToolBox/`.
"""


def _read_line(path):
    try:
        with open(path) as f:
            return f.readline().strip()
    except OSError:
        return ""


class AboutTab:
    def __init__(self):
        text = TEXT % (_read_line(VERSION_FILE) or "dev")
        view = textview.TextView(markdown.parse(text), rows=14, w=900)
        root = ui.VBox()
        root.add(view, stretch=1)
        self.layout = root
