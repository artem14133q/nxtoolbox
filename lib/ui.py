"""ui - a small GUI toolkit for NXToolBox scripts, built on the gfx module.

Controls: D-pad moves the focus to the nearest widget in that direction, A activates,
B goes back (closes the screen). Everything also works with the touch screen.

Widgets are placed either by layouts (like in Qt) or at fixed positions (x=, y=):

    import ui

    scr = ui.Screen("Settings")
    form = ui.Grid()
    form.add(ui.Label("Volume"), 0, 0)
    level = form.add(ui.Slider(value=30, maximum=100), 0, 1)
    form.add(ui.Label("Sound"), 1, 0)
    sound = form.add(ui.Checkbox("Enabled", checked=True), 1, 1)
    form.set_column_stretch(1, 1)

    root = ui.VBox()
    root.add(form)
    root.add(ui.Button("Save", on_click=lambda: ui.message("Saved: %d" % level.value)))
    root.add_stretch()
    scr.set_layout(root)
    scr.run()

Layouts: VBox, HBox, Grid; they can be nested. Free space goes to items with a stretch
factor, or (if there are none) to expanding widgets: Slider and ProgressBar grow in width,
ListBox in width and height. widget.expanding() makes any widget grow.

Only the widgets that changed are redrawn. Widgets must not overlap.

Colors and corner rounding come from the theme (lib/theme.py, settings.ini). set_rounded(r)
changes the corner radius at run time; box() draws a rounded, antialiased rectangle.
"""
import switch
import gfx

# ---------- theme ----------

import theme as _theme

THEME = _theme.current()


def opaque(color):
    """The color without transparency."""
    return color | 0xFF000000


