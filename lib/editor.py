"""editor - a small IDE for scripts: editing, syntax highlighting, running with an output panel.

    import editor
    action = editor.edit("/switch/NXToolBox/scripts/hello.py")
    # None, or "run": the caller should run the saved file in a clean interpreter

USB keyboard: typing, arrows, Home/End, PgUp/PgDn, Ctrl+Home/End, Ctrl+S save, Ctrl+Z undo,
F5 run here (output on the right), Ctrl+F5 save and run full screen, Ctrl+plus/minus zoom,
Esc close. Mouse: click places the cursor, the wheel scrolls.
Joy-Con: D-pad moves, A edits the line with the system keyboard, Y adds a line, X deletes
the line, ZR runs, ZL undoes, + saves, B closes.

F5 runs the text in this interpreter: print() goes to the output panel, an error moves the
cursor to its line, + and - together stop a script that hangs.
"""
import switch
import gfx
import ui
import keys

# ---------- look (colors from the theme, section [editor]) ----------

import theme as _theme

_T = _theme.current()
BG = _T.color("editor.background")
GUTTER_BG = _T.color("editor.gutter")
LINE_NUM = _T.color("editor.line_number")
LINE_NUM_CUR = _T.color("editor.line_number_current")
LINE_HI = _T.color("editor.line_highlight")
TITLE_BG = _T.color("editor.bar")
PANEL_BG = _T.color("editor.output")
TEXT = _T.color("editor.text")
CURSOR = _T.color("editor.cursor")
ERROR_BG = _T.color("editor.error_line")
ERROR_TEXT = _T.color("editor.error_text")
MUTED = ui.MUTED
BORDER = ui.BORDER

C_KEYWORD = _T.color("editor.keyword")
C_STRING = _T.color("editor.string")
C_COMMENT = _T.color("editor.comment")
C_NUMBER = _T.color("editor.number")
C_BUILTIN = _T.color("editor.builtin")
C_FUNC = _T.color("editor.function")

# Lines are redrawn over themselves without clearing, so transparent theme colors are mixed
# with the editor background once here (they look the same and never add up).
BG = ui.opaque(BG)
(GUTTER_BG, LINE_NUM, LINE_NUM_CUR, LINE_HI, TITLE_BG, PANEL_BG, TEXT, CURSOR, ERROR_BG,
 ERROR_TEXT, MUTED, BORDER, C_KEYWORD, C_STRING, C_COMMENT, C_NUMBER, C_BUILTIN, C_FUNC) = [
    ui.over(c, BG) for c in (GUTTER_BG, LINE_NUM, LINE_NUM_CUR, LINE_HI, TITLE_BG, PANEL_BG, TEXT,
                             CURSOR, ERROR_BG, ERROR_TEXT, MUTED, BORDER, C_KEYWORD, C_STRING,
                             C_COMMENT, C_NUMBER, C_BUILTIN, C_FUNC)]

TITLE_H = 36
STATUS_H = 24
PANEL_W = 400                       # output panel width
MAX_OUTPUT = 400                    # lines kept in the output panel
UNDO_LIMIT = 60
OUTPUT_ZOOM = 1                     # text size of the output panel (ui.MONO_SIZES index)

KEYWORDS = set("False None True and as assert async await break class continue def del elif "
               "else except finally for from global if import in is lambda nonlocal not or "
               "pass raise return try while with yield".split())
BUILTINS = set("print len range int str float list dict set tuple bool bytes abs min max sum "
               "open isinstance enumerate zip sorted reversed round chr ord hex super object "
               "Exception ValueError OSError KeyboardInterrupt self".split())

_chars = keys._chars                # character lists (also without Unicode support)


# ---------- syntax highlighting ----------

def _is_word(c):
    return c.isalpha() or c.isdigit() or c == "_" or ord(c[0]) >= 128


