"""usbdisk_tab - the "USB Drive" tab of the launcher: browse a FAT-formatted USB flash
drive (via usbmsc + fat) and copy files off it onto the SD card.

    import usbdisk_tab
    page = usbdisk_tab.UsbDiskTab(scr)
    scr.add_tab("USB Drive", page.layout, update=page.update, on_key=page.key,
                hint="A: open / copy   B: back   Y: refresh")

Read-only: files are copied to /switch/NXToolBox/downloads/<same path>, nothing on the
drive itself is ever written. Only the first FAT12/16/32 drive found is mounted; while
none is found the tab retries every POLL_MS.
"""
import os
import switch
import ui
import usbmsc
import fat

DOWNLOAD_ROOT = "/switch/NXToolBox/downloads"
POLL_MS = 2000
COPY_CHUNK = 65536
LIST_W = 760


def _makedirs(path):
    current = ""
    for part in path.strip("/").split("/"):
        current += "/" + part
        try:
            os.mkdir(current)
        except OSError:
            pass                        # already exists


def _human_size(n):
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1024
    return "%.1f GB" % size


def _row_text(entry):
    if entry["dir"]:
        return entry["name"] + "/"
    return "%s  (%s)" % (entry["name"], _human_size(entry["size"]))


class UsbDiskTab:
    def __init__(self, scr):
        self.scr = scr
        self.drive = None                  # usbmsc.Drive
        self.vol = None                    # fat.FatVolume
        self.folder = ""                   # path relative to the volume root, "" is the root
        self.items = []                    # listdir() entries of the current folder
        self._next = 0
        self._known = None                 # signature of the last (unsuccessful) drive list seen,
                                            # so a drive that won't mount is not retried every tick

        root = ui.VBox(spacing=12)
        self.path = root.add(ui.Label("", color=ui.MUTED))
        self.list = root.add(ui.ListBox(rows=8, w=LIST_W, on_select=self._open), stretch=1)
        self.status = root.add(ui.Label("", color=ui.MUTED))
        self.layout = root

    # ---------- tab hooks ----------

    def update(self):
        now = switch.ticks_ms()
        if now < self._next:
            return
        self._next = now + POLL_MS
        if self.vol is None:
            self._try_mount()
        else:
            self._check_present()

    def key(self, down):
        if down & switch.Y:
            self._next = 0
            if self.vol is None:
                self._known = None         # force a retry even if the drive list looks unchanged
                self._try_mount()
            else:
                self._refresh()
            return True
        if down & switch.B and self.vol is not None and self.folder:
            self._up()
            return True
        return False

    def _update(self, status: str, path: str, items: list):
        self.status.set_text(status)
        self.path.set_text(path)
        self.list.set_items(items)

    # ---------- mounting ----------

    def _check_present(self):
        """While mounted: notice the drive being unplugged even if nothing reads from it.
        usbmsc.drives() would not help here - it never lists an interface we already
        have open, so a real (if tiny) command is the only way to tell."""
        if not self.drive.ping():
            self._unmount("USB drive disconnected")

    def _try_mount(self):
        found = usbmsc.drives()
        signature = tuple(sorted((d["vid"], d["pid"], d["bus"], d["dev"], d["iface"]) for d in found))
        if signature == self._known:
            return                          # already tried this exact set of drives, don't retry every tick
        self._known = signature
        if not found:
            self._update("No USB drive found", "", [])
            return

        self.status.set_text("Detecting USB drive...")
        self.scr.refresh_now()

        last_error = None
        for info in found:
            drive = None
            try:
                drive = usbmsc.Drive(info)
                self.vol = fat.mount(drive)
                self.drive = drive
                self.folder = ""
                self._refresh()
                return
            except OSError as e:
                last_error = e
                if drive:
                    drive.close()

        self._update("USB drive found, but no FAT filesystem on it: %s" % last_error, "", [])

    def _unmount(self, message):
        if self.vol:
            self.vol.close()
        self.vol = self.drive = None
        self._known = None                 # re-evaluate the drive list even if it looks unchanged
        self._update(message, "", [])

    # ---------- navigation ----------

    def _refresh(self):
        try:
            self.items = sorted(self.vol.listdir(self.folder),
                                key=lambda e: (not e["dir"], e["name"].lower()))
        except OSError as e:
            self._unmount("USB drive error: %s" % e)
            return
        self.path.set_text("/" + self.folder)
        self.list.set_items([_row_text(e) for e in self.items])
        label = ("  -  " + self.vol.label) if self.vol.label else ""
        self.status.set_text("%d item(s)%s" % (len(self.items), label))

    def _open(self, index, _name):
        entry = self.items[index]
        if entry["dir"]:
            self.folder = (self.folder + "/" if self.folder else "") + entry["name"]
            self.list.selected = self.list.top = 0
            self._refresh()
        else:
            self._copy_to_sd(entry)

    def _up(self):
        parts = self.folder.split("/")
        self.folder = "/".join(parts[:-1])
        self.list.selected = self.list.top = 0
        self._refresh()

    # ---------- copying ----------

    def _copy_to_sd(self, entry):
        if not ui.confirm('Copy "%s" (%s) to the SD card?' % (entry["name"], _human_size(entry["size"])),
                          title="Copy file", yes="Copy", no="Cancel"):
            return
        rel = (self.folder + "/" if self.folder else "") + entry["name"]
        dest = DOWNLOAD_ROOT + "/" + rel
        size = entry["size"]
        try:
            _makedirs(dest[:dest.rfind("/")])
            copied = 0
            with self.vol.open(rel) as src:
                with open(dest, "wb") as out:
                    while True:
                        chunk = src.read(COPY_CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        copied += len(chunk)
                        pct = copied * 100 // size if size else 100
                        self.status.set_text("Copying %s... %d%%" % (entry["name"], pct))
                        self.scr.refresh_now()
        except OSError as e:
            self.status.set_text("Copy failed: %s" % e)
            return
        self.status.set_text("Saved to downloads/%s" % rel)
