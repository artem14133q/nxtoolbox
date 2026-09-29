"""Keyboard and mouse test: type text, see held keys, move the mouse cursor.

Connect a USB keyboard and/or mouse to one of the dock's USB ports (the system's
keyboard/mouse support only sees devices there - a USB-C OTG adapter in handheld
mode is not recognized, even though the console still charges/hosts USB over it).
Alt+Shift switches between the US and Russian layouts. Esc or B on the Joy-Con quits.
"""
__NXTOOLBOX_MODULE__ = {
    "title": "Keyboard & mouse",
    "description": "USB keyboard and mouse test",
    "version": "1.0",
}

import switch
import gfx
import keys

BG = gfx.rgb(22, 26, 40)
PANEL = gfx.rgb(45, 53, 80)
MUTED = gfx.rgb(140, 148, 170)
ACCENT = gfx.rgb(80, 150, 255)
MAX_LINES = 8
LINE_CHARS = 70

kb = keys.Keyboard()
mouse = keys.Mouse()
lines = [""]
clicks = []                     # recent click markers: (x, y, color)
wheel_total = [0, 0]


def type_char(ch):
    if len(keys._chars(lines[-1])) >= LINE_CHARS:
        lines.append("")
    lines[-1] += ch


def backspace():
    if lines[-1]:
        lines[-1] = "".join(keys._chars(lines[-1])[:-1])
    elif len(lines) > 1:
        lines.pop()


def draw_mouse_buttons(x, y, buttons):
    names = [("L", keys.MOUSE_LEFT), ("M", keys.MOUSE_MIDDLE), ("R", keys.MOUSE_RIGHT),
             ("Back", keys.MOUSE_BACK), ("Fwd", keys.MOUSE_FORWARD)]
    for label, bit in names:
        w = gfx.text_width(label, 2) + 24
        on = buttons & bit
        gfx.fill_rect(x, y, w, 40, ACCENT if on else PANEL)
        gfx.text(x + 12, y + 4, label, gfx.WHITE if on else MUTED, 2)
        x += w + 8


while switch.running():
    if switch.buttons_down() & switch.B:
        break
    quit_now = False
    for ev in kb.poll():
        if ev.code == keys.ESCAPE:
            quit_now = True
        elif ev.code in (keys.ENTER, keys.KP_ENTER):
            lines.append("")
        elif ev.code == keys.BACKSPACE:
            backspace()
        elif ev.code == keys.TAB:
            type_char("    ")
        elif ev.char:
            type_char(ev.char)
    if quit_now:
        break
    while len(lines) > MAX_LINES:
        lines.pop(0)

    m = mouse.poll()
    wheel_total[0] += m.wheel
    wheel_total[1] += m.wheel_h
    for bit, color in ((keys.MOUSE_LEFT, gfx.GREEN), (keys.MOUSE_RIGHT, gfx.RED),
                       (keys.MOUSE_MIDDLE, gfx.YELLOW)):
        if m.pressed & bit:
            clicks.append((m.x, m.y, color))
    while len(clicks) > 12:
        clicks.pop(0)

    # ---------- draw ----------
    gfx.clear(BG)
    gfx.text(24, 16, "Keyboard & mouse", gfx.WHITE, 2)
    gfx.text(24, 56, "Alt+Shift: layout   Esc or B: quit", MUTED, 1)

    # text box
    gfx.fill_rect(24, 84, 1232, 16 * 2 * MAX_LINES + 24, PANEL)
    for i, line in enumerate(lines):
        cursor = "_" if i == len(lines) - 1 and (switch.ticks_ms() // 500) % 2 else ""
        gfx.text(36, 96 + i * 32, line + cursor, gfx.WHITE, 2)

    y = 84 + 16 * 2 * MAX_LINES + 40
    gfx.text(24, y, "Layout", MUTED, 2)
    gfx.text(200, y, kb.layout.upper(), ACCENT, 2)
    gfx.text(24, y + 40, "Held keys", MUTED, 2)
    held = " ".join(keys.name(c) for c in kb.held) or "-"
    gfx.text(200, y + 40, held[:60], gfx.WHITE, 2)

    gfx.text(24, y + 80, "Mouse", MUTED, 2)
    if m.connected:
        gfx.text(200, y + 80, "x %4d  y %4d   wheel %d / %d" % (m.x, m.y, wheel_total[0], wheel_total[1]),
                 gfx.WHITE, 2)
        draw_mouse_buttons(200, y + 120, m.buttons)
    else:
        gfx.text(200, y + 80, "not connected", MUTED, 2)

    for cx, cy, color in clicks:
        gfx.circle(cx, cy, 10, color)
    if m.connected:                                     # cursor: a small arrow-like cross
        gfx.fill_rect(m.x - 12, m.y - 1, 25, 3, gfx.WHITE)
        gfx.fill_rect(m.x - 1, m.y - 12, 3, 25, gfx.WHITE)
        gfx.fill_circle(m.x, m.y, 3, ACCENT)
    gfx.present()