def tokenize(chars):
    """[(start, end, color)] for one line (a list of characters)."""
    out = []
    i, n = 0, len(chars)
    after_def = False
    while i < n:
        c = chars[i]
        if c == "#":
            out.append((i, n, C_COMMENT))
            break
        if c in "\"'":
            j = i + 1
            while j < n and chars[j] != c:
                j += 2 if chars[j] == "\\" else 1
            j = min(j + 1, n)
            out.append((i, j, C_STRING))
            i = j
            continue
        if c.isdigit():
            j = i
            while j < n and (chars[j].isdigit() or chars[j] in "._xXabcdefABCDEF"):
                j += 1
            out.append((i, j, C_NUMBER))
            i = j
            continue
        if _is_word(c):
            j = i
            while j < n and _is_word(chars[j]):
                j += 1
            word = "".join(chars[i:j])
            if after_def:
                color = C_FUNC
                after_def = False
            elif word in KEYWORDS:
                color = C_KEYWORD
                after_def = word in ("def", "class")
            elif word in BUILTINS:
                color = C_BUILTIN
            else:
                color = TEXT
            out.append((i, j, color))
            i = j
            continue
        j = i + 1
        while j < n and not _is_word(chars[j]) and chars[j] not in "#\"'" and not chars[j].isdigit():
            j += 1
        out.append((i, j, TEXT))
        i = j
    return out


# ---------- the editor ----------

