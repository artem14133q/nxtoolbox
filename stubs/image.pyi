"""IDE hints: the built-in `image` module (stb_image + nanosvg, runs only on the Switch)."""
from typing import Optional, Tuple


def load(path: str, max_w: int = 0, max_h: int = 0,
         bg: Optional[int] = None) -> Tuple[int, int, bytes]:
    """Decode a PNG, JPEG, BMP, GIF (first frame), TGA or SVG file into (w, h, rgba) for
    gfx.blit(x, y, w, h, rgba). max_w/max_h: scale down to fit (keeping the aspect ratio,
    never up); 0 = no limit. SVG is rendered straight at the target size (crisp at any
    size, not a blurry raster downscale) - not the full SVG spec: no filters/masks/text,
    basic shapes, paths, fills, strokes and gradients only. bg: a gfx color to blend
    transparent pixels onto (the result is opaque). OSError if the file cannot be read
    or decoded."""
    ...
