"""modinfo - reads the description of a script for the launcher tiles.

A script describes itself with a variable (anywhere in the first 16 KB of the file):

    __NXTOOLBOX_MODULE__ = {
        "title": "Snake",
        "description": "Classic snake game",
        "icon": "snake.png",          # relative to the script (PNG, JPEG, BMP, GIF, SVG)
        "version": "1.0",
        "author": "Artem",
    }

The file is NOT executed: only literals are understood (strings, numbers, True, False,
None, lists, tuples, dicts). Anything else makes the description empty.

A folder can have an icon too: icon.png or icon.svg inside it.
"""
VAR = "__NXTOOLBOX_MODULE__"
READ_LIMIT = 16384
FOLDER_ICONS = ("icon.png", "icon.svg")


class _Parser:
    """A tiny parser for Python literals (a safe subset of eval)."""

    def __init__(self, text, pos):
        self.s = text
        self.i = pos

    def _ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n\\":
                self.i += 1
            elif c == "#":
                end = s.find("\n", self.i)
                self.i = len(s) if end < 0 else end + 1
            else:
                break

    def _peek(self):
        self._ws()
        if self.i >= len(self.s):
            raise ValueError("unexpected end")
        return self.s[self.i]

    def _expect(self, c):
        if self._peek() != c:
            raise ValueError("expected " + c)
        self.i += 1

    def value(self):
        c = self._peek()
        if c == "{":
            return self._dict()
        if c in "[(":
            return self._list("]" if c == "[" else ")")
        if c in "\"'":
            text = self._string()
            while self.i < len(self.s) and self._peek() in "\"'":
                text += self._string()          # "adjacent " "strings" are joined
            return text
        if c.isdigit() or c in "-+.":
            return self._number()
        word = self._word()
        if word == "True":
            return True
        if word == "False":
            return False
        if word == "None":
            return None
        raise ValueError("not a literal: " + word)

    def _dict(self):
        self.i += 1
        d = {}
        while self._peek() != "}":
            key = self.value()
            self._expect(":")
            d[key] = self.value()
            if self._peek() == ",":
                self.i += 1
        self.i += 1
        return d

    def _list(self, closing):
        self.i += 1
        items = []
        while self._peek() != closing:
            items.append(self.value())
            if self._peek() == ",":
                self.i += 1
        self.i += 1
        return items

    def _string(self):
        s = self.s
        quote = s[self.i]
        self.i += 1
        out = []
        while True:
            if self.i >= len(s):
                raise ValueError("unterminated string")
            c = s[self.i]
            self.i += 1
            if c == quote:
                return "".join(out)
            if c == "\n":
                raise ValueError("unterminated string")
            if c == "\\" and self.i < len(s):
                e = s[self.i]
                self.i += 1
                out.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(e, e))
            else:
                out.append(c)

    def _number(self):
        start = self.i
        s = self.s
        while self.i < len(s) and (s[self.i].isdigit() or s[self.i] in "+-.eExXabcdefABCDEF_"):
            self.i += 1
        text = s[start:self.i].replace("_", "")
        try:
            return int(text, 0)                     # 42, -7, 0x1F
        except ValueError:
            return float(text)                      # 1.5, 2e3 (ValueError if neither)

    def _word(self):
        start = self.i
        s = self.s
        while self.i < len(s) and (s[self.i].isalpha() or s[self.i].isdigit() or s[self.i] == "_"):
            self.i += 1
        return s[start:self.i]


def parse(text):
    """The __NXTOOLBOX_MODULE__ dict from source text, or {}."""
    pos = 0
    while True:
        i = text.find(VAR, pos)
        if i < 0:
            return {}
        pos = i + len(VAR)
        if i > 0 and text[i - 1] != "\n":           # must be a top-level assignment
            continue
        rest = text[pos:pos + 8].lstrip(" \t")
        if not rest.startswith("=") or rest.startswith("=="):
            continue
        try:
            value = _Parser(text, text.index("=", pos) + 1).value()
        except (ValueError, IndexError):
            return {}
        return value if isinstance(value, dict) else {}


def read(path):
    """The description of the script at path, or {} (missing, unreadable or invalid)."""
    try:
        with open(path) as f:
            return parse(f.read(READ_LIMIT))
    except (OSError, UnicodeError):
        return {}


def tile_info(folder, name, icon_size=0, icon_bg=None):
    """Information for a launcher tile: {"title", "subtitle", "kind", "icon"?}.
    name is a file name or "folder/"; folder is the directory it is in."""
    if name.endswith("/"):
        info = {"title": name[:-1], "subtitle": "folder", "kind": "dir"}
        for fname in FOLDER_ICONS:
            if _load_icon(info, folder + "/" + name + fname, icon_size, icon_bg):
                break
        return info

    meta = read(folder + "/" + name)
    title = meta.get("title")
    subtitle = meta.get("description")
    if not subtitle and meta.get("version"):
        subtitle = "v%s" % meta["version"]
    info = {
        "title": str(title) if title else (name[:-3] if name.endswith(".py") else name),
        "subtitle": str(subtitle) if subtitle else "",
        "kind": "file",
        "meta": meta,
    }
    icon = meta.get("icon")
    if isinstance(icon, str) and icon and ".." not in icon:
        _load_icon(info, (icon if icon.startswith("/") else folder + "/" + icon), icon_size, icon_bg)
    return info


def _load_icon(info, path, size, bg):
    """True if path was actually loaded, so a caller trying several candidate paths
    (see FOLDER_ICONS) knows when to stop."""
    try:
        import image
        info["icon"] = image.load(path, size, size, bg)
        return True
    except (ImportError, OSError, MemoryError):
        return False