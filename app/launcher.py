"""NXToolBox start screen (launcher).

Lives at /switch/NXToolBox/launcher.py and runs every time the app shows its start screen.
It is plain Python, so it can be changed without rebuilding the app:

    python3 send.py upload app/launcher.py --to .

The app ships a copy of this file and lib/ in NXToolBox.nro and installs them into
/switch/NXToolBox/sys/. Files uploaded to /switch/NXToolBox/launcher.py or /switch/NXToolBox/lib/
take priority, so quick patches still work. Uploading a new launcher.py (or lib/ui.py)
restarts the launcher right away. Once per app start the launcher checks update_url.txt
for a newer version of the bundled files and offers to install it.
If the launcher fails, the app falls back to the built-in text menu (X there retries).
Hold - while starting the app to skip the launcher.

The nxapp module connects it to the app:
    nxapp.run(path)      run a script after the launcher exits (then close the screen)
    nxapp.quit()         exit the app after the launcher exits
    nxapp.restart()      start the launcher again after it exits
    nxapp.poll()         None or (kind, text): "upload", "run" (must exit now), "info"
    nxapp.state()        string kept between launcher runs; nxapp.set_state(s) stores it
    nxapp.info()         {"ip", "port", "password", "network"}
"""
import os
import switch
import nxapp
import ui
import tabs
import systab
import usbtab
import usbdisk_tab
import tiles
import modinfo
import settings_tab
import docs_tab
import about_tab

ROOT = "/switch/NXToolBox/scripts"
VERSION_FILE = "/switch/NXToolBox/sys/VERSION"
SELF_FILES = ("launcher.py", "lib/ui.py")    # uploading these restarts the launcher
BATTERY_EVERY_MS = 5000


def is_dir(path):
    try:
        return os.stat(path)[0] & 0x4000 != 0
    except OSError:
        return False


def sort_key(name):
    return name.lower()


def read_line(path):
    try:
        with open(path) as f:
            return f.readline().strip()
    except OSError:
        return ""


