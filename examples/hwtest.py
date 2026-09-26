# Tests the switch module: battery, buttons, sticks, touch screen, rumble.
# Each stage waits for input and tells you how to move on to the next one.
# Stop the script at any time: + and - together (or Ctrl+C on the computer).

import switch

BUTTONS = [
    ("A", switch.A), ("B", switch.B), ("X", switch.X), ("Y", switch.Y),
    ("L", switch.L), ("R", switch.R), ("ZL", switch.ZL), ("ZR", switch.ZR),
    ("PLUS", switch.PLUS), ("MINUS", switch.MINUS),
    ("UP", switch.UP), ("DOWN", switch.DOWN), ("LEFT", switch.LEFT), ("RIGHT", switch.RIGHT),
    ("LSTICK", switch.LSTICK), ("RSTICK", switch.RSTICK),
]


def names(mask):
    found = [name for name, bit in BUTTONS if mask & bit]
    return " ".join(found) if found else "-"


def title(text):
    print()
    print("=== " + text + " ===")


def wait_for_a():
    print("[A] next")
    while switch.running():
        if switch.buttons_down() & switch.A:
            return
        switch.sleep_ms(16)


# ---------- 1. Battery ----------
title("1/5 Battery")
try:
    print("Charge:", switch.battery(), "%")
except OSError as e:
    print("Battery info unavailable:", e)
wait_for_a()


# ---------- 2. Buttons ----------
title("2/5 Buttons")
print("Press any buttons, their names will appear here.")
print("Hold L + R together to continue.")
while switch.running():
    down = switch.buttons_down()
    if down:
        print("pressed:", names(down), "   held:", names(switch.buttons()))
    held = switch.buttons()
    if held & switch.L and held & switch.R:
        break
    switch.sleep_ms(16)
# wait until L and R are released so they do not leak into the next stage
while switch.buttons() & (switch.L | switch.R):
    switch.sleep_ms(16)
switch.buttons_down()  # discard accumulated presses


# ---------- 3. Sticks ----------
title("3/5 Sticks")
print("Move both sticks. Values are from -1.00 to +1.00 (up and right are +).")
DEAD = 0.05       # dead zone: ignore small stick jitter
STEP = 0.10       # print only when a value changes noticeably
last = None
print("[A] next")
while switch.running():
    lx, ly = switch.stick(0)
    rx, ry = switch.stick(1)
    cur = [0.0 if abs(v) < DEAD else v for v in (lx, ly, rx, ry)]
    if last is None or max(abs(a - b) for a, b in zip(cur, last)) >= STEP:
        print("L (%+.2f, %+.2f)   R (%+.2f, %+.2f)" % tuple(cur))
        last = cur
    if switch.buttons_down() & switch.A:
        break
    switch.sleep_ms(50)


# ---------- 4. Touch screen ----------
title("4/5 Touch screen")
print("Touch the screen with one or more fingers (handheld mode only).")
print("Screen is 1280 x 720. In docked mode touch does not work - just press A.")
last = None
print("[A] next")
while switch.running():
    pts = switch.touches()
    if pts != last:
        if pts:
            print("%d touch(es): %s" % (len(pts), "  ".join("(%d, %d)" % p for p in pts)))
        elif last:
            print("released")
        last = pts
    if switch.buttons_down() & switch.A:
        break
    switch.sleep_ms(30)


# ---------- 5. Rumble ----------
title("5/5 Rumble")
tests = [
    ("weak",           0.3, 160, 320),
    ("strong",         0.9, 160, 320),
    ("low frequency",  0.7,  80, 160),
    ("high frequency", 0.7, 320, 640),
]
for name, amp, low, high in tests:
    print("rumble: %-15s amp=%.1f  low=%d Hz  high=%d Hz" % (name, amp, low, high))
    switch.rumble(amp, 500, low=low, high=high)
    switch.sleep_ms(300)

print()
print("Now control rumble with the RIGHT stick: push up for stronger vibration.")
print("[A] stop")
last_amp = -1.0
while switch.running():
    _, ry = switch.stick(1)
    amp = max(0.0, ry)                 # up only: 0.0 .. 1.0
    amp = round(amp * 10) / 10         # 0.1 steps so the motors are not updated on every jitter
    if amp != last_amp:
        switch.rumble(amp)             # no ms: keeps vibrating until changed
        print("amp = %.1f" % amp)
        last_amp = amp
    if switch.buttons_down() & switch.A:
        break
    switch.sleep_ms(30)
switch.rumble(0)

print()
print("All tests done!")
