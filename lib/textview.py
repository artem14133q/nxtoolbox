"""textview - a scrollable, read-only, GitHub-style view of markdown.parse() blocks:
headings at real proportional sizes, word-wrapped paragraphs and (nested, numbered)
lists with **bold**, *italic*, ~~strike~~, `code` and [link](url) spans, blockquotes,
fenced code blocks in the monospace font, horizontal rules and tables. Scrolls like
ui.ListBox (Up/Down, or drag a finger) but has no selection - it is meant for a help
screen, not a menu.

Headings are drawn straight through the font/gfx modules at an exact pixel size instead
of through ui.text()'s integer "scale" grid, which only ever gives body size or exactly
2x - not enough tiers to tell h1/h2/h3 apart the way a real Markdown renderer does.

Bold is a real (if faked) heavier stroke, scaled to the text size. Italic uses the
theme's real italic font (THEME.fonts["italic"]) if there is one; without it (or on the
pixel-font fallback, which has no slanted glyphs either) it falls back to a muted color
instead. Links have no navigation in this engine, so they just look like links.

    import markdown, textview
    view = textview.TextView(markdown.parse(readme_text), rows=16, w=900)
"""
import switch
import ui
import markdown

ROW_H = ui.CHAR_H + 6
_INDENT = ui.CHAR_W * 2
_ITALIC_COLOR = ui.shade(ui.TEXT, -60)          # used only without a real italic font
_CODE_BG = ui.shade(ui.PANEL, -14)              # `code` chip and ``` block ``` background
BODY_PX = 16                                    # matches ui.text()'s scale=1 exactly

# kind -> (pixel size, color, force_bold, underline)
# GitHub-like proportions (h1 2x body, h2 1.4x, h3 1.1x); h2 also gets an underline like
# a setext heading - at the same *size* class as h3 and body, bold alone is too easy to
# miss at a glance, a rule under it is not. h1 does not need one, it is already much
# bigger; h3 stays the plainer, bold-only tier.
_HEADING_STYLE = {
    "h1": (30, ui.ACCENT, True, False),
    "h2": (22, ui.ACCENT, True, True),
    "h3": (18, ui.ACCENT, True, False),
}

_RULE = "rule"


def _font_for(seg):
    """The font id to use for one inline-parsed word (None = the default UI font)."""
    if seg and seg["italic"] and ui.ITALIC_FONT is not None:
        return ui.ITALIC_FONT
    return None


def _measure_px(word, px, font=None):
    """Pixel width of word at an exact size - bypasses ui.text_width()'s scale grid."""
    font = ui.UI_FONT if font is None else font
    if font is None:
        return ui.text_width(word, max(1, round(px / ui.gfx.FONT_HEIGHT)))
    return ui._font.width(font, word, px)


