"""IDE hints: the built-in `font` module - smooth TrueType text (stb_truetype).

The GUI uses it through ui.text() / ui.text_width() with the fonts of the theme.
Text is drawn into the gfx frame with antialiasing; the first call switches to graphics mode.
"""
from typing import Tuple


def load(path: str) -> int:
    """Load a .ttf file; returns a font id (the same path gives the same id). OSError on failure."""
    ...


def text(font: int, x: int, y: int, text: str, color: int = 0xFFFFFFFF, size: int = 16,
         advance: int = 0) -> int:
    """Draw text with the top-left corner of its first line at (x, y); returns the width.
    size is the pixel height of the font (ascent + descent); "\\n" starts a new line;
    advance > 0 puts the characters on a fixed grid of that many pixels (monospace)."""
    ...


def width(font: int, text: str, size: int = 16, advance: int = 0) -> int:
    """Width of the widest line in pixels."""
    ...


def metrics(font: int, size: int = 16) -> Tuple[int, int, int]:
    """(ascent, descent, line_height) in pixels."""
    ...


def fallback(font: int, other: int) -> None:
    """Draw characters missing in font with other (-1 = no fallback)."""
    ...
