"""IDE hints: the built-in `usbinput` module (USB keyboard and mouse through the system).
Most scripts use lib/keys.py (characters, layouts, auto-repeat, mouse clicks) instead."""
from typing import Dict, List, Union

MOD_CTRL: int
MOD_SHIFT: int
MOD_LEFT_ALT: int
MOD_RIGHT_ALT: int
MOD_GUI: int
MOD_CAPS_LOCK: int      # lock states
MOD_SCROLL_LOCK: int
MOD_NUM_LOCK: int

MOUSE_LEFT: int
MOUSE_RIGHT: int
MOUSE_MIDDLE: int
MOUSE_FORWARD: int
MOUSE_BACK: int


def keys() -> List[int]:
    """USB HID usage codes of the keys held right now (see the names in lib/keys.py)."""
    ...


def modifiers() -> int:
    """MOD_* bits: held modifier keys and the Caps/Num/Scroll Lock states."""
    ...


def mouse() -> Dict[str, Union[int, bool]]:
    """{"x", "y": cursor position; "dx", "dy": movement and "wheel", "wheel_h": wheel steps
    since the previous call; "buttons": MOUSE_* held; "connected": bool}"""
    ...