class Launcher:
    def __init__(self):
        saved = nxapp.state().split("\n")
        self.folder = saved[0]                          # relative to ROOT, "" is the root
        remembered = saved[1] if len(saved) > 1 else ""
        self.update_checked = len(saved) > 2 and saved[2] == "1"   # once per app start
        self.items = []
        self._battery_at = 0

        scr = tabs.TabScreen("NXToolBox",
                             hint="A: open / run   B: back   ZR: edit   ZL: new   Y: refresh   X: delete   +: exit",
                             on_back=self.back, on_key=self.key)
        self.scr = scr

        # Left: current folder, file list (takes all free space), status line
        left = ui.VBox(spacing=12)
        self.path = left.add(ui.Label("", color=ui.MUTED))
        self.list = left.add(tiles.TileGrid(describe=self.describe, on_select=self.open))
        self.status = left.add(ui.Label("", color=ui.MUTED))

        # Right: connection info
        info = nxapp.info()
        right = ui.VBox(spacing=8)
        right.add(ui.Label("Network", color=ui.MUTED))
        right.add(ui.Label("%s:%d" % (info["ip"], info["port"]) if info["network"] else "offline"))
        right.add_spacing(16)
        right.add(ui.Label("Password", color=ui.MUTED))
        right.add(ui.Label(info["password"]))
        right.add_spacing(16)
        right.add(ui.Label("Battery", color=ui.MUTED))
        self.battery = right.add(ui.Label("--", w=ui.CHAR_W * 4))
        right.add_spacing(16)
        right.add(ui.Label("Version", color=ui.MUTED))
        right.add(ui.Label(read_line(VERSION_FILE) or "dev"))
        right.add_spacing(24)
        right.add(ui.Button("Get scripts...", on_click=self.open_store))
        right.add_spacing(24)
        right.add(ui.Label("From your computer:\n  send.py upload file.py\n  send.py run file.py",
                           color=ui.MUTED, scale=1))
        right.add_stretch()

        root = ui.HBox(spacing=48)
        root.add(left, stretch=1)
        root.add(right)
        scr.add_tab("Files", root)

        self.system = systab.SystemTab()
        scr.add_tab("System", self.system.layout, update=self.system.update,
                    on_key=self.system.key, hint="Y: show / hide serial   +: exit")

        self.usb = usbtab.UsbTab()
        scr.add_tab("USB", self.usb.layout, update=self.usb.update,
                    on_key=self.usb.key, hint="Y: refresh   +: exit")

        self.usb_disk = usbdisk_tab.UsbDiskTab(scr)
        scr.add_tab("USB Drive", self.usb_disk.layout, update=self.usb_disk.update,
                    on_key=self.usb_disk.key, hint="A: open / copy   B: back   Y: refresh   +: exit")

        self.settings = settings_tab.SettingsTab(on_restart=self.restart_ui)
        scr.add_tab("Settings", self.settings.layout,
                    hint="A: apply theme   Left/Right: rounding   +: exit")

        self.docs = docs_tab.DocsTab()
        scr.add_tab("Docs", self.docs.layout, hint="A: open page   Up/Down or drag: scroll   +: exit")

        self.about = about_tab.AboutTab()
        scr.add_tab("About", self.about.layout, hint="Up/Down or drag: scroll   +: exit")
        scr.update = self.update

        if not self.refresh(remembered) and self.folder:
            self.folder = ""                            # the remembered folder is gone
            self.refresh()

    # ---------- file list ----------

    def describe(self, name):
        """Tile of a folder or script (title, description and icon from __NXTOOLBOX_MODULE__)."""
        return modinfo.tile_info(self.folder_path(), name, tiles.ICON, tiles.ICON_BG)

    def folder_path(self):
        return ROOT + "/" + self.folder if self.folder else ROOT

    def refresh(self, select=None):
        """Re-read the current folder; keeps the selection on `select` if it still exists."""
        base = self.folder_path()
        self.path.set_text("scripts/" + (self.folder + "/" if self.folder else ""))
        try:
            names = os.listdir(base)
        except OSError:
            self.items = []
            self.list.set_items([])
            self.status.set_text("Cannot open " + base)
            return False
        dirs, files = [], []
        for name in names:
            if name.startswith("."):
                continue
            if is_dir(base + "/" + name):
                dirs.append(name + "/")
            elif name.lower().endswith(".py"):
                files.append(name)
        dirs.sort(key=sort_key)
        files.sort(key=sort_key)
        self.items = dirs + files
        self.list.forget()                              # re-read descriptions and icons
        self.list.set_items(self.items)
        if select in self.items:
            self.list.select(self.items.index(select))
        if not self.items:
            self.status.set_text("No scripts here yet. Upload one: send.py upload file.py")
        return True

    def remember(self):
        nxapp.set_state(self.folder + "\n" + (self.list.selected_item() or "") + "\n" +
                        ("1" if self.update_checked else ""))

    def busy(self, text):
        self.status.set_text(text)
        self.scr.refresh_now()

    def check_updates(self):
        """Offer a newer version of the app's Python files (see tools/bundle.py)."""
        import installer
        self.update_checked = True
        self.remember()
        if not installer.update_url():
            return
        self.busy("Checking for updates...")
        try:
            manifest = installer.check_update()
        except Exception as e:
            self.status.set_text(("Update check failed: %s" % e)[:52])
            print("Update check failed:", e)            # full text in the log / send.py output
            return
        if not manifest:
            self.status.set_text("")
            return
        version = manifest["version"]
        if not ui.confirm("A new version is available:\n%s\n\nInstall it now?" % version,
                          title="Update", yes="Update", no="Later"):
            self.status.set_text("Update %s skipped" % version)
            return
        try:
            installer.install_update(manifest, self.busy)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.status.set_text("")
            ui.message("Update failed:\n%s" % e, title="Error")
            return
        nxapp.restart()                                 # start the new launcher
        self.scr.close()

    # ---------- actions ----------

    def open(self, index, name):
        if name.endswith("/"):
            self.folder = (self.folder + "/" if self.folder else "") + name[:-1]
            self.list.selected = self.list.top = 0
            self.status.set_text("")
            self.refresh()
            return
        self.remember()
        nxapp.run(self.folder_path() + "/" + name)
        self.scr.close()

    def back(self):
        if self.scr.tab != 0:                           # B does nothing outside the file list
            return
        if not self.folder:
            self.status.set_text("Press + to exit NXToolBox")
            return
        parts = self.folder.split("/")
        child = parts[-1] + "/"
        self.folder = "/".join(parts[:-1])
        self.list.selected = self.list.top = 0
        self.status.set_text("")
        self.refresh(child)

    def delete(self):
        name = self.list.selected_item()
        if not name or name.endswith("/"):
            self.status.set_text("Only files can be deleted")
            return
        if ui.confirm("Delete %s?" % name, title="Delete", yes="Delete", no="Cancel"):
            try:
                os.remove(self.folder_path() + "/" + name)
                self.status.set_text("Deleted " + name)
            except OSError as e:
                self.status.set_text("Cannot delete: %s" % e)
            self.refresh()

    def edit_selected(self):
        """Open the selected script in the editor (ZR)."""
        name = self.list.selected_item()
        if not name or not name.endswith(".py"):
            self.status.set_text("Select a .py file to edit")
            return
        self.open_editor(self.folder_path() + "/" + name)

    def new_script(self):
        """Create a script in the current folder and open it (ZL)."""
        import editor
        name = switch.keyboard("", "New script name")
        if not name:
            return
        name = name.strip().replace("/", "_")
        if not name.endswith(".py"):
            name += ".py"
        path = self.folder_path() + "/" + name
        if not editor.create(path):
            self.status.set_text(name + " already exists, opening it")
        self.refresh(name)
        self.open_editor(path)

    def open_editor(self, path):
        import editor
        action = editor.edit(path)
        self.refresh(path.split("/")[-1])
        self.scr.relayout()                             # the editor drew over the whole screen
        if action == "run":                             # Ctrl+F5: run the saved file full screen
            self.remember()
            nxapp.run(path)
            self.scr.close()

    def restart_ui(self):
        """Start the launcher again (a new theme is loaded on start)."""
        self.remember()
        nxapp.restart()
        self.scr.close()

    def open_store(self):
        import store                                    # loaded only when needed
        path = store.run()
        if path:                                        # "Run it now?" after installing
            self.remember()
            nxapp.run(path)
            self.scr.close()
            return
        self.refresh(self.list.selected_item())

    def key(self, down):
        if down & switch.PLUS:
            if ui.confirm("Exit NXToolBox?", title="Exit", yes="Exit", no="Stay"):
                nxapp.quit()
                self.scr.close()
            return True
        if self.scr.tab != 0:                           # the keys below are for the file list
            return False
        if down & switch.ZR:
            self.edit_selected()
            return True
        if down & switch.ZL:
            self.new_script()
            return True
        if down & switch.Y:
            self.refresh(self.list.selected_item())
            self.status.set_text("List refreshed")
            return True
        if down & switch.X:
            self.delete()
            return True
        return False

    # ---------- every frame ----------

    def update(self):
        if not self.update_checked:
            self.check_updates()                        # after the first frame is on screen
            return
        event = nxapp.poll()
        if event:
            kind, text = event
            if kind == "run":
                self.remember()
                self.scr.close()                        # the app runs the network script now
                return
            if kind == "upload":
                if text in SELF_FILES:
                    self.remember()
                    nxapp.restart()                     # load the new launcher / ui library
                    self.scr.close()
                    return
                self.status.set_text("Uploaded " + text)
                self.refresh(self.list.selected_item())
            else:
                self.status.set_text(text)

        now = switch.ticks_ms()
        if now >= self._battery_at:
            self._battery_at = now + BATTERY_EVERY_MS
            try:
                self.battery.set_text("%d%%" % switch.battery())
            except OSError:
                pass


if __name__ == "__main__":
    Launcher().scr.run()
