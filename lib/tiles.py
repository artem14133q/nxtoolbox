"""tiles - a grid of tiles with icons (used by the launcher's Files tab).

    grid = tiles.TileGrid(describe=info_for, on_select=open_item)
    grid.set_items(["games/", "snake.py", ...])

The API matches ui.ListBox (items, selected, top, set_items, select, selected_item,
on_select, on_change), so it can replace a list. describe(item) returns a dict:
    {"title": str, "subtitle": str, "kind": "dir" | "file", "icon": (w, h, rgba) or missing}
It is called lazily, only for tiles that are on screen; icons of tiles far off screen
are dropped to save memory. Icons are expected to be at most ICON x ICON pixels and
composited onto ICON_BG (image.load(path, ICON, ICON, ICON_BG)).
"""
import switch
import gfx
import ui

TILE_W = 200
TILE_H = 214
GAP = 16
PLATE = 128                         # rounded plate behind the icon
ICON = 112                          # icons are loaded at most ICON x ICON pixels
ICON_BG = ui.ICON_BG
# colors for the default "letter" icons, picked by the title
PALETTE = [gfx.rgb(214, 69, 65), gfx.rgb(230, 126, 34), gfx.rgb(241, 196, 15),
           gfx.rgb(46, 204, 113), gfx.rgb(26, 188, 156), gfx.rgb(52, 152, 219),
           gfx.rgb(155, 89, 182), gfx.rgb(236, 100, 165)]
FOLDER = gfx.rgb(240, 180, 60)
FOLDER_DARK = gfx.rgb(200, 140, 40)

_chars = ui._chars                  # character lists (also without Unicode support)


def _hash(text):
    h = 0
    for c in text:
        h = (h * 31 + ord(c)) & 0xFFFF
    return h


