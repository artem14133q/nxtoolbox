"""IDE hints: the built-in `draw` module - alpha-blended shapes in the gfx frame.

Colors are gfx colors; gfx.rgb(r, g, b, a) sets the alpha (255 = opaque, 0 = invisible).
Unlike gfx.fill_rect, transparent colors are blended with what is already on screen and
rounded corners are smooth over any background. The GUI uses it through ui.box() / ui.fill().
"""
from typing import Optional


def rect(x: int, y: int, w: int, h: int, color: int, radius: int = 0,
         border: Optional[int] = None, border_width: int = 0) -> None:
    """A rectangle with rounded, antialiased corners; the border is drawn inside it."""
    ...


def circle(cx: int, cy: int, r: int, color: int, border: Optional[int] = None,
           border_width: int = 0) -> None:
    """A smooth filled circle, optionally with a border ring."""
    ...


def blit(x: int, y: int, w: int, h: int, rgba: bytes) -> None:
    """Draw w*h RGBA pixels, each blended by its own alpha (gfx.blit only skips alpha 0)."""
    ...