def _draw_px(x, y, s, color, px, bold=False, font=None):
    """Draws text at an exact pixel size with a specific font id (None = the default UI
    font); returns its width. bold draws extra passes offset by roughly px/16 pixels, so
    the fake weight scales with the text size instead of staying a fixed (and at large
    sizes, invisible) 1px."""
    font = ui.UI_FONT if font is None else font
    if font is None:
        return ui.text(x, y, s, color, max(1, round(px / ui.gfx.FONT_HEIGHT)), bold)
    w = ui._font.text(font, x, y, s, color, px)
    if bold:
        off = max(1, px // 16)
        ui._font.text(font, x + off, y, s, color, px)
        ui._font.text(font, x, y + off, s, color, px)
    return w


def _word_style(seg, base_color, force_bold):
    """(color, bold, underline, strike) for one inline-parsed word. `code` is not here:
    it keeps the normal text color - draw() paints a chip behind it instead (see pass 2
    there), the same way it marks a fenced code block."""
    bold = force_bold or seg["bold"]
    if seg["link"]:
        return ui.ACCENT, bold, True, False
    if seg["italic"] and ui.ITALIC_FONT is None:
        return _ITALIC_COLOR, bold, False, False    # no real italic font: color stand-in
    if seg["strike"]:
        return base_color, bold, False, True
    return base_color, bold, False, False


def _wrap_segments(segments, avail_px, measure):
    """[[(word, seg), ...], ...] - every segment's words, greedily wrapped into lines
    that fit avail_px pixels; measure(word, seg) gives its width at the line's own size,
    using seg to pick the right font (e.g. italic words measure narrower/wider than the
    same word in the regular font)."""
    space_w = measure(" ", None)
    lines = []
    line = []
    line_w = 0
    for seg in segments:
        for word in seg["text"].split():
            ww = measure(word, seg)
            add_w = ww if not line else space_w + ww
            if line and line_w + add_w > avail_px:
                lines.append(line)
                line = []
                line_w = 0
                add_w = ww
            line.append((word, seg))
            line_w += add_w
    if line:
        lines.append(line)
    return lines or [[]]                          # an empty block still makes one blank line


def _text_line(words, px, indent, color, bold=False, prefix=None, underline=False, quote=False):
    return {"words": words, "px": px, "indent": indent, "color": color, "bold": bold,
           "prefix": prefix, "underline": underline, "quote": quote}


_BLANK = _text_line([], BODY_PX, 0, ui.TEXT)


class TextView(ui.Widget):
    focusable = True
    expand_w = True
    expand_h = True

    def __init__(self, blocks=None, rows=12, w=600, x=0, y=0):
        self.rows = rows
        self.min_rows = rows
        self.min_w = w
        self.top = 0
        self._dragging = False
        self._blocks = blocks or []
        self._lines = []                  # laid out for the current width, see _layout()
        self._wrapped_w = None
        ui.Widget.__init__(self, x, y, w, rows * ROW_H + 8)
        self._layout()                    # in case resize() never fires (hint == final size)

    def hint(self):
        return self.min_w, self.min_rows * ROW_H + 8

    def resize(self, w, h):
        self.rows = max(1, (h - 8) // ROW_H)
        ui.Widget.resize(self, w, self.rows * ROW_H + 8)
        if w != self._wrapped_w:
            self._layout()

    def set_blocks(self, blocks):
        self._blocks = blocks
        self.top = 0
        self._layout()

    def _max_top(self):
        return max(0, len(self._lines) - self.rows)

    # ---------- layout ----------

    def _table_lines(self, block, avail):
        rows, align = block["rows"], block["align"]
        ncols = max((len(r) for r in rows), default=0)
        if not ncols:
            return []
        col_w = max(60, (avail - 4) // ncols)
        out = [_RULE]
        for ri, row in enumerate(rows):
            cells = row + [""] * (ncols - len(row))
            # cells are plain text, not full inline styling (too little room per word to
            # matter) - but **bold**/`code`/etc. markers still need stripping, or they
            # would show up literally
            plain = ["".join(seg["text"] for seg in markdown.parse_inline(c)) for c in cells]
            out.append({"cells": plain, "align": align, "col_w": col_w, "header": ri == 0})
            if ri == 0:
                out.append(_RULE)
        out.append(_RULE)
        return out

    def _layout(self):
        self._wrapped_w = self.w
        avail = max(80, self.w - 24)
        out = []
        blocks = self._blocks

        def body_measure(word, seg):
            return _measure_px(word, BODY_PX, _font_for(seg))

        for idx, b in enumerate(blocks):
            kind = b["kind"]
            next_kind = blocks[idx + 1]["kind"] if idx + 1 < len(blocks) else None

            if kind in _HEADING_STYLE:
                px, color, bold, underline = _HEADING_STYLE[kind]
                wrapped = _wrap_segments(markdown.parse_inline(b["text"]), avail,
                                         lambda w, seg, px=px: _measure_px(w, px, _font_for(seg)))
                head = [_text_line(line, px, 0, color, bold) for line in wrapped]
                if underline and head:
                    head[-1]["underline"] = True
                out.extend(head)
                if next_kind != "li":             # a list hugs its heading; anything
                    out.append(_BLANK)            # else gets a full blank line first

            elif kind == "hr":
                out.append(_RULE)

            elif kind == "code":
                for line in b["text"].split("\n"):
                    out.append({"mono": line, "indent": _INDENT, "color": ui.TEXT})
                out.append(_BLANK)

            elif kind == "quote":
                wrapped = _wrap_segments(markdown.parse_inline(b["text"]), avail - _INDENT, body_measure)
                for line in wrapped:
                    out.append(_text_line(line, BODY_PX, _INDENT, ui.MUTED, quote=True))
                out.append(_BLANK)

            elif kind == "li":
                indent = _INDENT * (b.get("depth", 0) + 1)
                prefix = b["marker"] + " "
                cont = " " * len(prefix)
                pw = _measure_px(prefix, BODY_PX)
                wrapped = _wrap_segments(markdown.parse_inline(b["text"]),
                                         max(40, avail - indent - pw), body_measure)
                for i, line in enumerate(wrapped):
                    out.append(_text_line(line, BODY_PX, indent, ui.TEXT,
                                          prefix=prefix if i == 0 else cont))
                if next_kind != "li":             # blank only once the list is over
                    out.append(_BLANK)

            elif kind == "table":
                out.extend(self._table_lines(b, avail))
                out.append(_BLANK)

            else:                                    # "p"
                wrapped = _wrap_segments(markdown.parse_inline(b["text"]), avail, body_measure)
                out.extend(_text_line(line, BODY_PX, 0, ui.TEXT) for line in wrapped)
                out.append(_BLANK)

        while out and out[-1] is _BLANK:              # no trailing blank line
            out.pop()
        self._lines = out
        self.top = max(0, min(self.top, self._max_top()))
        self.invalidate()

    # ---------- drawing ----------

    def _draw_table_row(self, line, ry):
        cx = self.x + 12
        color = ui.ACCENT if line["header"] else ui.TEXT
        cells, align = line["cells"], line["align"]
        for ci, cell in enumerate(cells):
            col_w = line["col_w"]
            txt = ui.elide(cell, col_w - 12, 1)
            tw = ui.text_width(txt, 1)
            a = align[ci] if ci < len(align) else ""
            if a == "right":
                tx = cx + col_w - 8 - tw
            elif a == "center":
                tx = cx + (col_w - tw) // 2
            else:
                tx = cx + 6
            _draw_px(tx, ry + 3, txt, color, BODY_PX, line["header"])
            cx += col_w
            if ci < len(cells) - 1:
                ui.fill(cx - 1, ry, 1, ROW_H, ui.BORDER)

    def draw(self):
        ui.box(self.x, self.y, self.w, self.h, ui.PANEL, ui.BORDER, 1, bg=self.bg())
        for row in range(self.rows):
            i = self.top + row
            if i >= len(self._lines):
                break
            line = self._lines[i]
            ry = self.y + 4 + row * ROW_H

            if line is _RULE:
                ui.fill(self.x + 12, ry + ROW_H // 2, self.w - 24, 1, ui.BORDER)
                continue
            if "cells" in line:
                self._draw_table_row(line, ry)
                continue
            if "mono" in line:
                if i == 0 or "mono" not in self._lines[i - 1]:
                    # the first line of a fenced code block: paint one rounded panel
                    # behind however much of it is visible in this frame (a block that
                    # is itself taller than the widget just gets clipped at the bottom,
                    # same as everything else here)
                    j = i
                    while j < len(self._lines) and "mono" in self._lines[j]:
                        j += 1
                    span = min(j - i, self.rows - row)
                    ui.box(self.x + 8, ry - 2, self.w - 16, span * ROW_H - 6, _CODE_BG, radius=8)
                ui.mono_text(self.x + 12 + line["indent"], ry + 3, line["mono"], line["color"], 1)
                continue

            x = self.x + 12 + line["indent"]
            if line["quote"]:
                ui.fill(x - 8, ry + 2, 3, ROW_H - 8, ui.ACCENT)
            if line["prefix"]:
                x += _draw_px(x, ry + 3, line["prefix"], line["color"], line["px"], line["bold"])

            # pass 1: where each word lands, without drawing anything yet
            positions = []
            cx = x
            for word, seg in line["words"]:
                w = _measure_px(word, line["px"], _font_for(seg))
                positions.append((cx, w, word, seg))
                cx += w + _measure_px(" ", line["px"])

            # pass 2: one rounded `code` chip behind each run of words from the same
            # inline code span (several words when there is a space inside the backticks),
            # drawn before the text so it sits behind it
            k = 0
            while k < len(positions):
                px0, w0, _word0, seg0 = positions[k]
                if seg0["code"]:
                    j = k
                    end_x = px0 + w0
                    while j + 1 < len(positions) and positions[j + 1][3] is seg0:
                        j += 1
                        end_x = positions[j][0] + positions[j][1]
                    ui.box(px0 - 4, ry - 1, end_x - px0 + 8, line["px"] + 8, _CODE_BG, radius=6)
                    k = j + 1
                else:
                    k += 1

            # pass 3: the text itself, on top of any code chip backgrounds
            for cx, w, word, seg in positions:
                color, bold, underline, strike = _word_style(seg, line["color"], line["bold"])
                _draw_px(cx, ry + 3, word, color, line["px"], bold, _font_for(seg))
                if underline:
                    ui.fill(cx, ry + 3 + line["px"], w, 1, color)
                if strike:
                    ui.fill(cx, ry + 3 + line["px"] // 2, w, 1, color)
            if line["underline"]:
                ui.fill(self.x + 12, ry + ROW_H - 4, self.w - 24, 2, line["color"])

        if len(self._lines) > self.rows:              # scroll indicator, as in ui.ListBox
            bar_h = max(16, (self.h - 8) * self.rows // len(self._lines))
            bar_y = self.y + 4 + (self.h - 8 - bar_h) * self.top // (len(self._lines) - self.rows)
            ui.box(self.x + self.w - 10, bar_y, 6, bar_h, ui.MUTED,
                  radius=3 if ui.RADIUS else 0, bg=ui.PANEL)

    # ---------- input ----------

    def key(self, down):
        if down & switch.UP and self.top > 0:
            self.top -= 1
            self.invalidate()
            return True
        if down & switch.DOWN and self.top < self._max_top():
            self.top += 1
            self.invalidate()
            return True
        return False

    def touch(self, x, y, first):
        if first:
            self._dragging = False
            self._drag_y = y
            self._drag_top = self.top
            return
        dy = y - self._drag_y
        if not self._dragging and abs(dy) < ui._DRAG_PX:
            return
        self._dragging = True
        rows = abs(dy) // ROW_H
        top = max(0, min(self._max_top(), self._drag_top + (-rows if dy > 0 else rows)))
        if top != self.top:
            self.top = top
            self.invalidate()

    def touch_end(self, inside):
        self._dragging = False
