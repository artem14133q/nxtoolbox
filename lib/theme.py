"""theme - color themes and corner rounding for ui, tabs, tiles and the editor.

Themes are INI files:
    /switch/NXToolBox/themes/<name>.ini       your themes (take priority)
    /switch/NXToolBox/sys/themes/<name>.ini   bundled: dark, light

The selected theme and the corner radius are stored in /switch/NXToolBox/settings.ini:
    [ui]
    theme = dark
    radius = 8            ; optional, overrides the theme's radius (0 = square corners)

A theme may define only some colors: the rest come from the built-in dark theme.
Colors are "#RRGGBB", "#RGB" or "r, g, b", with an optional alpha channel: "#RRGGBBAA",
"#RGBA" or "r, g, b, a" (FF / 255 = opaque). "background" and "dialog" are always opaque.

Fonts (section [fonts]: ui, mono) are .ttf files looked up in /switch/NXToolBox/fonts and
then in /switch/NXToolBox/sys/fonts. Without them the GUI uses the built-in pixel font.

    import theme
    t = theme.current()            # the theme from settings.ini (loaded once)
    t.color("accent")              # gfx color
    t.radius
    theme.available()              # [(name, title), ...]
    theme.save_settings(theme="light", radius=6)
"""
import gfx

APP = "/switch/NXToolBox"
SETTINGS = APP + "/settings.ini"
THEME_DIRS = (APP + "/themes", APP + "/sys/themes")
FONT_DIRS = (APP + "/fonts", APP + "/sys/fonts")

# The built-in dark theme (JetBrains New UI Dark); every theme falls back to these values
DEFAULTS = {
    "theme": {"name": "Dark", "radius": "8"},
    "colors": {
        "background": "#1E1F22",     # screens
        "bar": "#2B2D30",            # title bar
        "dialog": "#2B2D30",         # dialog background
        "border": "#43454A",         # dialog border
        "panel": "#393B40",          # buttons, lists, tiles
        "panel_hover": "#4E5157",    # selected / focused widget background
        "accent": "#3574F0",         # focus, selection, sliders
        "accent_text": "#FFFFFF",    # text on the accent color
        "selection": "#2E436E",      # selected row of a list without focus
        "text": "#DFE1E5",
        "muted": "#868A91",
        "disabled": "#5A5D63",
        "success": "#5FB865",
        "warning": "#F2C55C",
        "error": "#F75464",
        "icon_bg": "#2B2D30",        # plate behind tile icons
        "overlay": "#0000008C",      # dims the screen behind dialogs
    },
    "fonts": {
        "ui": "Inter-Regular.ttf",           # the GUI (JetBrains New UI uses Inter)
        "italic": "Inter-Italic.ttf",         # *italic* text in textview.py
        "mono": "JetBrainsMono-Regular.ttf",  # the script editor, ``` code ``` blocks
    },
    "editor": {
        "background": "#1E1F22",
        "gutter": "#1E1F22",
        "line_number": "#4B5059",
        "line_number_current": "#A1A3AB",
        "line_highlight": "#26282E",
        "text": "#BCBEC4",
        "cursor": "#CED0D6",
        "bar": "#2B2D30",
        "output": "#191A1C",
        "error_line": "#5E3438",
        "error_text": "#F75464",
        "keyword": "#CF8E6D",
        "string": "#6AAB73",
        "comment": "#7A7E85",
        "number": "#2AACB8",
        "builtin": "#8888C6",
        "function": "#56A8F5",
    },
}


# ---------- INI ----------

