"""IDE hints: the built-in `gfx` module from NXToolBox (runs only on the Switch).

1280x720 graphics. The first drawing call switches the screen from the text console
to graphics mode; when the script ends, the console comes back automatically and shows
everything the script printed meanwhile (including errors).

Typical loop:
    while switch.running():
        gfx.clear()
        ... draw ...
        gfx.present()      # show the frame, ~60 fps

Colors are ints; use gfx.rgb() or the constants below. Coordinates may be off-screen,
everything is clipped.
"""

WIDTH: int          # 1280
HEIGHT: int         # 720
FONT_WIDTH: int     # 8 (character cell width at scale 1)
FONT_HEIGHT: int    # 16

BLACK: int
WHITE: int
GRAY: int
RED: int
GREEN: int
BLUE: int
YELLOW: int
ORANGE: int
CYAN: int
MAGENTA: int


def rgb(r: int, g: int, b: int, a: int = 255) -> int:
    """Color from components 0..255."""
    ...


def begin() -> None:
    """Switch to graphics mode now (drawing functions do it automatically)."""
    ...


def end() -> None:
    """Back to the text console before the script ends."""
    ...


def present() -> None:
    """Show what has been drawn. Waits for the display, so a loop runs at ~60 fps.
    The picture is kept between frames: you can redraw only what changed."""
    ...


def clear(color: int = BLACK) -> None: ...
def pixel(x: int, y: int, color: int) -> None: ...
def line(x0: int, y0: int, x1: int, y1: int, color: int) -> None: ...


def rect(x: int, y: int, w: int, h: int, color: int) -> None:
    """Rectangle outline."""
    ...


def fill_rect(x: int, y: int, w: int, h: int, color: int) -> None: ...


def fill_gradient(x: int, y: int, w: int, h: int, color1: int, color2: int, vertical: bool = True) -> None:
    """Rectangle filled with a linear gradient from color1 to color2: top-to-bottom if
    vertical (the default), left-to-right otherwise. All four channels (R, G, B, A) are
    interpolated."""
    ...


def circle(x: int, y: int, r: int, color: int) -> None:
    """Circle outline centered at (x, y)."""
    ...


def fill_circle(x: int, y: int, r: int, color: int) -> None: ...


def text(x: int, y: int, _text: str, color: int = WHITE, scale: int = 1) -> int:
    """Draw text with a 8x16 bitmap font (Latin, Cyrillic, arrows, box drawing).
    (x, y) is the top-left corner; '\\n' starts a new line; scale enlarges the pixels.
    Returns the width of the widest line in pixels."""
    ...


def text_width(_text: str, scale: int = 1) -> int:
    """Width of the text in pixels without drawing it (for centering and alignment)."""
    ...


def blit(x: int, y: int, w: int, h: int, data: bytes) -> None:
    """Draw an image of w*h pixels, 4 bytes per pixel (R, G, B, A), row by row.
    Pixels with A == 0 are transparent."""
    ...
