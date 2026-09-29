"""settings_tab - the "Settings" tab of the launcher: theme and corner rounding.

    import settings_tab
    page = settings_tab.SettingsTab(on_restart=restart_launcher)
    scr.add_tab("Settings", page.layout, hint="...")

The corner radius applies right away (and is saved); a new theme is saved and applied by
restarting the launcher (on_restart). Your own themes: ini files in /switch/NXToolBox/themes/
(see themes/dark.ini for the format).
"""
import ui
import theme

MAX_RADIUS = 16


class SettingsTab:
    def __init__(self, on_restart=None):
        self.on_restart = on_restart
        current = theme.current()
        self.themes = theme.available()             # [(name, title)]
        names = [name for name, _ in self.themes]
        self.theme_list = ui.ListBox([title for _, title in self.themes], rows=6, w=420,
                                     on_select=self._choose)
        if current.name in names:
            self.theme_list.select(names.index(current.name))

        self.radius = ui.Slider(value=min(ui.RADIUS, MAX_RADIUS), maximum=MAX_RADIUS, step=2,
                                w=320, on_change=self._radius)
        self.status = ui.Label("Theme: %s" % current.title, color=ui.MUTED)

        left = ui.VBox(spacing=12)
        left.add(ui.Label("Theme", color=ui.MUTED))
        left.add(self.theme_list, stretch=1)
        left.add(ui.Button("Apply theme", on_click=self._apply))

        preview = ui.HBox(spacing=24)
        preview.add(ui.Button("Button"))
        preview.add(ui.Checkbox("Option", checked=True))
        preview.add_stretch()

        right = ui.VBox(spacing=16)
        right.add(ui.Label("Corner rounding", color=ui.MUTED))
        right.add(self.radius)
        right.add_spacing(16)
        right.add(ui.Label("Preview", color=ui.MUTED))
        right.add(preview)
        right.add(ui.ProgressBar(0.6, w=320))
        right.add_stretch()
        right.add(self.status)

        root = ui.HBox(spacing=48)
        root.add(left)
        root.add(right, stretch=1)
        self.layout = root

    def _radius(self, value):
        ui.set_rounded(value)                        # redraws the screen with the new corners
        theme.save_settings(radius=value)

    def _choose(self, index, item):
        self._apply()

    def _apply(self):
        name, title = self.themes[self.theme_list.selected]
        if name == theme.current().name:
            self.status.set_text("%s is already in use" % title)
            return
        theme.save_settings(theme=name)
        if self.on_restart:
            self.on_restart()                        # colors are read when the GUI starts
        else:
            self.status.set_text("Saved: %s (restart to apply)" % title)