def parse_ini(text):
    """{section: {key: value}}; comments start with ; or # (also after a value)."""
    data = {}
    section = data.setdefault("", {})
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = data.setdefault(line[1:-1].strip().lower(), {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()               # a value may start with # (a color)
        for mark in (" ;", " #", "\t;", "\t#"):
            i = value.find(mark)            # comments need a space before them
            if i >= 0:
                value = value[:i].strip()
        section[key.strip().lower()] = value
    return data


def read_ini(path):
    try:
        with open(path) as f:
            return parse_ini(f.read())
    except OSError:
        return {}


def _write_ini(path, data, header=""):
    with open(path, "w") as f:
        if header:
            f.write(header)
        for name, section in data.items():
            if not name or not section:
                continue
            f.write("[%s]\n" % name)
            for key, value in section.items():
                f.write("%s = %s\n" % (key, value))
            f.write("\n")


def parse_color(value, fallback=None):
    """gfx color from "#RRGGBB", "#RRGGBBAA", "#RGB", "#RGBA", "r, g, b" or "r, g, b, a"
    (alpha 255 / FF = opaque, 0 = invisible); fallback if it cannot be read."""
    try:
        v = value.strip()
        if v.startswith("#"):
            h = v[1:]
            if len(h) in (3, 4):
                h = "".join(c * 2 for c in h)
            if len(h) not in (6, 8):
                return fallback
            alpha = int(h[6:8], 16) if len(h) == 8 else 255
            return gfx.rgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
        parts = [int(p) for p in v.split(",")]
        return gfx.rgb(parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else 255)
    except (ValueError, IndexError, AttributeError):
        return fallback


# ---------- themes ----------

class Theme:
    def __init__(self, name, data):
        self.name = name
        self.title = data.get("theme", {}).get("name") or name
        try:
            self.radius = max(0, int(data.get("theme", {}).get("radius", DEFAULTS["theme"]["radius"])))
        except ValueError:
            self.radius = int(DEFAULTS["theme"]["radius"])
        self.fonts = {}
        given_fonts = data.get("fonts", {})
        for kind, default in DEFAULTS["fonts"].items():
            self.fonts[kind] = font_path(given_fonts.get(kind) or default)
        self._colors = {}
        for section in ("colors", "editor"):
            defaults = DEFAULTS[section]
            given = data.get(section, {})
            for key, default in defaults.items():
                fallback = parse_color(default)
                self._colors[section + "." + key] = parse_color(given.get(key, default), fallback)

    def color(self, key):
        """A color from [colors]; "editor.keyword" style keys for other sections."""
        return self._colors.get(key if "." in key else "colors." + key)


def font_path(name):
    """Full path of a font file (a name from the fonts folders, or a path), or None."""
    candidates = [name] if name.startswith("/") else ["%s/%s" % (d, name) for d in FONT_DIRS]
    for path in candidates:
        try:
            open(path).close()
            return path
        except OSError:
            pass
    return None


def theme_path(name):
    for folder in THEME_DIRS:
        path = "%s/%s.ini" % (folder, name)
        try:
            open(path).close()
            return path
        except OSError:
            pass
    return None


def load(name):
    """Load a theme by name (built-in dark values if the file is missing)."""
    path = theme_path(name)
    return Theme(name, read_ini(path) if path else {})


def available():
    """[(name, title)] of all themes, your folder first; names are unique."""
    import os
    seen = {}
    for folder in THEME_DIRS:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for fname in names:
            if fname.endswith(".ini") and not fname.startswith("."):
                name = fname[:-4]
                if name not in seen:
                    title = read_ini(folder + "/" + fname).get("theme", {}).get("name") or name
                    seen[name] = title
    if not seen:
        seen["dark"] = DEFAULTS["theme"]["name"]
    return sorted(seen.items(), key=lambda item: item[1].lower())


def settings():
    """(theme name, radius or None) from settings.ini."""
    ui = read_ini(SETTINGS).get("ui", {})
    radius = ui.get("radius")
    try:
        radius = max(0, int(radius)) if radius not in (None, "") else None
    except ValueError:
        radius = None
    return ui.get("theme") or "dark", radius


def save_settings(theme=None, radius=None):
    """Store the theme and/or the corner radius in settings.ini (other settings are kept)."""
    data = read_ini(SETTINGS)
    section = data.setdefault("ui", {})
    if theme is not None:
        section["theme"] = theme
    if radius is not None:
        section["radius"] = str(int(radius))
    _write_ini(SETTINGS, data, "; NXToolBox settings\n\n")
    global _current
    _current = None                     # load again next time


_current = None


def current():
    """The theme selected in settings.ini, with the radius from settings.ini if set."""
    global _current
    if _current is None:
        name, radius = settings()
        _current = load(name)
        if radius is not None:
            _current.radius = radius
    return _current
