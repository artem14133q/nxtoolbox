"""keys - USB keyboard and mouse for scripts (on top of the built-in usbinput module).

    import keys

    kb = keys.Keyboard()                  # US and Russian layouts, Alt+Shift switches
    mouse = keys.Mouse()
    while switch.running():
        for ev in kb.poll():              # new presses and auto-repeat
            if ev.char:                   # a printable character (layout, Shift, Caps Lock)
                text += ev.char
            elif ev.code == keys.BACKSPACE:
                text = text[:-1]
            elif ev.code == keys.ENTER and ev.ctrl:
                ...
        m = mouse.poll()                  # x, y, dx, dy, wheel, buttons, pressed, released
        if m.pressed & keys.MOUSE_LEFT:
            ...

Key codes are USB HID usage codes; names for the common keys are defined below.
"""
import switch
import usbinput

# ---------- key codes (USB HID usage page 7) ----------

A, B, C, D, E, F, G, H, I, J, K, L, M = range(0x04, 0x11)
N, O, P, Q, R, S, T, U, V, W, X, Y, Z = range(0x11, 0x1E)
N1, N2, N3, N4, N5, N6, N7, N8, N9, N0 = range(0x1E, 0x28)
ENTER, ESCAPE, BACKSPACE, TAB, SPACE = 0x28, 0x29, 0x2A, 0x2B, 0x2C
MINUS, EQUAL, LEFT_BRACKET, RIGHT_BRACKET, BACKSLASH = 0x2D, 0x2E, 0x2F, 0x30, 0x31
SEMICOLON, QUOTE, GRAVE, COMMA, PERIOD, SLASH, CAPS_LOCK = 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39
F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12 = range(0x3A, 0x46)
PRINT_SCREEN, SCROLL_LOCK, PAUSE, INSERT, HOME, PAGE_UP = 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B
DELETE, END, PAGE_DOWN, RIGHT, LEFT, DOWN, UP = 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52
NUM_LOCK, KP_ENTER = 0x53, 0x58
LEFT_CTRL, LEFT_SHIFT, LEFT_ALT, LEFT_GUI = 0xE0, 0xE1, 0xE2, 0xE3
RIGHT_CTRL, RIGHT_SHIFT, RIGHT_ALT, RIGHT_GUI = 0xE4, 0xE5, 0xE6, 0xE7

MOUSE_LEFT = usbinput.MOUSE_LEFT
MOUSE_RIGHT = usbinput.MOUSE_RIGHT
MOUSE_MIDDLE = usbinput.MOUSE_MIDDLE
MOUSE_BACK = usbinput.MOUSE_BACK
MOUSE_FORWARD = usbinput.MOUSE_FORWARD

_MODIFIER_KEYS = (LEFT_CTRL, LEFT_SHIFT, LEFT_ALT, LEFT_GUI,
                  RIGHT_CTRL, RIGHT_SHIFT, RIGHT_ALT, RIGHT_GUI)

_NAMES = {ENTER: "Enter", ESCAPE: "Esc", BACKSPACE: "Backspace", TAB: "Tab", SPACE: "Space",
          CAPS_LOCK: "CapsLock", PRINT_SCREEN: "PrintScreen", SCROLL_LOCK: "ScrollLock",
          PAUSE: "Pause", INSERT: "Insert", HOME: "Home", PAGE_UP: "PageUp", DELETE: "Delete",
          END: "End", PAGE_DOWN: "PageDown", RIGHT: "Right", LEFT: "Left", DOWN: "Down",
          UP: "Up", NUM_LOCK: "NumLock", KP_ENTER: "KpEnter",
          LEFT_CTRL: "LCtrl", LEFT_SHIFT: "LShift", LEFT_ALT: "LAlt", LEFT_GUI: "LGui",
          RIGHT_CTRL: "RCtrl", RIGHT_SHIFT: "RShift", RIGHT_ALT: "RAlt", RIGHT_GUI: "RGui"}


# ---------- layouts: characters for codes 0x04..0x38 (normal, with Shift) ----------

_UNICODE = len("é") == 1            # str counts characters (else: UTF-8 bytes)


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


def _table(normal, shifted):
    normal, shifted = _chars(normal), _chars(shifted)
    return {0x04 + i: (normal[i], shifted[i]) for i in range(len(normal)) if normal[i] != " "}


# codes 0x04..0x1D letters, 0x1E..0x27 digits, 0x2C space, 0x2D..0x38 punctuation;
# " " marks keys without a character (Enter, Esc, Backspace, Tab)
_US_NORMAL = "abcdefghijklmnopqrstuvwxyz1234567890    " + " -=[]\\#;'`,./"
_US_SHIFT = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()    " + " _+{}|~:\"~<>?"
_RU_NORMAL = "фисвуапршолдьтщзйкыегмцчня1234567890    " + " -=хъ\\\\жэё,.."
_RU_SHIFT = "ФИСВУАПРШОЛДЬТЩЗЙКЫЕГМЦЧНЯ!\"№;%:?*()    " + " _+ХЪ//ЖЭЁБЮ,"

LAYOUTS = {"us": _table(_US_NORMAL, _US_SHIFT), "ru": _table(_RU_NORMAL, _RU_SHIFT)}
# the Russian keys for , . on the "б ю" keys and the one next to them
LAYOUTS["ru"][COMMA] = ("б", "Б")
LAYOUTS["ru"][PERIOD] = ("ю", "Ю")
LAYOUTS["ru"][SLASH] = (".", ",")
for _t in LAYOUTS.values():
    _t[SPACE] = (" ", " ")

