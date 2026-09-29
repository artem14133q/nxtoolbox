"""markdown - a Markdown parser for NXToolBox's docs and help text, close to what GitHub
renders: headings (#, ##, ###), paragraphs, bullet/numbered/nested lists, blockquotes
(>), fenced code blocks (```), tables, horizontal rules (---) and inline **bold**,
*italic*, ~~strikethrough~~, `code` and [links](url) spans. Not full CommonMark (no
images, no nested inline emphasis, no escaped characters) - enough for real README-style
docs. Pairs with textview.TextView, which renders the result.

    import markdown
    blocks = markdown.parse(text)
    # [{"kind": "h1"/"h2"/"h3"/"p"/"li"/"quote"/"code"/"hr"/"table", ...}, ...]
    # "text" is raw Markdown (inline markers not yet removed) for every kind except
    # "code" (shown as is) and "table" (see "rows"/"align" instead).
    # "li" also has "marker" ("-" or "1.", "2.", ...) and "depth" (0, 1, 2, ... - 2 spaces
    # of source indentation per level).
    # "table" has "rows" ([[cell, ...], ...], first row is the header) and "align"
    # (["left"/"right"/"center"/"", ...] per column).
    # A line right below a paragraph or list item with no marker of its own is treated as
    # its continuation, same as in the source Markdown; blockquote lines are not (every
    # line needs its own ">").

    segments = markdown.parse_inline(blocks[0]["text"])
    # [{"text": str, "bold": bool, "italic": bool, "strike": bool, "code": bool,
    #   "link": bool}, ...]
"""


def parse_inline(text):
    """**bold**, *italic*, ~~strikethrough~~, `code` and [link](url) spans split out of
    a line of text, in order (the url itself is dropped - nothing here can navigate to
    it, so only the link's visible text is kept, styled differently). Unmatched or empty
    markers are left as literal characters, so ordinary text (file_name.py, "5 * 3") is
    never corrupted."""
    segments = []
    buf = []

    def flush():
        if buf:
            segments.append({"text": "".join(buf), "bold": False, "italic": False,
                             "strike": False, "code": False, "link": False})
            buf.clear()

    def span(txt, **style):
        flush()
        seg = {"bold": False, "italic": False, "strike": False, "code": False, "link": False}
        seg.update(style)
        seg["text"] = txt
        segments.append(seg)

    i, n = 0, len(text)
    while i < n:
        if text.startswith("**", i):
            j = text.find("**", i + 2)
            if j > i + 2:
                span(text[i + 2:j], bold=True)
                i = j + 2
                continue
        if text.startswith("~~", i):
            j = text.find("~~", i + 2)
            if j > i + 2:
                span(text[i + 2:j], strike=True)
                i = j + 2
                continue
        if text[i] == "`":
            j = text.find("`", i + 1)
            if j > i + 1:
                span(text[i + 1:j], code=True)
                i = j + 1
                continue
        if text[i] == "[":
            close = text.find("]", i + 1)
            if close > i + 1 and close + 1 < n and text[close + 1] == "(":
                end = text.find(")", close + 2)
                if end > close + 1:
                    span(text[i + 1:close], link=True)
                    i = end + 1
                    continue
        if text[i] == "*":
            j = text.find("*", i + 1)
            if j > i + 1:
                span(text[i + 1:j], italic=True)
                i = j + 1
                continue
        buf.append(text[i])
        i += 1
    flush()
    return segments


def _list_marker(stripped):
    """(marker, text) from a "- ", "* " or "1. " line, or None: marker is what to show
    ("-" or "1.", "2.", ...)."""
    if stripped[:2] in ("- ", "* "):
        return "-", stripped[2:]
    i = 0
    while i < len(stripped) and stripped[i].isdigit():
        i += 1
    if i > 0 and stripped[i:i + 2] == ". ":
        return stripped[:i] + ".", stripped[i + 2:]
    return None


def _indent_level(raw):
    """Leading whitespace (a tab counts as 4 spaces) as a nesting depth, 2 spaces/level."""
    n = 0
    for c in raw:
        if c == " ":
            n += 1
        elif c == "\t":
            n += 4
        else:
            break
    return n // 2


def _is_table_rule(stripped):
    """True for a table header separator: | --- | :---: | ---: | ..."""
    if "|" not in stripped:
        return False
    cells = [c.strip() for c in stripped.strip().strip("|").split("|")]
    if not cells:
        return False
    for c in cells:
        if not c or "-" not in c or not all(ch in "-:" for ch in c):
            return False
    return True


def _table_cells(raw):
    return [c.strip() for c in raw.strip().strip("|").split("|")]


def _table_align(rule_cells):
    align = []
    for c in rule_cells:
        left, right = c.startswith(":"), c.endswith(":")
        align.append("center" if left and right else "right" if right else "left" if left else "")
    return align


def parse(text):
    """[{"kind", ...}, ...] blocks, in order."""
    blocks = []
    parts = []
    open_kind = None                # None, "p", "li" or "quote": what parts belongs to
    open_marker = open_depth = None
    in_code = False
    code_lines = []

    def flush():
        if open_kind == "li":
            blocks.append({"kind": "li", "text": " ".join(parts),
                           "marker": open_marker, "depth": open_depth})
        elif open_kind:
            blocks.append({"kind": open_kind, "text": " ".join(parts)})
        parts.clear()

    lines = text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        if in_code:
            if stripped.startswith("```"):
                blocks.append({"kind": "code", "text": "\n".join(code_lines)})
                code_lines = []
                in_code = False
            else:
                code_lines.append(raw.rstrip())
            i += 1
            continue

        if stripped.startswith("```"):
            flush()
            open_kind = None
            in_code = True
            i += 1
            continue

        if not stripped:
            flush()
            open_kind = None
            i += 1
            continue

        if stripped.startswith("### "):
            flush()
            open_kind = None
            blocks.append({"kind": "h3", "text": stripped[4:]})
            i += 1
            continue
        if stripped.startswith("## "):
            flush()
            open_kind = None
            blocks.append({"kind": "h2", "text": stripped[3:]})
            i += 1
            continue
        if stripped.startswith("# "):
            flush()
            open_kind = None
            blocks.append({"kind": "h1", "text": stripped[2:]})
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            flush()
            open_kind = None
            blocks.append({"kind": "hr", "text": ""})
            i += 1
            continue

        # a table: a "|...|" row immediately followed by a "| --- |" separator row
        if "|" in stripped and i + 1 < n and _is_table_rule(lines[i + 1].strip()):
            flush()
            open_kind = None
            rows = [_table_cells(raw)]
            align = _table_align(_table_cells(lines[i + 1]))
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_table_cells(lines[i]))
                i += 1
            blocks.append({"kind": "table", "rows": rows, "align": align})
            continue

        if stripped.startswith("> "):
            if open_kind != "quote":
                flush()
                open_kind = "quote"
            parts.append(stripped[2:])
            i += 1
            continue

        marker = _list_marker(stripped)
        if marker is not None:
            flush()
            open_kind = "li"
            open_marker, item_text = marker
            open_depth = _indent_level(raw)
            parts.append(item_text)
            i += 1
            continue

        if open_kind is None:               # a line with no marker starts a paragraph...
            open_kind = "p"
        parts.append(stripped)              # ...or continues whatever is already open
        i += 1

    flush()
    if in_code and code_lines:              # an unterminated fence: show what there is
        blocks.append({"kind": "code", "text": "\n".join(code_lines)})
    return blocks