class Editor:
    def __init__(self, path):
        self.path = path
        self.name = path.split("/")[-1]
        self.lines = [[]]
        self.cy = self.cx = 0                   # cursor: line, column (characters)
        self.top = self.left = 0                # scroll position
        self.zoom = 1                           # ui.MONO_SIZES index (Ctrl+plus/minus)
        self.modified = False
        self.output = []
        self.status = "Ready"
        self.status_color = MUTED
        self.error_line = -1
        self.undo = []
        self._undo_kind = None
        self._undo_time = 0
        self._tokens = {}
        self._dirty = True
        self._blink_on = True
        self._blink_at = 0
        self._last_present = 0
        self._repeat_at = 0
        self.kb = keys.Keyboard()
        self.mouse = keys.Mouse()
        self.load()

    # ----- file -----

    def load(self):
        try:
            with open(self.path) as f:
                text = f.read()
        except OSError:
            text = ""
        text = text.replace("\r", "").replace("\t", "    ")
        self.lines = [_chars(line) for line in text.split("\n")]
        if len(self.lines) > 1 and not self.lines[-1]:
            self.lines.pop()                    # the final newline
        self.modified = False

    def text(self):
        return "\n".join("".join(line) for line in self.lines) + "\n"

    def save(self):
        try:
            with open(self.path, "w") as f:
                f.write(self.text())
            self.modified = False
            self.set_status("Saved " + self.name, C_STRING)
        except OSError as e:
            self.set_status("Cannot save: %s" % e, ERROR_TEXT)
        self._dirty = True

    # ----- geometry -----

    def cw(self):
        return ui.mono_cell(self.zoom)[0]

    def ch(self):
        return ui.mono_cell(self.zoom)[1]

    def gutter_w(self):
        return (len(str(len(self.lines))) + 2) * self.cw()

    def text_x(self):
        return self.gutter_w()

    def visible_rows(self):
        return (gfx.HEIGHT - TITLE_H - STATUS_H) // self.ch()

    def visible_cols(self):
        return (gfx.WIDTH - PANEL_W - self.text_x() - 8) // self.cw()

    def scroll_to_cursor(self):
        rows, cols = self.visible_rows(), self.visible_cols()
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + rows:
            self.top = self.cy - rows + 1
        if self.cx < self.left:
            self.left = max(0, self.cx - 8)
        elif self.cx >= self.left + cols:
            self.left = self.cx - cols + 8

    # ----- editing -----

    def set_status(self, text, color=MUTED):
        self.status = text
        self.status_color = color
        self._dirty = True

    def checkpoint(self, kind):
        """Save an undo step; typing within a second is grouped into one step."""
        now = switch.ticks_ms()
        if kind != self._undo_kind or now - self._undo_time > 1000:
            self.undo.append(([list(l) for l in self.lines], self.cy, self.cx))
            if len(self.undo) > UNDO_LIMIT:
                self.undo.pop(0)
        self._undo_kind = kind
        self._undo_time = now

    def do_undo(self):
        if not self.undo:
            self.set_status("Nothing to undo")
            return
        self.lines, self.cy, self.cx = self.undo.pop()
        self._undo_kind = None
        self.modified = True
        self.clamp()
        self._dirty = True

    def clamp(self):
        self.cy = max(0, min(self.cy, len(self.lines) - 1))
        self.cx = max(0, min(self.cx, len(self.lines[self.cy])))

    def insert(self, text):
        self.checkpoint("type")
        line = self.lines[self.cy]
        for c in _chars(text):
            line.insert(self.cx, c)
            self.cx += 1
        self.changed()

    def newline(self):
        self.checkpoint("newline")
        line = self.lines[self.cy]
        indent = 0
        while indent < len(line) and line[indent] == " ":
            indent += 1
        head = line[:self.cx]
        if "".join(head).rstrip().endswith(":"):
            indent += 4
        rest = line[self.cx:]
        self.lines[self.cy] = head
        self.lines.insert(self.cy + 1, [" "] * indent + rest)
        self.cy += 1
        self.cx = indent
        self.changed()

    def backspace(self):
        self.checkpoint("delete")
        line = self.lines[self.cy]
        if self.cx > 0:
            n = 1
            if all(c == " " for c in line[:self.cx]):
                n = (self.cx - 1) % 4 + 1        # remove one indent level
            for _ in range(n):
                line.pop(self.cx - n)
            self.cx -= n
        elif self.cy > 0:
            prev = self.lines[self.cy - 1]
            self.cx = len(prev)
            prev.extend(line)
            self.lines.pop(self.cy)
            self.cy -= 1
        self.changed()

    def delete(self):
        self.checkpoint("delete")
        line = self.lines[self.cy]
        if self.cx < len(line):
            del line[self.cx]
        elif self.cy < len(self.lines) - 1:
            line.extend(self.lines.pop(self.cy + 1))
        self.changed()

    def delete_line(self):
        self.checkpoint("line")
        if len(self.lines) > 1:
            self.lines.pop(self.cy)
        else:
            self.lines[0] = []
        self.clamp()
        self.changed()

    def edit_line(self, new_line_below=False):
        """Edit the current line (or a new one) with the system keyboard."""
        if new_line_below:
            indent = 0
            line = self.lines[self.cy]
            while indent < len(line) and line[indent] == " ":
                indent += 1
            initial = " " * indent
        else:
            initial = "".join(self.lines[self.cy])
        text = switch.keyboard(initial, "Line %d" % (self.cy + (2 if new_line_below else 1)))
        self._dirty = True
        if text is None:
            return
        self.checkpoint("line")
        if new_line_below:
            self.lines.insert(self.cy + 1, _chars(text))
            self.cy += 1
        else:
            self.lines[self.cy] = _chars(text)
        self.cx = len(self.lines[self.cy])
        self.changed()

    def changed(self):
        self.modified = True
        self.error_line = -1
        self.clamp()
        self.scroll_to_cursor()
        self._dirty = True
        self._blink_on = True

    def move(self, dy=0, dx=0):
        if dx:
            if dx < 0 and self.cx == 0 and self.cy > 0:
                self.cy -= 1
                self.cx = len(self.lines[self.cy])
            elif dx > 0 and self.cx == len(self.lines[self.cy]) and self.cy < len(self.lines) - 1:
                self.cy += 1
                self.cx = 0
            else:
                self.cx += dx
        self.cy += dy
        self.clamp()
        self.scroll_to_cursor()
        self._undo_kind = None
        self._dirty = True
        self._blink_on = True

    # ----- output panel -----

    def out(self, text):
        cols = (PANEL_W - 24) // ui.mono_cell(OUTPUT_ZOOM)[0]
        parts = text.split("\n")
        if self.output and parts:
            first = self.output.pop() + parts[0]  # continue the unfinished line
            parts[0] = first
        for part in parts:
            chars = _chars(part)
            while len(chars) > cols:
                self.output.append("".join(chars[:cols]))
                chars = chars[cols:]
            self.output.append("".join(chars))
        while len(self.output) > MAX_OUTPUT:
            self.output.pop(0)
        now = switch.ticks_ms()
        if now - self._last_present > 50:         # live output, but not slower than the script
            self._last_present = now
            self.draw_panel()
            gfx.present()

    def _print(self, *args, sep=" ", end="\n"):
        self.out(sep.join(str(a) for a in args) + end)

    # ----- running -----

    def run_here(self):
        self.output = [""]
        self.error_line = -1
        self.set_status("Running... (+ and - stop it)", C_FUNC)
        self.draw()
        gfx.present()
        folder = self.path[:self.path.rfind("/")]
        env = {"__name__": "__main__", "__file__": self.path, "print": self._print}
        start = switch.ticks_ms()
        import sys
        added = folder not in sys.path
        if added:
            sys.path.insert(0, folder)
        try:
            exec(self.text(), env)
            self.set_status("Finished in %.2f s" % ((switch.ticks_ms() - start) / 1000), C_STRING)
        except KeyboardInterrupt:
            self.out("\n[stopped]\n")
            self.set_status("Stopped", CURSOR)
        except SystemExit:
            self.set_status("Finished (exit)", C_STRING)
        except Exception as e:
            tb = _format_exception(e)
            line = _error_line(tb.split("\n"))
            self.out("\n" + _script_frames(tb, self.name))
            if line > 0:
                self.error_line = line - 1
                self.cy, self.cx = self.error_line, 0
                self.clamp()
                self.scroll_to_cursor()
            self.set_status("Error%s: %s" % (" in line %d" % line if line > 0 else "",
                                              type(e).__name__), ERROR_TEXT)
        finally:
            if added and folder in sys.path:
                sys.path.remove(folder)
            try:
                switch.rumble(0)
            except Exception:
                pass
        self._dirty = True

    # ----- drawing -----

    def _line_tokens(self, chars):
        key = "".join(chars)
        tokens = self._tokens.get(key)
        if tokens is None:
            if len(self._tokens) > 1500:
                self._tokens = {}
            tokens = tokenize(chars)
            self._tokens[key] = tokens
        return tokens

    def draw_line(self, row):
        """Draw one visible row of the text (row = index on screen)."""
        index = self.top + row
        cw, ch = self.cw(), self.ch()
        y = TITLE_H + row * ch
        width = gfx.WIDTH - PANEL_W
        bg = ERROR_BG if index == self.error_line else (LINE_HI if index == self.cy else BG)
        gfx.fill_rect(0, y, self.gutter_w(), ch, GUTTER_BG)
        gfx.fill_rect(self.gutter_w(), y, width - self.gutter_w(), ch, bg)
        if index >= len(self.lines):
            return
        num = str(index + 1)
        ui.mono_text(self.gutter_w() - (len(num) + 1) * cw, y, num,
                     LINE_NUM_CUR if index == self.cy else LINE_NUM, self.zoom)
        chars = self.lines[index]
        x0 = self.text_x()
        cols = self.visible_cols()
        for start, end, color in self._line_tokens(chars):
            s, e = max(start, self.left), min(end, self.left + cols)
            if s < e:
                ui.mono_text(x0 + (s - self.left) * cw, y, "".join(chars[s:e]), color, self.zoom)
        if index == self.cy and self._blink_on:
            cx = x0 + (self.cx - self.left) * cw
            if x0 <= cx < width:
                gfx.fill_rect(cx, y, 2, ch, CURSOR)

    def draw_title(self):
        gfx.fill_rect(0, 0, gfx.WIDTH, TITLE_H, TITLE_BG)
        gfx.fill_rect(0, TITLE_H - 1, gfx.WIDTH, 1, BORDER)
        ui.text(16, 2, self.name + (" •" if self.modified else ""), ui.TEXT, 2)
        hint = "F5 run  Ctrl+F5 run full  Ctrl+S save  Esc close"
        ui.text(gfx.WIDTH - PANEL_W - ui.text_width(hint, 1) - 16, 10, hint, MUTED, 1)

    def draw_panel(self):
        x = gfx.WIDTH - PANEL_W
        gfx.fill_rect(x, TITLE_H, PANEL_W, gfx.HEIGHT - TITLE_H - STATUS_H, PANEL_BG)
        gfx.fill_rect(x, TITLE_H, 1, gfx.HEIGHT - TITLE_H - STATUS_H, BORDER)
        ui.text(x + 12, TITLE_H + 6, "Output", MUTED, 2)
        line_h = ui.mono_cell(OUTPUT_ZOOM)[1]
        rows = (gfx.HEIGHT - TITLE_H - STATUS_H - 48) // line_h
        shown = self.output[-rows:]
        for i, line in enumerate(shown):
            color = ERROR_TEXT if line.startswith("Traceback") or "Error" in line[:30] else TEXT
            ui.mono_text(x + 12, TITLE_H + 44 + i * line_h, line, color, OUTPUT_ZOOM)

    def draw_status(self):
        y = gfx.HEIGHT - STATUS_H
        gfx.fill_rect(0, y, gfx.WIDTH, STATUS_H, TITLE_BG)
        gfx.fill_rect(0, y, gfx.WIDTH, 1, BORDER)
        ui.text(12, y + 4, self.status[:90], self.status_color, 1)
        info = "Ln %d, Col %d   %s   A edit line  Y new line  X delete  ZR run  ZL undo  + save  B close" % (
            self.cy + 1, self.cx + 1, self.kb.layout.upper())
        ui.text(gfx.WIDTH - ui.text_width(info, 1) - 12, y + 4, info, MUTED, 1)

    def draw(self):
        self.draw_title()
        for row in range(self.visible_rows()):
            self.draw_line(row)
        rows_end = TITLE_H + self.visible_rows() * self.ch()
        gfx.fill_rect(0, rows_end, gfx.WIDTH - PANEL_W, gfx.HEIGHT - STATUS_H - rows_end, BG)
        self.draw_panel()
        self.draw_status()
        self._dirty = False

    # ----- input -----

    def keyboard(self):
        """Handles USB keyboard events. Returns "close", "run" or None."""
        for ev in self.kb.poll():
            k = ev.code
            if ev.ctrl:
                if k == keys.S:
                    self.save()
                elif k == keys.Z:
                    self.do_undo()
                elif k == keys.F5:
                    return "run"
                elif k == keys.HOME:
                    self.cy = self.cx = 0
                    self.move()
                elif k == keys.END:
                    self.cy = len(self.lines) - 1
                    self.cx = len(self.lines[self.cy])
                    self.move()
                elif k == keys.EQUAL and self.zoom < len(ui.MONO_SIZES) - 1:
                    self.zoom += 1
                    self.move()
                elif k == keys.MINUS and self.zoom > 0:
                    self.zoom -= 1
                    self.move()
                continue
            if k == keys.ESCAPE:
                return "close"
            if k == keys.F5:
                self.run_here()
            elif k in (keys.ENTER, keys.KP_ENTER):
                self.newline()
            elif k == keys.BACKSPACE:
                self.backspace()
            elif k == keys.DELETE:
                self.delete()
            elif k == keys.TAB:
                self.insert(" " * (4 - self.cx % 4))
            elif k == keys.UP:
                self.move(dy=-1)
            elif k == keys.DOWN:
                self.move(dy=1)
            elif k == keys.LEFT:
                self.move(dx=-1)
            elif k == keys.RIGHT:
                self.move(dx=1)
            elif k == keys.HOME:
                line = self.lines[self.cy]
                indent = 0
                while indent < len(line) and line[indent] == " ":
                    indent += 1
                self.cx = 0 if self.cx == indent else indent   # smart Home
                self.move()
            elif k == keys.END:
                self.cx = len(self.lines[self.cy])
                self.move()
            elif k == keys.PAGE_UP:
                self.move(dy=-self.visible_rows())
            elif k == keys.PAGE_DOWN:
                self.move(dy=self.visible_rows())
            elif ev.char:
                self.insert(ev.char)
        return None

    def mouse_input(self):
        m = self.mouse.poll()
        if not m.connected:
            return
        if m.wheel:
            self.top = max(0, min(len(self.lines) - 1, self.top - m.wheel * 3))
            self._dirty = True
        if m.pressed & keys.MOUSE_LEFT and m.x < gfx.WIDTH - PANEL_W and TITLE_H <= m.y < gfx.HEIGHT - STATUS_H:
            self.cy = self.top + (m.y - TITLE_H) // self.ch()
            self.cx = self.left + max(0, (m.x - self.text_x()) // self.cw())
            self.clamp()
            self._undo_kind = None
            self._dirty = True

    def buttons(self):
        """Joy-Con controls. Returns "close" or None."""
        down = switch.buttons_down()
        held = switch.buttons()
        now = switch.ticks_ms()
        dirs = switch.UP | switch.DOWN | switch.LEFT | switch.RIGHT
        if down & dirs:
            self._repeat_at = now + 400
        elif held & dirs and now >= self._repeat_at:
            down |= held & dirs
            self._repeat_at = now + 60
        if down & switch.UP:
            self.move(dy=-1)
        if down & switch.DOWN:
            self.move(dy=1)
        if down & switch.LEFT:
            self.move(dx=-1)
        if down & switch.RIGHT:
            self.move(dx=1)
        if down & switch.A:
            self.edit_line()
        if down & switch.Y:
            self.edit_line(new_line_below=True)
        if down & switch.X:
            self.delete_line()
        if down & switch.ZR:
            self.run_here()
        if down & switch.ZL:
            self.do_undo()
        if down & switch.PLUS:
            self.save()
        if down & switch.B:
            return "close"
        return None

    def confirm_close(self):
        if not self.modified:
            return True
        choice = ui._dialog("Unsaved changes", "Save %s before closing?" % self.name,
                            ["Save", "Discard", "Cancel"])
        self._dirty = True
        if choice == 0:
            self.save()
            return not self.modified
        return choice == 1

    def run(self):
        """Event loop. Returns None, or "run" to run the saved file in a clean interpreter."""
        switch.buttons_down()
        while switch.running():
            action = self.keyboard() or self.buttons()
            self.mouse_input()
            if action == "close" and self.confirm_close():
                return None
            if action == "run":
                if self.modified:
                    self.save()
                if not self.modified:
                    return "run"
            now = switch.ticks_ms()
            if now >= self._blink_at:
                self._blink_at = now + 500
                self._blink_on = not self._blink_on
                if not self._dirty and self.top <= self.cy < self.top + self.visible_rows():
                    self.draw_line(self.cy - self.top)
                    gfx.present()
                    continue
            if self._dirty:
                self.draw()
                gfx.present()
            else:
                switch.sleep_ms(16)
        return None


def _format_exception(e):
    try:
        import io
        import sys
        buf = io.StringIO()
        sys.print_exception(e, buf)
        return buf.getvalue()
    except Exception:
        return "%s: %s\n" % (type(e).__name__, e)


def _script_frames(tb, name):
    """The traceback without the editor's own frames, with the file name instead of <string>."""
    out = []
    lines = tb.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("File ") and '"<string>"' not in line:
            i += 1
            if i < len(lines) and lines[i].startswith("    "):
                i += 1                              # the source line shown under the frame
            continue
        out.append(line.replace('"<string>"', '"%s"' % name))
        i += 1
    return "\n".join(out)


def _error_line(output):
    """Line number of the last traceback entry in the edited script ("<string>"), or 0."""
    for text in reversed(output):
        i = text.find('"<string>", line ')
        if i >= 0:
            digits = ""
            for c in text[i + 17:]:
                if not c.isdigit():
                    break
                digits += c
            return int(digits) if digits else 0
    return 0


def edit(path):
    """Open path in the editor. Returns None, or "run" (run the saved file full screen)."""
    return Editor(path).run()


NEW_SCRIPT = '''__NXTOOLBOX_MODULE__ = {
    "title": "%s",
    "description": "",
    "version": "1.0",
}

import switch

print("Hello from %s!")
'''


def create(path):
    """Create a new script from a small template (does not overwrite existing files)."""
    try:
        open(path).close()
        return False
    except OSError:
        pass
    title = path.split("/")[-1][:-3] if path.endswith(".py") else path.split("/")[-1]
    with open(path, "w") as f:
        f.write(NEW_SCRIPT % (title, title))
    return True
