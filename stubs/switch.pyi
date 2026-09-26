"""IDE hints: the `switch` module from nxtest (implemented in C, runs only on the Switch).

This file is never executed; it only helps the editor (CLion, PyCharm, VS Code)
understand `import switch` and show completion and documentation.
"""
from typing import List, Tuple

# ---------- buttons (bit masks) ----------
A: int
B: int
X: int
Y: int
L: int
R: int
ZL: int
ZR: int
PLUS: int
MINUS: int
UP: int
DOWN: int
LEFT: int
RIGHT: int
LSTICK: int
"""Left stick click."""
RSTICK: int
"""Right stick click."""


# ---------- system ----------
def battery() -> int:
    """Battery charge in percent. OSError if the data is unavailable."""
    ...


def sleep_ms(ms: int) -> None:
    """Pause in milliseconds. Can be interrupted (+ and -, Ctrl+C, HOME)."""
    ...


def ticks_ms() -> int:
    """Milliseconds since the console was powered on. For timing and timeouts:
    `start = switch.ticks_ms(); ...; elapsed = switch.ticks_ms() - start`"""
    ...


def running() -> bool:
    """Call in every loop: refreshes the screen and handles HOME.
    False means the system asks the app to exit."""
    ...


# ---------- buttons ----------
def buttons() -> int:
    """Mask of buttons held right now. Check with: `if switch.buttons() & switch.A:`"""
    ...


def buttons_down() -> int:
    """Mask of buttons pressed since the previous buttons_down() call."""
    ...


# ---------- sticks ----------
def stick(index: int) -> Tuple[float, float]:
    """Stick position: 0 left, 1 right.
    Returns (x, y) from -1.0 to 1.0; up and right are positive."""
    ...


# ---------- touch screen ----------
def touches() -> List[Tuple[int, int]]:
    """Current touches [(x, y), ...], screen is 1280 x 720.
    Works only in handheld mode; always an empty list when docked."""
    ...


# ---------- rumble ----------
def rumble(amp: float, ms: int = 0, *, low: float = 160, high: float = 320) -> None:
    """Controller rumble.

    amp  - strength 0.0..1.0; 0 turns the rumble off.
    ms   - if > 0: vibrate for this many milliseconds, then stop (the call waits);
           if 0: vibrate until rumble(0) is called.
    low, high - frequencies of the low and high bands in Hz.

    The rumble is turned off automatically when the script ends.
    """
    ...