# keypad digits and operators (with Num Lock on)
_KEYPAD = {0x54: "/", 0x55: "*", 0x56: "-", 0x57: "+", 0x59: "1", 0x5A: "2", 0x5B: "3",
           0x5C: "4", 0x5D: "5", 0x5E: "6", 0x5F: "7", 0x60: "8", 0x61: "9", 0x62: "0", 0x63: "."}


def name(code):
    """Readable name of a key code: "A", "7", "Enter", "F5"..."""
    if A <= code <= Z:
        return chr(ord("A") + code - A)
    if N1 <= code <= N9:
        return str(code - N1 + 1)
    if code == N0:
        return "0"
    if F1 <= code <= F12:
        return "F%d" % (code - F1 + 1)
    if code in _NAMES:
        return _NAMES[code]
    if code in LAYOUTS["us"]:
        return LAYOUTS["us"][code][0]
    return "0x%02X" % code


class KeyEvent:
    """A key press (or auto-repeat). char is the typed character or None."""

    def __init__(self, code, char, mods, repeat):
        self.code = code
        self.char = char
        self.mods = mods
        self.repeat = repeat
        self.ctrl = bool(mods & usbinput.MOD_CTRL)
        self.shift = bool(mods & usbinput.MOD_SHIFT)
        self.alt = bool(mods & (usbinput.MOD_LEFT_ALT | usbinput.MOD_RIGHT_ALT))

    def __repr__(self):
        return "KeyEvent(%s, %r%s)" % (name(self.code), self.char, ", repeat" if self.repeat else "")


class Keyboard:
    """Turns the raw keyboard state into key events with characters and auto-repeat.

    layouts - layout names to cycle through with Alt+Shift (see LAYOUTS)
    repeat_delay / repeat_rate - auto-repeat timing in ms (0 disables auto-repeat)
    """

    def __init__(self, layouts=("us", "ru"), repeat_delay=450, repeat_rate=40):
        self.layouts = list(layouts)
        self.layout = self.layouts[0]
        self.repeat_delay = repeat_delay
        self.repeat_rate = repeat_rate
        self.held = []
        self.mods = 0
        self._prev = set(usbinput.keys())    # keys held before we started are not presses
        self._repeat_key = None
        self._repeat_at = 0

    def next_layout(self):
        i = self.layouts.index(self.layout) if self.layout in self.layouts else -1
        self.layout = self.layouts[(i + 1) % len(self.layouts)]

    def char(self, code, mods):
        """The character a key types with the current layout and modifiers, or None."""
        if mods & (usbinput.MOD_CTRL | usbinput.MOD_LEFT_ALT | usbinput.MOD_GUI):
            return None                                  # shortcuts do not type
        if code in _KEYPAD:
            return _KEYPAD[code] if mods & usbinput.MOD_NUM_LOCK else None
        pair = LAYOUTS[self.layout].get(code)
        if not pair:
            return None
        shift = bool(mods & usbinput.MOD_SHIFT)
        if mods & usbinput.MOD_CAPS_LOCK and pair[0].lower() != pair[0].upper():
            shift = not shift                            # Caps Lock affects letters only
        return pair[1] if shift else pair[0]

    def poll(self):
        """New key presses since the previous call, plus auto-repeat of the last key held."""
        codes = usbinput.keys()
        self.mods = usbinput.modifiers()
        self.held = codes
        now = switch.ticks_ms()
        events = []
        current = set(codes)
        for code in codes:
            if code in self._prev:
                continue
            # Alt+Shift switches the layout (the key pressed second triggers it)
            if (code in (LEFT_SHIFT, RIGHT_SHIFT) and self.mods & usbinput.MOD_LEFT_ALT) or \
               (code == LEFT_ALT and self.mods & usbinput.MOD_SHIFT):
                self.next_layout()
            if code in _MODIFIER_KEYS:
                continue
            events.append(KeyEvent(code, self.char(code, self.mods), self.mods, False))
            self._repeat_key = code
            self._repeat_at = now + self.repeat_delay
        if self._repeat_key is not None and self._repeat_key not in current:
            self._repeat_key = None
        if self._repeat_key is not None and self.repeat_rate and now >= self._repeat_at:
            code = self._repeat_key
            events.append(KeyEvent(code, self.char(code, self.mods), self.mods, True))
            self._repeat_at = now + self.repeat_rate
        self._prev = current
        return events

    def is_down(self, code):
        """True if the key is held (as of the last poll())."""
        return code in self.held


class MouseState:
    def __init__(self, raw, pressed, released):
        self.x = raw["x"]
        self.y = raw["y"]
        self.dx = raw["dx"]
        self.dy = raw["dy"]
        self.wheel = raw["wheel"]
        self.wheel_h = raw["wheel_h"]
        self.buttons = raw["buttons"]
        self.connected = raw["connected"]
        self.pressed = pressed           # buttons pressed since the previous poll()
        self.released = released         # buttons released since the previous poll()


class Mouse:
    """Mouse state with pressed/released buttons since the previous poll()."""

    def __init__(self):
        self._buttons = usbinput.mouse()["buttons"]

    def poll(self):
        raw = usbinput.mouse()
        buttons = raw["buttons"]
        pressed = buttons & ~self._buttons
        released = self._buttons & ~buttons
        self._buttons = buttons
        return MouseState(raw, pressed, released)
