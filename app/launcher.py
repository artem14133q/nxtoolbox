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

        scr = ui.Screen("NXToolBox",
                        hint="A: open / run   B: back   Y: refresh   X: delete   R: get scripts   +: exit",
                        on_back=self.back, on_key=self.key)
        self.scr = scr

        # Left: current folder, file list (takes all free space), status line
        left = ui.VBox(spacing=12)
        self.path = left.add(ui.Label("", color=ui.MUTED))
        self.list = left.add(ui.ListBox(rows=8, w=600, on_select=self.open))
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
        scr.set_layout(root)
        scr.update = self.update

        if not self.refresh(remembered) and self.folder:
            self.folder = ""                            # the remembered folder is gone
            self.refresh()

    # ---------- file list ----------

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
        if down & switch.R:
            self.open_store()
            return True
        if down & switch.PLUS:
            if ui.confirm("Exit NXToolBox?", title="Exit", yes="Exit", no="Stay"):
                nxapp.quit()
                self.scr.close()
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