class TileGrid(ui.Widget):
    focusable = True
    expand_w = True
    expand_h = True
    focus_ring = False                  # the selected tile gets the ring instead

    def __init__(self, items=None, describe=None, on_select=None, on_change=None,
                 cols=3, rows=2, x=0, y=0):
        self.items = list(items or [])
        self.describe = describe
        self.on_select = on_select
        self.on_change = on_change
        self.selected = 0
        self.top = 0                    # first visible row
        self._dragging = False
        self._cache = {}                # item -> describe() result
        self.min_cols, self.min_rows = cols, rows
        ui.Widget.__init__(self, x, y, *self._size(cols, rows))

    # ---------- geometry ----------

    @staticmethod
    def _size(cols, rows):
        return cols * (TILE_W + GAP) - GAP, rows * (TILE_H + GAP) - GAP

    def hint(self):
        return self._size(self.min_cols, self.min_rows)

    def cols(self):
        return max(1, (self.w + GAP) // (TILE_W + GAP))

    def rows(self):
        return max(1, (self.h + GAP) // (TILE_H + GAP))

    def _origin(self):
        # center the grid horizontally inside the widget
        cols = self.cols()
        used = cols * (TILE_W + GAP) - GAP
        return self.x + (self.w - used) // 2, self.y

    # ---------- list-like API ----------

    def set_items(self, items):
        self.items = list(items)
        self._cache = {k: v for k, v in self._cache.items() if k in self.items}
        if self.selected >= len(self.items):
            self.selected = max(0, len(self.items) - 1)
        self._scroll_to(self.selected)
        self.invalidate()

    def forget(self, item=None):
        """Drop cached descriptions (all, or of one item) so they are read again."""
        if item is None:
            self._cache = {}
        else:
            self._cache.pop(item, None)
        self.invalidate()

    def select(self, index):
        self._select(index)

    def selected_item(self):
        return self.items[self.selected] if self.items else None

    def _max_top(self):
        cols, rows = self.cols(), self.rows()
        if not self.items:
            return 0
        return max(0, (len(self.items) - 1) // cols - rows + 1)

    def _scroll_to(self, index):
        cols, rows = self.cols(), self.rows()
        row = index // cols
        if row < self.top:
            self.top = row
        elif row >= self.top + rows:
            self.top = row - rows + 1
        self.top = max(0, min(self.top, self._max_top()))

    def _select(self, index):
        if not self.items:
            return
        index = max(0, min(len(self.items) - 1, index))
        if index == self.selected:
            return
        self.selected = index
        self._scroll_to(index)
        self.invalidate()
        if self.on_change:
            self.on_change(index, self.items[index])

    # ---------- input ----------

    def key(self, down):
        if not self.items:
            return False
        cols = self.cols()
        i = self.selected
        if down & switch.LEFT and i % cols > 0:
            self._select(i - 1)
            return True
        if down & switch.RIGHT and i % cols < cols - 1 and i + 1 < len(self.items):
            self._select(i + 1)
            return True
        if down & switch.UP and i >= cols:
            self._select(i - cols)
            return True
        if down & switch.DOWN and i // cols < (len(self.items) - 1) // cols:
            self._select(min(i + cols, len(self.items) - 1))   # the last row may be shorter
            return True
        return False                        # at the edge: the screen moves the focus

    def activate(self):
        if self.items and self.on_select:
            self.on_select(self.selected, self.items[self.selected])

    def _index_at(self, px, py):
        ox, oy = self._origin()
        col = (px - ox) // (TILE_W + GAP)
        row = (py - oy) // (TILE_H + GAP)
        if col < 0 or col >= self.cols() or row < 0 or row >= self.rows():
            return -1
        if (px - ox) % (TILE_W + GAP) >= TILE_W or (py - oy) % (TILE_H + GAP) >= TILE_H:
            return -1                       # in the gap between tiles
        index = (self.top + row) * self.cols() + col
        return index if index < len(self.items) else -1

    def touch(self, x, y, first):
        if first:
            self._dragging = False
            self._drag_y = y
            self._drag_top = self.top
            index = self._index_at(x, y)
            if index >= 0:
                self._select(index)
            return
        dy = y - self._drag_y
        if not self._dragging and abs(dy) < ui._DRAG_PX:
            return
        self._dragging = True
        step = TILE_H + GAP
        rows = abs(dy) // step
        top = max(0, min(self._max_top(), self._drag_top + (-rows if dy > 0 else rows)))
        if top != self.top:
            self.top = top
            self.invalidate()

    def touch_end(self, inside):
        dragging = self._dragging
        self._dragging = False
        if inside and not dragging:
            self.activate()

    # ---------- drawing ----------

    def _info(self, item):
        info = self._cache.get(item)
        if info is None:
            try:
                info = self.describe(item) if self.describe else {}
            except Exception:
                info = {}
            info.setdefault("title", item)
            info.setdefault("subtitle", "")
            info.setdefault("kind", "dir" if item.endswith("/") else "file")
            self._cache[item] = info
        return info

    def draw(self):
        bg = self.screen.bg if self.screen else ui.BG
        gfx.fill_rect(self.x, self.y, self.w, self.h, bg)
        cols, rows = self.cols(), self.rows()
        ox, oy = self._origin()
        first = self.top * cols
        last = min(len(self.items), first + cols * rows)
        for index in range(first, last):
            r, c = divmod(index - first, cols)
            self._draw_tile(ox + c * (TILE_W + GAP), oy + r * (TILE_H + GAP),
                            self._info(self.items[index]), index == self.selected)
        if not self.items:
            ui.text(self.x + 16, self.y + 16, "Nothing here yet", ui.MUTED)

        # scroll indicator
        total_rows = (len(self.items) + cols - 1) // cols
        if total_rows > rows:
            track = self.h
            bar = max(24, track * rows // total_rows)
            pos = (track - bar) * self.top // (total_rows - rows)
            ui.box(self.x + self.w - 6, self.y, 6, track, ui.PANEL, radius=3 if ui.RADIUS else 0)
            ui.box(self.x + self.w - 6, self.y + pos, 6, bar, ui.MUTED, radius=3 if ui.RADIUS else 0)

        # drop icons of tiles far from the visible ones (memory)
        keep_from, keep_to = first - cols * rows, last + cols * rows
        for i, item in enumerate(self.items):
            if (i < keep_from or i >= keep_to) and item in self._cache:
                del self._cache[item]

    def _draw_tile(self, x, y, info, selected):
        bg = self.screen.bg if self.screen else ui.BG
        radius = ui.RADIUS + 4 if ui.RADIUS else 0
        fill = ui.PANEL_HI if selected else ui.PANEL
        if selected and self.focused:
            ui.box(x - 4, y - 4, TILE_W + 8, TILE_H + 8, bg, ui.ACCENT, 2,
                   radius + 4 if radius else 0, bg)
        ui.box(x, y, TILE_W, TILE_H, fill, ui.BORDER, 1, radius, bg)

        ix, iy = x + (TILE_W - PLATE) // 2, y + 12
        ui.box(ix, iy, PLATE, PLATE, ICON_BG, radius=ui.RADIUS, bg=fill)
        icon = info.get("icon")
        if icon:
            w, h, data = icon
            gfx.blit(ix + (PLATE - w) // 2, iy + (PLATE - h) // 2, w, h, data)
        elif info["kind"] == "dir":
            _draw_folder(ix, iy)
        else:
            _draw_letter(ix, iy, info["title"])

        title = ui.elide(info["title"], TILE_W - 16)
        tw = ui.text_width(title)
        ui.text(x + (TILE_W - tw) // 2, iy + PLATE + 8, title, ui.TEXT)
        sub = ui.elide(info["subtitle"], TILE_W - 16, 1) if info["subtitle"] else ""
        if sub:
            sw = ui.text_width(sub, 1)
            ui.text(x + (TILE_W - sw) // 2, iy + PLATE + 8 + ui.CHAR_H + 2, sub, ui.MUTED, 1)


def _draw_folder(x, y):
    r = min(ui.RADIUS, 6)
    ui.box(x + 18, y + 28, 44, 20, FOLDER_DARK, radius=r, bg=ICON_BG)      # tab
    ui.box(x + 18, y + 38, 92, 64, FOLDER, radius=r, bg=ICON_BG)          # body
    ui.fill(x + 18 + r, y + 38, 92 - 2 * r, 5, FOLDER_DARK)


def _draw_letter(x, y, title):
    chars = _chars(title.strip()) or ["?"]
    color = PALETTE[_hash(title) % len(PALETTE)]
    ui.box(x + 8, y + 8, PLATE - 16, PLATE - 16, color, radius=ui.RADIUS + 2 if ui.RADIUS else 0, bg=ICON_BG)
    letter = chars[0].upper()
    lw = ui.text_width(letter, 4)
    ui.text(x + (PLATE - lw) // 2, y + (PLATE - gfx.FONT_HEIGHT * 4) // 2, letter, gfx.WHITE, 4)