def over(color, bg):
    """The opaque color you see when color (with its alpha) is drawn over bg."""
    a = (color >> 24) & 0xFF
    if a == 255:
        return color
    out = 0xFF000000
    for shift in (0, 8, 16):
        c, b = (color >> shift) & 0xFF, (bg >> shift) & 0xFF
        out |= ((c * a + b * (255 - a) + 127) // 255) << shift
    return out


def shade(color, delta):
    """color with each RGB channel shifted by delta (clamped 0..255), alpha unchanged.
    Negative darkens, positive lightens - a theme-independent way to get a second,
    subtly different tone from an already-opaque color (e.g. for a gradient)."""
    out = color & 0xFF000000
    for shift in (0, 8, 16):
        c = (color >> shift) & 0xFF
        out |= max(0, min(255, c + delta)) << shift
    return out


# Colors may be transparent (#RRGGBBAA in the theme) - except the backgrounds: widgets erase
# themselves with them before they redraw.
BG = opaque(THEME.color("background"))    # screen background
BAR = THEME.color("bar")                  # title bar
# BAR may be translucent (e.g. the glass theme's near-transparent white); over(BAR, BG)
# resolves it to the same opaque color the flat title bar already renders as today, so
# the gradient stays correct for every theme instead of guessing at a second raw color.
BAR_TOP = over(BAR, BG)
BAR_LOW = shade(BAR_TOP, -14)              # subtly darker: bottom of the title bar
DIALOG = opaque(THEME.color("dialog"))    # dialog background
BORDER = THEME.color("border")            # outlines and separators
PANEL = THEME.color("panel")              # widget background
PANEL_HI = THEME.color("panel_hover")     # widget background when focused
ACCENT = THEME.color("accent")            # focus ring, slider fill, selection
ACCENT_TEXT = THEME.color("accent_text")  # text on ACCENT
SELECTION = THEME.color("selection")      # selected row of a list without focus
TEXT = THEME.color("text")
MUTED = THEME.color("muted")
DISABLED = THEME.color("disabled")
SUCCESS = THEME.color("success")
WARNING = THEME.color("warning")
ERROR = THEME.color("error")
ICON_BG = THEME.color("icon_bg")
OVERLAY = THEME.color("overlay")          # dims the screen behind dialogs
RADIUS = THEME.radius                     # corner radius in pixels, 0 = square corners

SCALE = 2                          # text scale: characters are 16x32 pixels
CHAR_W = gfx.FONT_WIDTH * SCALE
CHAR_H = gfx.FONT_HEIGHT * SCALE
TITLE_H = 56
FOOTER_H = 40
MARGIN = 24                        # space between the screen edges and a layout

_DIRS = switch.UP | switch.DOWN | switch.LEFT | switch.RIGHT
_REPEAT_DELAY = 400                # ms before a held direction starts repeating
_REPEAT_RATE = 80                  # ms between repeats
_DRAG_PX = 14                      # finger movement before a touch becomes a scroll drag, not a tap

_stack = []                        # screens currently running (dialogs on top)


# ---------- text ----------
# Smooth TrueType text (the font module with the theme's fonts), or the built-in pixel font
# if either is missing. "scale" keeps its meaning for layouts: a line is 16 * scale pixels.

UI_FONT = None                     # font ids from font.load(), None = pixel font
MONO_FONT = None
ITALIC_FONT = None                 # *italic* text in textview.py; None = no real slant
_font = None
try:
    import font as _font
    if THEME.fonts.get("ui"):
        UI_FONT = _font.load(THEME.fonts["ui"])
    if THEME.fonts.get("mono"):
        MONO_FONT = _font.load(THEME.fonts["mono"])
    if THEME.fonts.get("italic"):
        ITALIC_FONT = _font.load(THEME.fonts["italic"])
    if UI_FONT is not None and MONO_FONT is not None:
        _font.fallback(UI_FONT, MONO_FONT)        # characters missing in the GUI font
    if ITALIC_FONT is not None and UI_FONT is not None:
        _font.fallback(ITALIC_FONT, UI_FONT)      # characters missing in the italic font
except (ImportError, OSError):
    pass

_UNICODE = len("é") == 1           # str counts characters (else: UTF-8 bytes)


def _chars(text):
    """List of characters, also when strings are byte-based (no Unicode support)."""
    if _UNICODE:
        return list(text)
    out = []
    i = 0
    while i < len(text):
        b = ord(text[i])
        n = 1 if b < 0x80 else 2 if b < 0xE0 else 3 if b < 0xF0 else 4
        out.append(text[i:i + n])
        i += n
    return out


def font_size(scale=SCALE):
    """Pixel height of the TrueType font for a text scale: 16 px for scale 1, 30 for 2
    (the lines stay 16 * scale pixels high, as with the pixel font)."""
    return 14 * scale + 2


def text(x, y, s, color=None, scale=SCALE, bold=False):
    """Draw text with its top-left corner at (x, y); returns its width in pixels.
    bold fakes a bolder stroke by drawing two extra passes, 1px right and 1px down -
    there is no real bold face for either font backend, but this works with both of
    them and (unlike a single offset pass) actually reads as bold at small sizes."""
    if color is None:
        color = TEXT
    if UI_FONT is None:
        w = gfx.text(x, y, s, color, scale)
        if bold:
            gfx.text(x + 1, y, s, color, scale)
            gfx.text(x, y + 1, s, color, scale)
        return w
    size = font_size(scale)
    line = gfx.FONT_HEIGHT * scale
    top = y + (line - size) // 2
    widest = 0
    for i, part in enumerate(s.split("\n")):
        ty = top + i * line
        widest = max(widest, _font.text(UI_FONT, x, ty, part, color, size))
        if bold:
            _font.text(UI_FONT, x + 1, ty, part, color, size)
            _font.text(UI_FONT, x, ty + 1, part, color, size)
    return widest


def text_width(s, scale=SCALE):
    """Width of text in pixels (the widest line)."""
    if UI_FONT is None:
        return gfx.text_width(s, scale)
    return _font.width(UI_FONT, s, font_size(scale))


def elide(s, width, scale=SCALE):
    """s, shortened with "…" at the end if it is wider than width pixels."""
    if text_width(s, scale) <= width:
        return s
    chars = _chars(s)
    lo, hi = 0, len(chars)
    while lo < hi:                                  # the longest prefix that fits
        mid = (lo + hi + 1) // 2
        if text_width("".join(chars[:mid]) + "…", scale) <= width:
            lo = mid
        else:
            hi = mid - 1
    return "".join(chars[:lo]) + "…"


# Monospace text (the script editor): zoom levels -> font pixel size
MONO_SIZES = (13, 16, 20, 26)
_mono_cells = {}


def mono_cell(zoom):
    """(column width, line height) in pixels of the monospace font at a zoom level."""
    zoom = max(0, min(len(MONO_SIZES) - 1, zoom))
    cell = _mono_cells.get(zoom)
    if cell is None:
        if MONO_FONT is None:
            scale = 1 if zoom < 2 else 2
            cell = (gfx.FONT_WIDTH * scale, gfx.FONT_HEIGHT * scale)
        else:
            size = MONO_SIZES[zoom]
            width10 = _font.width(MONO_FONT, "M" * 10, size)   # exact to 1/10 pixel
            cell = ((width10 + 5) // 10, size * 4 // 3)
        _mono_cells[zoom] = cell
    return cell


def mono_text(x, y, s, color, zoom=1):
    """Draw text on the monospace grid (one column per character); returns its width."""
    zoom = max(0, min(len(MONO_SIZES) - 1, zoom))
    if MONO_FONT is None:
        return gfx.text(x, y, s, color, 1 if zoom < 2 else 2)
    cw, ch = mono_cell(zoom)
    size = MONO_SIZES[zoom]
    return _font.text(MONO_FONT, x, y + (ch - size) // 2, s, color, size, cw)


def _text_w(s, scale=SCALE):
    return text_width(s, scale)


def _lines(text):
    return text.count("\n") + 1


def wrap(text, width):
    """Break lines longer than width characters (at spaces where possible)."""
    out = []
    for line in text.split("\n"):
        while len(line) > width:
            cut = line.rfind(" ", 0, width + 1)
            if cut <= 0:
                cut = width
            out.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        out.append(line)
    return "\n".join(out)


# ---------- base widget ----------

# ---------- rounded boxes ----------
# With the draw module (C) shapes are blended into the frame: transparent colors work and
# rounded corners are smooth over any background. Without it corner images are made here
# and transparent colors are mixed with the bg argument.

try:
    import draw as _draw
except ImportError:
    _draw = None


def fill(x, y, w, h, color):
    """A filled rectangle; transparent colors are blended with what is already there."""
    if w <= 0 or h <= 0:
        return
    if _draw is not None:
        _draw.rect(x, y, w, h, color)
    else:
        gfx.fill_rect(x, y, w, h, over(color, BG))


_SAMPLES = 4                       # antialiasing: 4x4 samples per corner pixel
_corner_cache = {}


def _channels(c):
    return c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF


def _corners(r, fill, border, bw, bg):
    """RGBA images of the four corners (top-left, top-right, bottom-left, bottom-right):
    the fill and a border ring of width bw. Pixels fully outside the rounding are
    transparent (whatever is below stays visible); edge pixels are blended with bg."""
    key = (r, fill, border, bw, bg)
    got = _corner_cache.get(key)
    if got:
        return got
    if len(_corner_cache) > 128:
        _corner_cache.clear()
    fr, fg, fb = _channels(fill)
    rr, rg, rb = _channels(border)
    br, bgg, bb = _channels(bg)
    outer2 = r * r
    inner = max(0, r - bw)
    inner2 = inner * inner
    n = _SAMPLES * _SAMPLES
    offsets = [(k + 0.5) / _SAMPLES for k in range(_SAMPLES)]
    images = [bytearray(r * r * 4) for _ in range(4)]
    tl, tr, bl, brc = images
    for j in range(r):
        for i in range(r):
            a_out = a_in = 0
            for oy in offsets:
                dy = r - (j + oy)
                dy2 = dy * dy
                for ox in offsets:
                    dx = r - (i + ox)
                    d2 = dx * dx + dy2
                    if d2 <= outer2:
                        a_out += 1
                        if d2 <= inner2:
                            a_in += 1
            if a_out == 0:
                continue                    # outside: stays transparent (alpha 0)
            w_bg, w_ring = n - a_out, a_out - a_in
            px = ((br * w_bg + rr * w_ring + fr * a_in) // n,
                  (bgg * w_bg + rg * w_ring + fg * a_in) // n,
                  (bb * w_bg + rb * w_ring + fb * a_in) // n)
            mi, mj = r - 1 - i, r - 1 - j
            for img, x, y in ((tl, i, j), (tr, mi, j), (bl, i, mj), (brc, mi, mj)):
                k = (y * r + x) * 4
                img[k] = px[0]
                img[k + 1] = px[1]
                img[k + 2] = px[2]
                img[k + 3] = 255
    result = (bytes(tl), bytes(tr), bytes(bl), bytes(brc))
    _corner_cache[key] = result
    return result


def box(
    x,
    y,
    w,
    h,
    _fill,
    border=None,
    bw=0,
    radius=None,
    bg=None
):
    """A filled rectangle with rounded, antialiased corners and an optional border.
    bg is the color around the box (the corners are blended into it);
    radius None means the theme radius (RADIUS), 0 square corners."""
    if w <= 0 or h <= 0:
        return
    r = RADIUS if radius is None else radius
    r = max(0, min(r, w // 2, h // 2))
    if _draw is not None:
        _draw.rect(x, y, w, h, _fill, radius=r,
                   border=border if bw > 0 else None, border_width=bw)
        return
    if bg is None:
        bg = BG
    bg = opaque(bg)
    _fill = over(_fill, bg)
    if border is None or bw <= 0:
        border, bw = _fill, 0
    else:
        border = over(border, bg)
    if r == 0:
        gfx.fill_rect(x, y, w, h, border if bw else _fill)
        if bw:
            gfx.fill_rect(x + bw, y + bw, w - 2 * bw, h - 2 * bw, _fill)
        return
    gfx.fill_rect(x + r, y, w - 2 * r, h, _fill)
    gfx.fill_rect(x, y + r, r, h - 2 * r, _fill)
    gfx.fill_rect(x + w - r, y + r, r, h - 2 * r, _fill)
    if bw:
        gfx.fill_rect(x + r, y, w - 2 * r, bw, border)
        gfx.fill_rect(x + r, y + h - bw, w - 2 * r, bw, border)
        gfx.fill_rect(x, y + r, bw, h - 2 * r, border)
        gfx.fill_rect(x + w - bw, y + r, bw, h - 2 * r, border)
    tl, tr, bl, br = _corners(r, _fill, border, bw, bg)
    gfx.blit(x, y, r, r, tl)
    gfx.blit(x + w - r, y, r, r, tr)
    gfx.blit(x, y + h - r, r, r, bl)
    gfx.blit(x + w - r, y + h - r, r, r, br)


def circle(cx, cy, radius, fill, border=None, bw=0, bg=None):
    """A smooth filled circle (optionally with a border ring)."""
    box(cx - radius, cy - radius, 2 * radius, 2 * radius, fill, border, bw, radius, bg)


def set_rounded(radius):
    """Change the corner radius of all widgets (0 = square corners) and redraw."""
    global RADIUS
    RADIUS = max(0, int(radius))
    for scr in _stack:
        scr._full_redraw = True


class Widget:
    """Base class. Subclasses implement draw() and, if interactive, key/activate/touch."""
    focusable = False
    expand_w = False               # grows in width inside layouts
    expand_h = False               # grows in height inside layouts
    focus_ring = True              # draw the focus ring around the whole widget

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.enabled = True
        self.visible = True
        self.focused = False
        self.screen = None
        self._dirty = True
        self._old_w = w
        self._old_h = h

    def invalidate(self):
        """Mark for redraw on the next frame."""
        self._dirty = True

    def contains(self, px, py):
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def move(self, x, y):
        """Place the widget at a fixed position (when not using layouts)."""
        self.x, self.y = x, y
        self.invalidate()
        return self

    def resize(self, w, h):
        self._old_w = max(self._old_w, self.w)
        self._old_h = max(self._old_h, self.h)
        self.w, self.h = w, h
        self.invalidate()

    def expanding(self, w=True, h=False):
        """Let the widget grow inside layouts; returns the widget for chaining."""
        self.expand_w, self.expand_h = w, h
        return self

    # ----- layout protocol -----

    def hint(self):
        """Natural size (w, h)."""
        return self.w, self.h

    def expands(self, horizontal):
        return self.expand_w if horizontal else self.expand_h

    def set_geometry(self, x, y, w, h):
        self.x, self.y = x, y
        if (w, h) != (self.w, self.h):
            self.resize(w, h)
        self.invalidate()

    def widgets(self):
        return [self]

    # ----- drawing -----

    def paint(self):
        """Erase the area (including the focus ring) and draw the widget."""
        bg = self.screen.bg if self.screen else BG
        w = max(self.w, self._old_w)
        h = max(self.h, self._old_h)
        gfx.fill_rect(self.x - 4, self.y - 4, w + 8, h + 8, opaque(bg))
        self._old_w, self._old_h = self.w, self.h
        if self.visible:
            if self.focused and self.focus_ring:
                box(self.x - 4, self.y - 4, self.w + 8, self.h + 8, bg, ACCENT, 2,
                    RADIUS + 4 if RADIUS else 0, bg)
            self.draw()
        self._dirty = False

    def bg(self):
        """The color around the widget (for blending rounded corners)."""
        return self.screen.bg if self.screen else BG

    def draw(self):
        pass

    # Input hooks; key() returns True if the key was used by the widget
    def key(self, down):
        return False

    def activate(self):
        pass

    def touch(self, x, y, first):
        pass

    def touch_end(self, inside):
        if inside:
            self.activate()


# ---------- widgets ----------

class Label(Widget):
    """Text. set_text() changes it. w reserves a width (e.g. for text that changes),
    align is "left", "center" or "right" inside that width."""

    def __init__(self, text="", color=TEXT, scale=SCALE, w=None, align="left", x=0, y=0):
        self.text = text
        self.color = color
        self.scale = scale
        self.min_w = w or 0
        self.align = align
        Widget.__init__(self, x, y, *self._natural())

    def _natural(self):
        return (max(self.min_w, _text_w(self.text, self.scale)),
                gfx.FONT_HEIGHT * self.scale * _lines(self.text))

    def hint(self):
        return self._natural()

    def set_text(self, text, color=None):
        if color is not None:
            self.color = color
        if text == self.text and color is None:
            return
        self.text = text
        nw, nh = self._natural()
        if self.expand_w:
            nw = max(nw, self.w)
        self.resize(nw, nh)

    def draw(self):
        tw = _text_w(self.text, self.scale)
        x = self.x
        if self.align == "right":
            x += self.w - tw
        elif self.align == "center":
            x += (self.w - tw) // 2
        text(x, self.y, self.text, self.color if self.enabled else DISABLED, self.scale)


class Button(Widget):
    """Push button. on_click() is called when it is activated."""
    focusable = True

    def __init__(self, text, on_click=None, w=None, x=0, y=0):
        self.text = text
        self.on_click = on_click
        self._pressed = False
        width = w if w is not None else _text_w(text) + 48
        self.min_w = width
        Widget.__init__(self, x, y, width, CHAR_H + 20)

    def hint(self):
        return self.min_w, CHAR_H + 20

    def draw(self):
        fill = ACCENT if self._pressed else (PANEL_HI if self.focused else PANEL)
        box(self.x, self.y, self.w, self.h, fill, None if self._pressed else BORDER, 1, bg=self.bg())
        tw = _text_w(self.text)
        color = ACCENT_TEXT if self._pressed else (TEXT if self.enabled else DISABLED)
        text(self.x + (self.w - tw) // 2, self.y + 10, self.text, color, SCALE)

    def activate(self):
        if not self.enabled:
            return
        self._pressed = True             # short visual feedback
        self.paint()
        gfx.present()
        switch.sleep_ms(80)
        self._pressed = False
        self.paint()                     # back to normal before the callback opens a dialog
        if self.on_click:
            self.on_click()


class Checkbox(Widget):
    """Check box with a label. on_change(checked) is called when toggled."""
    focusable = True

    def __init__(self, text, checked=False, on_change=None, x=0, y=0):
        self.text = text
        self.checked = checked
        self.on_change = on_change
        Widget.__init__(self, x, y, CHAR_H + 16 + _text_w(text), CHAR_H)

    def hint(self):
        return CHAR_H + 16 + _text_w(self.text), CHAR_H

    def set(self, checked):
        if checked != self.checked:
            self.checked = checked
            self.invalidate()

    def draw(self):
        size = CHAR_H - 4
        x, y = self.x, self.y + 2
        r = min(RADIUS, 6)
        if self.checked:
            box(x, y, size, size, ACCENT if self.enabled else DISABLED, radius=r, bg=self.bg())
            for d in (-1, 0, 1):                         # a thick check mark
                gfx.line(x + 6, y + 14 + d, x + 11, y + 19 + d, ACCENT_TEXT)
                gfx.line(x + 11, y + 19 + d, x + 21, y + 8 + d, ACCENT_TEXT)
        else:
            box(x, y, size, size, PANEL_HI if self.focused else PANEL,
                ACCENT if self.focused else MUTED, 2, r, self.bg())
        text(self.x + CHAR_H + 16, self.y, self.text, TEXT if self.enabled else DISABLED, SCALE)

    def activate(self):
        if not self.enabled:
            return
        self.checked = not self.checked
        self.invalidate()
        if self.on_change:
            self.on_change(self.checked)


class Slider(Widget):
    """Horizontal slider. Left/right (or dragging) changes the value.
    on_change(value) is called on every change. w is the minimum width."""
    focusable = True
    expand_w = True

    def __init__(self, value=0, minimum=0, maximum=100, step=1, on_change=None, w=300, x=0, y=0):
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self.value = self._clamp(value)
        self.on_change = on_change
        self.min_w = w
        Widget.__init__(self, x, y, w, CHAR_H)

    def hint(self):
        return self.min_w, CHAR_H

    def _clamp(self, v):
        return max(self.minimum, min(self.maximum, v))

    def _track(self):
        # the knob (radius 12) must stay inside the widget; the value text takes the right part
        return self.x + 12, self.w - _text_w(str(self.maximum)) - 48

    def set(self, value):
        value = self._clamp(value)
        if value != self.value:
            self.value = value
            self.invalidate()
            if self.on_change:
                self.on_change(value)

    def draw(self):
        tx, tw = self._track()
        cy = self.y + self.h // 2
        span = self.maximum - self.minimum
        pos = tx + (tw * (self.value - self.minimum) // span if span else 0)
        bg = self.bg()
        box(tx, cy - 3, tw, 6, BORDER, radius=3 if RADIUS else 0, bg=bg)
        box(tx, cy - 3, pos - tx + 3, 6, ACCENT if self.enabled else DISABLED,
            radius=3 if RADIUS else 0, bg=bg)
        if RADIUS:
            circle(pos, cy, 11, ACCENT_TEXT, ACCENT if self.focused else BORDER, 2, bg)
        else:
            fill(pos - 6, cy - 12, 12, 24, ACCENT if self.focused else MUTED)
        text(tx + tw + 24, self.y, str(self.value), TEXT if self.enabled else DISABLED, SCALE)

    def key(self, down):
        if not self.enabled:
            return False
        if down & switch.LEFT:
            self.set(self.value - self.step)
            return True
        if down & switch.RIGHT:
            self.set(self.value + self.step)
            return True
        return False

    def touch(self, x, y, first):
        if not self.enabled:
            return
        tx, tw = self._track()
        frac = (x - tx) / tw if tw else 0
        raw = self.minimum + frac * (self.maximum - self.minimum)
        self.set(self._clamp(int(round(raw / self.step)) * self.step))

    def touch_end(self, inside):
        pass


class ProgressBar(Widget):
    """Progress indicator, value from 0.0 to 1.0. Not focusable. w is the minimum width."""
    expand_w = True

    def __init__(self, value=0.0, show_percent=True, w=300, x=0, y=0):
        self.value = value
        self.show_percent = show_percent
        self.min_w = w
        Widget.__init__(self, x, y, w, CHAR_H)

    def hint(self):
        return self.min_w, CHAR_H

    def set(self, value):
        value = max(0.0, min(1.0, value))
        if value != self.value:
            self.value = value
            self.invalidate()

    def draw(self):
        r = min(RADIUS, self.h // 2)
        box(self.x, self.y, self.w, self.h, PANEL, BORDER, 1, r, self.bg())
        fw = int(self.w * self.value)
        if fw > 0:
            box(self.x, self.y, max(fw, 2 * r), self.h, ACCENT, radius=r, bg=PANEL)
        if self.show_percent:
            label = "%d%%" % int(self.value * 100 + 0.5)
            text(self.x + (self.w - _text_w(label)) // 2, self.y, label, TEXT, SCALE)


class ListBox(Widget):
    """Scrollable list of strings. Up/down moves the selection (at the edges the
    focus moves on to other widgets); A or a tap calls on_select(index, item).
    Dragging a finger scrolls the list instead of selecting (touch only).
    on_change(index, item) is called whenever the selection moves.
    rows and w are the minimum size; inside layouts the list grows in both directions."""
    focusable = True
    expand_w = True
    expand_h = True
    ROW_H = CHAR_H + 8

    def __init__(self, items=None, rows=6, on_select=None, on_change=None, w=300, x=0, y=0):
        self.items = list(items or [])
        self.rows = rows
        self.min_rows = rows
        self.min_w = w
        self.selected = 0
        self.top = 0
        self.on_select = on_select
        self.on_change = on_change
        self._dragging = False
        Widget.__init__(self, x, y, w, rows * self.ROW_H + 8)

    def hint(self):
        return self.min_w, self.min_rows * self.ROW_H + 8

    def resize(self, w, h):
        self.rows = max(1, (h - 8) // self.ROW_H)
        if self.selected >= self.top + self.rows:
            self.top = self.selected - self.rows + 1
        Widget.resize(self, w, self.rows * self.ROW_H + 8)

    def set_items(self, items):
        self.items = list(items)
        self.selected = min(self.selected, max(0, len(self.items) - 1))
        self.top = min(self.top, self.selected)
        self.invalidate()

    def select(self, index):
        """Move the selection to index (and scroll to it)."""
        self._select(index)

    def selected_item(self):
        return self.items[self.selected] if self.items else None

    def _select(self, index):
        if not self.items:
            return
        index = max(0, min(len(self.items) - 1, index))
        if index == self.selected:
            return
        self.selected = index
        if index < self.top:
            self.top = index
        elif index >= self.top + self.rows:
            self.top = index - self.rows + 1
        self.invalidate()
        if self.on_change:
            self.on_change(index, self.items[index])

    def draw(self):
        box(self.x, self.y, self.w, self.h, PANEL, BORDER, 1, bg=self.bg())
        for row in range(self.rows):
            i = self.top + row
            if i >= len(self.items):
                break
            ry = self.y + 4 + row * self.ROW_H
            selected = i == self.selected
            if selected:
                box(self.x + 4, ry, self.w - 8, self.ROW_H, ACCENT if self.focused else SELECTION,
                    radius=max(0, RADIUS - 2), bg=PANEL)
            label = elide(str(self.items[i]), self.w - 32)
            text(self.x + 12, ry + 4, label, ACCENT_TEXT if selected and self.focused else TEXT, SCALE)
        if len(self.items) > self.rows:              # scroll indicator
            bar_h = max(16, (self.h - 8) * self.rows // len(self.items))
            bar_y = self.y + 4 + (self.h - 8 - bar_h) * self.top // (len(self.items) - self.rows)
            box(self.x + self.w - 10, bar_y, 6, bar_h, MUTED, radius=3 if RADIUS else 0, bg=PANEL)

    def key(self, down):
        if down & switch.UP and self.selected > 0:
            self._select(self.selected - 1)
            return True
        if down & switch.DOWN and self.selected < len(self.items) - 1:
            self._select(self.selected + 1)
            return True
        return False

    def activate(self):
        if self.items and self.on_select:
            self.on_select(self.selected, self.items[self.selected])

    def _max_top(self):
        return max(0, len(self.items) - self.rows)

    def touch(self, x, y, first):
        if first:
            self._dragging = False
            self._drag_y = y
            self._drag_top = self.top
            row = (y - self.y - 4) // self.ROW_H
            self._select(self.top + row)
            return
        dy = y - self._drag_y
        if not self._dragging and abs(dy) < _DRAG_PX:
            return
        self._dragging = True
        rows = abs(dy) // self.ROW_H
        top = max(0, min(self._max_top(), self._drag_top + (-rows if dy > 0 else rows)))
        if top != self.top:
            self.top = top
            self.invalidate()

    def touch_end(self, inside):
        dragging = self._dragging
        self._dragging = False
        if inside and not dragging:
            self.activate()


# ---------- layouts ----------

def _place(item, x, y, w, h, align):
    """Puts an item into a cell. Nested layouts always get the whole cell (like in Qt);
    expanding widgets fill it, others keep their natural size, aligned horizontally
    by `align` and centered vertically."""
    if isinstance(item, Layout):
        item.set_geometry(x, y, w, h)
        return
    hw, hh = item.hint()
    iw = w if item.expands(True) else min(hw, w)
    ih = h if item.expands(False) else min(hh, h)
    if align == "center":
        x += (w - iw) // 2
    elif align == "right":
        x += w - iw
    y += (h - ih) // 2
    item.set_geometry(x, y, iw, ih)


def _distribute(sizes, extra, weights):
    """Adds `extra` pixels to sizes in proportion to weights (in place)."""
    total = sum(weights)
    if extra <= 0 or total <= 0:
        return
    given = 0
    last = 0
    for i, wgt in enumerate(weights):
        if wgt > 0:
            add = extra * wgt // total
            sizes[i] += add
            given += add
            last = i
    sizes[last] += extra - given       # rounding remainder


class Spacer:
    """Empty space inside a layout (see Layout.add_stretch / add_spacing)."""

    def __init__(self, w=0, h=0):
        self.w, self.h = w, h

    def hint(self):
        return self.w, self.h

    def expands(self, horizontal):
        return False

    def set_geometry(self, x, y, w, h):
        pass

    def widgets(self):
        return []


class Layout:
    """Base class of VBox, HBox and Grid."""

    def __init__(self, spacing=16):
        self.spacing = spacing
        self.x = self.y = self.w = self.h = 0

    def widgets(self):
        result = []
        for item in self._children():
            result.extend(item.widgets())
        return result


class _Box(Layout):
    HORIZONTAL = False

    def __init__(self, spacing=16):
        Layout.__init__(self, spacing)
        self.items = []                # (item, stretch, align)

    def add(self, item, stretch=0, align="left"):
        """Add a widget or a nested layout; returns it. stretch > 0 gives it a share
        of the free space; align ("left", "center", "right") applies if it does not fill."""
        self.items.append((item, stretch, align))
        return item

    def add_stretch(self, stretch=1):
        """Flexible empty space that pushes the other items apart."""
        self.items.append((Spacer(), stretch, "left"))

    def add_spacing(self, size):
        """Fixed empty space."""
        self.items.append((Spacer(size, size), 0, "left"))

    def _children(self):
        return [item for item, _, _ in self.items]

    def hint(self):
        main = cross = 0
        for item, _, _ in self.items:
            w, h = item.hint()
            m, c = (w, h) if self.HORIZONTAL else (h, w)
            main += m
            cross = max(cross, c)
        main += self.spacing * max(0, len(self.items) - 1)
        return (main, cross) if self.HORIZONTAL else (cross, main)

    def expands(self, horizontal):
        for item, stretch, _ in self.items:
            if item.expands(horizontal) or (stretch > 0 and horizontal == self.HORIZONTAL):
                return True
        return False

    def set_geometry(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        if not self.items:
            return
        hor = self.HORIZONTAL
        sizes = [item.hint()[0 if hor else 1] for item, _, _ in self.items]
        avail = (w if hor else h) - self.spacing * (len(self.items) - 1)
        weights = [stretch for _, stretch, _ in self.items]
        if not any(weights):
            weights = [1 if item.expands(hor) else 0 for item, _, _ in self.items]
        _distribute(sizes, avail - sum(sizes), weights)

        pos = x if hor else y
        for (item, _, align), size in zip(self.items, sizes):
            if hor:
                _place(item, pos, y, size, h, align)
            else:
                _place(item, x, pos, w, size, align)
            pos += size + self.spacing


class VBox(_Box):
    """Items one below another."""
    HORIZONTAL = False


class HBox(_Box):
    """Items side by side."""
    HORIZONTAL = True


class Grid(Layout):
    """Items in rows and columns. Column widths and row heights come from the largest
    item in them; free space goes to stretched (or else expanding) columns and rows."""

    def __init__(self, spacing=16, row_spacing=None):
        Layout.__init__(self, spacing)
        self.row_spacing = spacing if row_spacing is None else row_spacing
        self.cells = []                # (item, row, col, rowspan, colspan, align)
        self.col_stretch = {}
        self.row_stretch = {}

    def add(self, item, row, col, rowspan=1, colspan=1, align="left"):
        """Add a widget or a nested layout at (row, col); returns it."""
        self.cells.append((item, row, col, rowspan, colspan, align))
        return item

    def set_column_stretch(self, col, stretch):
        self.col_stretch[col] = stretch

    def set_row_stretch(self, row, stretch):
        self.row_stretch[row] = stretch

    def _children(self):
        ordered = sorted(self.cells, key=lambda c: (c[1], c[2]))   # focus order: by rows
        return [c[0] for c in ordered]

    def _size(self):
        rows = cols = 0
        for _, r, c, rs, cs, _ in self.cells:
            rows = max(rows, r + rs)
            cols = max(cols, c + cs)
        return rows, cols

    def _minimums(self):
        rows, cols = self._size()
        col_w = [0] * cols
        row_h = [0] * rows
        for item, r, c, rs, cs, _ in self.cells:
            w, h = item.hint()
            if cs == 1:
                col_w[c] = max(col_w[c], w)
            if rs == 1:
                row_h[r] = max(row_h[r], h)
        # items spanning several cells: widen the last spanned column/row if needed
        for item, r, c, rs, cs, _ in self.cells:
            w, h = item.hint()
            if cs > 1:
                have = sum(col_w[c:c + cs]) + self.spacing * (cs - 1)
                if w > have:
                    col_w[c + cs - 1] += w - have
            if rs > 1:
                have = sum(row_h[r:r + rs]) + self.row_spacing * (rs - 1)
                if h > have:
                    row_h[r + rs - 1] += h - have
        return col_w, row_h

    def hint(self):
        col_w, row_h = self._minimums()
        return (sum(col_w) + self.spacing * max(0, len(col_w) - 1),
                sum(row_h) + self.row_spacing * max(0, len(row_h) - 1))

    def _weights(self, count, stretch, horizontal):
        weights = [stretch.get(i, 0) for i in range(count)]
        if any(weights):
            return weights
        weights = [0] * count
        for item, r, c, rs, cs, _ in self.cells:
            if item.expands(horizontal):
                weights[c if horizontal else r] = 1
        return weights

    def expands(self, horizontal):
        if (self.col_stretch if horizontal else self.row_stretch):
            return True
        return any(item.expands(horizontal) for item, _, _, _, _, _ in self.cells)

    def set_geometry(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        if not self.cells:
            return
        col_w, row_h = self._minimums()
        rows, cols = len(row_h), len(col_w)
        _distribute(col_w, w - self.hint()[0], self._weights(cols, self.col_stretch, True))
        _distribute(row_h, h - self.hint()[1], self._weights(rows, self.row_stretch, False))

        col_x = [x]
        for c in range(1, cols):
            col_x.append(col_x[-1] + col_w[c - 1] + self.spacing)
        row_y = [y]
        for r in range(1, rows):
            row_y.append(row_y[-1] + row_h[r - 1] + self.row_spacing)

        for item, r, c, rs, cs, align in self.cells:
            cw = sum(col_w[c:c + cs]) + self.spacing * (cs - 1)
            ch = sum(row_h[r:r + rs]) + self.row_spacing * (rs - 1)
            _place(item, col_x[c], row_y[r], cw, ch, align)


# ---------- screen ----------

class Screen:
    """A set of widgets with a title bar and an event loop.

    title   - text in the title bar ("" for none)
    hint    - help line at the bottom
    panel   - (x, y, w, h) to draw as a dialog over the previous screen instead of full screen
    on_back - called on B; by default B closes the screen
    on_key  - on_key(down) is called first for every key press; return True to consume it
    """

    def __init__(self, title="", hint="A: select   B: back", panel=None, on_back=None, on_key=None):
        self.title = title
        self.hint = hint
        self.panel = panel
        self.on_back = on_back
        self.on_key = on_key
        self.bg = DIALOG if panel else BG
        self.widgets = []
        self.focus = None
        self.layout = None
        self.margin = MARGIN
        self.result = None
        self._closed = False
        self._full_redraw = True
        self._dimmed = False               # a dialog dims the screen below it once
        self._touching = False
        self._touch_w = None
        self._touch_pos = (0, 0)
        self._repeat_at = 0

    # ----- building -----

    def add(self, widget):
        """Add a widget placed by coordinates (x=, y= or move()); returns it."""
        widget.screen = self
        self.widgets.append(widget)
        if self.focus is None and widget.focusable and widget.enabled:
            self.set_focus(widget)
        return widget

    def set_layout(self, layout, margin=MARGIN):
        """Place a layout over the whole screen (between the title and the hint line)
        and add all its widgets. Build the layout completely before calling this."""
        self.layout = layout
        self.margin = margin
        for w in layout.widgets():
            if w not in self.widgets:
                self.add(w)
        self.relayout()
        return layout

    def content_rect(self):
        """(x, y, w, h) of the area a layout occupies."""
        m = self.margin
        if self.panel:
            px, py, pw, ph = self.panel
            top = py + (TITLE_H if self.title else 0) + m
            return px + m, top, pw - 2 * m, py + ph - m - top
        top = (TITLE_H if self.title else 0) + m
        bottom = gfx.HEIGHT - (FOOTER_H if self.hint else 0) - m // 2
        return m, top, gfx.WIDTH - 2 * m, bottom - top

    def relayout(self):
        """Recompute widget positions (e.g. after adding widgets to the layout)."""
        if self.layout:
            for w in self.layout.widgets():
                if w not in self.widgets:
                    self.add(w)
            self.layout.set_geometry(*self.content_rect())
        self._full_redraw = True

    def set_focus(self, widget):
        if widget is self.focus:
            return
        if self.focus:
            self.focus.focused = False
            self.focus.invalidate()
        self.focus = widget
        if widget:
            widget.focused = True
            widget.invalidate()

    def close(self, result=None):
        """Leave run(); run() returns result."""
        self.result = result
        self._closed = True

    def update(self):
        """Called once per frame; override (or assign) to refresh widgets, e.g. from USB data."""
        pass

    def refresh_now(self):
        """Draw pending changes immediately, e.g. a status label during a long operation."""
        self._paint()
        gfx.present()

    # ----- drawing -----

    def _redraw(self):
        if self.panel:
            px, py, pw, ph = self.panel
            if not self._dimmed:                  # once: the screen below stays as it is
                self._dimmed = True
                fill(0, 0, gfx.WIDTH, gfx.HEIGHT, OVERLAY)
            box(px - 2, py - 2, pw + 4, ph + 4, self.bg, BORDER, 2,
                RADIUS + 6 if RADIUS else 0, BG)
            if self.title:
                text(px + 24, py + 12, self.title, TEXT, SCALE)
                fill(px + 16, py + TITLE_H - 1, pw - 32, 1, BORDER)
        else:
            gfx.clear(BG)
            if self.title:
                gfx.fill_gradient(0, 0, gfx.WIDTH, TITLE_H, BAR_TOP, BAR_LOW)
                fill(0, TITLE_H - 1, gfx.WIDTH, 1, BORDER)
                text(24, 12, self.title, TEXT, SCALE)
            if self.hint:
                text(24, gfx.HEIGHT - FOOTER_H + 12, self.hint, MUTED, 1)
        for w in self.widgets:
            w.invalidate()
        self._full_redraw = False

    def _paint(self):
        painted = False
        if self._full_redraw:
            self._redraw()
            painted = True
        for w in self.widgets:
            if w._dirty:
                w.paint()
                painted = True
        return painted

    # ----- input -----

    def _read_keys(self):
        down = switch.buttons_down()
        held = switch.buttons() & _DIRS
        now = switch.ticks_ms()
        if down & _DIRS:
            self._repeat_at = now + _REPEAT_DELAY
        elif held and now >= self._repeat_at:
            down |= held
            self._repeat_at = now + _REPEAT_RATE
        return down

    def _focusable(self):
        return [w for w in self.widgets if w.focusable and w.enabled and w.visible]

    def _move_focus(self, dx, dy):
        cands = self._focusable()
        if not cands:
            return
        f = self.focus
        if f not in cands:
            self.set_focus(cands[0])
            return
        fx, fy = f.center()
        best, best_score = None, 0
        for w in cands:
            if w is f:
                continue
            wx, wy = w.center()
            # Distance between edges in the direction of movement, and the gap
            # sideways (0 if the widgets overlap sideways, e.g. a column of widgets)
            if dx:
                along = w.x - (f.x + f.w) if dx > 0 else f.x - (w.x + w.w)
                across = max(0, w.y - (f.y + f.h), f.y - (w.y + w.h))
                off = abs(wy - fy)
            else:
                along = w.y - (f.y + f.h) if dy > 0 else f.y - (w.y + w.h)
                across = max(0, w.x - (f.x + f.w), f.x - (w.x + w.w))
                off = abs(wx - fx)
            if along < 0:
                # overlapping along the movement axis: accept only widgets in the same
                # row/column whose center is further in the wanted direction
                if across > 0 or (wx - fx) * dx + (wy - fy) * dy <= 0:
                    continue
                along = 0
            score = along + 2 * across + off // 4
            if best is None or score < best_score:
                best, best_score = w, score
        if best:
            self.set_focus(best)

    def _widget_at(self, x, y):
        for w in self.widgets:
            if w.visible and w.contains(x, y):
                return w
        return None

    def _handle_touch(self):
        pts = switch.touches()
        if pts:
            x, y = pts[0]
            self._touch_pos = (x, y)
            if not self._touching:
                self._touching = True
                w = self._widget_at(x, y)
                self._touch_w = w
                if w and w.focusable and w.enabled:
                    self.set_focus(w)
                    w.touch(x, y, True)
            elif self._touch_w and self._touch_w.enabled:
                self._touch_w.touch(x, y, False)
        elif self._touching:
            self._touching = False
            w = self._touch_w
            self._touch_w = None
            if w and w.focusable and w.enabled:
                w.touch_end(w.contains(*self._touch_pos))

    def _handle_keys(self, down):
        if self.on_key and self.on_key(down):
            return
        f = self.focus
        if f and f.enabled and f.key(down):
            return
        if down & switch.UP:
            self._move_focus(0, -1)
        elif down & switch.DOWN:
            self._move_focus(0, 1)
        elif down & switch.LEFT:
            self._move_focus(-1, 0)
        elif down & switch.RIGHT:
            self._move_focus(1, 0)
        if down & switch.A and f and f.enabled:
            f.activate()
        if down & switch.B:
            if self.on_back:
                self.on_back()
            else:
                self.close()

    # ----- event loop -----

    def run(self):
        """Show the screen and process input until close(). Returns the close() result."""
        self._closed = False
        self._full_redraw = True
        _stack.append(self)
        switch.buttons_down()                      # ignore presses made before the screen opened
        try:
            while not self._closed and switch.running():
                down = self._read_keys()
                if down:
                    self._handle_keys(down)
                if not self._closed:
                    self._handle_touch()
                    self.update()
                if self._closed:
                    break
                if self._paint():
                    gfx.present()                  # waits for the display, ~60 fps
                else:
                    switch.sleep_ms(16)
        finally:
            _stack.pop()
            if _stack:
                _stack[-1]._full_redraw = True     # the dialog covered part of the parent
        return self.result


# ---------- dialogs ----------

def _dialog_screen(title, body, min_w=0):
    """A dialog centered on the screen, sized to fit the `body` layout."""
    m = 40
    bw, bh = body.hint()
    pw = min(max(bw, min_w, _text_w(title) + 40) + 2 * m, gfx.WIDTH - 80)
    ph = min(bh + (TITLE_H if title else 0) + 2 * m, gfx.HEIGHT - 80)
    dlg = Screen(title, hint="", panel=((gfx.WIDTH - pw) // 2, (gfx.HEIGHT - ph) // 2, pw, ph))
    dlg.set_layout(body, margin=m)
    return dlg


def _dialog(title, text, buttons):
    """A message with a row of buttons; returns the chosen index or None (B)."""
    body = VBox(spacing=32)
    body.add(Label(wrap(text, 56)))
    row = body.add(HBox(spacing=24))
    row.add_stretch()
    btn_w = max(_text_w(b) for b in buttons) + 48
    dlg = None
    for i, name in enumerate(buttons):
        row.add(Button(name, w=btn_w, on_click=lambda i=i: dlg.close(i)))
    row.add_stretch()
    dlg = _dialog_screen(title, body)
    return dlg.run()


def message(text, title="Message"):
    """Show a message with an OK button."""
    _dialog(title, text, ["OK"])


def confirm(text, title="Confirm", yes="Yes", no="No"):
    """Ask a yes/no question; returns True for yes (B counts as no)."""
    return _dialog(title, text, [yes, no]) == 0


def choose(title, items, rows=8):
    """Let the user pick an item from a list; returns its index, or None on B."""
    items = [str(i) for i in items]
    width = max([_text_w(i) for i in items] + [400]) + 48
    body = VBox()
    dlg = None
    body.add(ListBox(items, rows=max(1, min(rows, len(items))), w=width,
                     on_select=lambda i, item: dlg.close(i)))
    dlg = _dialog_screen(title, body)
    return dlg.run()
