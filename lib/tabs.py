"""tabs - screens with tabs under the title, switched with L and R.

    import ui, tabs

    scr = tabs.TabScreen("NXToolBox")
    scr.add_tab("Files", files_layout)
    scr.add_tab("System", system_layout, update=refresh_system, on_key=system_keys,
                hint="Y: show serial")
    scr.run()

Each tab has its own layout; only the widgets of the active tab are drawn and receive
input. update() of a tab runs every frame while that tab is shown; on_key(down) of a tab
gets key presses before the screen's own on_key. hint replaces the help line while the
tab is shown ("L/R: tabs" is added in front). The focus is remembered per tab.
"""
import switch
import gfx
import ui

TAB_H = 48          # height of the tab bar


class TabScreen(ui.Screen):
    def __init__(self, title="", **kwargs):
        ui.Screen.__init__(self, title, **kwargs)
        self._user_key = self.on_key
        self.on_key = self._key
        self.tabs = []              # [title, layout, update, on_key, focus, hint]
        self._base_hint = self.hint
        self.tab = 0

    # ----- tabs -----

    def add_tab(self, title, layout, update=None, on_key=None, hint=None):
        """Add a tab; returns its index. The first tab is shown right away."""
        self.tabs.append([title, layout, update, on_key, None, hint])
        if len(self.tabs) == 1:
            self.select(0)
        return len(self.tabs) - 1

    def select(self, index):
        """Show a tab (the index wraps around)."""
        if not self.tabs:
            return
        if self.widgets:
            self.tabs[self.tab][4] = self.focus         # remember the focus of the old tab
        for w in self.widgets:
            w.focused = False
        self.widgets = []
        self.focus = None
        self.tab = index % len(self.tabs)
        hint = self.tabs[self.tab][5]
        hint = self._base_hint if hint is None else hint
        self.hint = ("L/R: tabs   " + hint) if hint else "L/R: tabs"
        self.set_layout(self.tabs[self.tab][1], self.margin)
        remembered = self.tabs[self.tab][4]
        if remembered in self.widgets:
            self.set_focus(remembered)

    # ----- ui.Screen hooks -----

    def _key(self, down):
        if down & switch.L:
            self.select(self.tab - 1)
            return True
        if down & switch.R:
            self.select(self.tab + 1)
            return True
        tab_key = self.tabs[self.tab][3] if self.tabs else None
        if tab_key and tab_key(down):
            return True
        return bool(self._user_key and self._user_key(down))

    def content_rect(self):
        x, y, w, h = ui.Screen.content_rect(self)
        return x, y + TAB_H, w, h - TAB_H

    def _paint(self):
        update = self.tabs[self.tab][2] if self.tabs else None
        if update:
            update()
        return ui.Screen._paint(self)

    def _redraw(self):
        ui.Screen._redraw(self)
        self._draw_tabs()

    def _draw_tabs(self):
        y = ui.TITLE_H if self.title else 0
        gfx.fill_rect(0, y, gfx.WIDTH, TAB_H, ui.BG)
        ui.fill(0, y + TAB_H - 1, gfx.WIDTH, 1, ui.BORDER)
        x = 24
        x = _key_hint(x, y, "L") + 12
        for i, entry in enumerate(self.tabs):
            title = entry[0]
            w = ui.text_width(title) + 40
            if i == self.tab:
                ui.box(x, y + 6, w, TAB_H - 12, ui.PANEL_HI, bg=ui.BG)
                ui.fill(x + 12, y + TAB_H - 3, w - 24, 3, ui.ACCENT)
                color = ui.TEXT
            else:
                color = ui.MUTED
            ui.text(x + 20, y + 8, title, color)
            x += w + 8
        _key_hint(x + 4, y, "R")


def _key_hint(x, y, label):
    """A small button icon ("L", "R"); returns the x after it."""
    w = max(ui.text_width(label) + 16, TAB_H - 16)
    ui.box(x, y + 8, w, TAB_H - 16, ui.BG, ui.MUTED, 2, min(ui.RADIUS, 8), ui.BG)
    ui.text(x + (w - ui.text_width(label)) // 2, y + 8, label, ui.MUTED)
    return x + w
