"""store - the "Get scripts" screen: install scripts from GitHub or plain URLs and from
script catalogs. Opened from the launcher (R or the "Get scripts" button).

    import store
    path = store.run()      # path of a script the user wants to run now, or None

URLs are typed with the system keyboard (switch.keyboard). Catalogs are kept in
/switch/NXToolBox/catalogs.txt ("Name | URL" per line), which can also be edited on the
computer and uploaded with: send.py upload catalogs.txt --to .
"""
import switch
import ui
import installer

URL_ITEM = "Download from a GitHub or file URL..."
ADD_ITEM = "Add a catalog..."
DESC_CHARS = 28                 # description column width in characters


def _ask(initial, hint):
    text = switch.keyboard(initial, hint)
    return text.strip() if text else None


def _report(error):
    ui.message("%s" % error, title="Error")


class Store:
    def __init__(self):
        self.catalogs = []
        self.scr = ui.Screen("Get scripts", hint="A: open    X: remove catalog    B: back",
                             on_key=self.key)
        root = ui.VBox(spacing=12)
        root.add(ui.Label("Choose a source", color=ui.MUTED))
        self.list = root.add(ui.ListBox(rows=8, w=600, on_select=self.open))
        self.status = root.add(ui.Label("", color=ui.MUTED))
        self.scr.set_layout(root)
        self.reload()

    def reload(self):
        self.catalogs = installer.load_catalogs()
        self.list.set_items([URL_ITEM, ADD_ITEM] + ["Catalog: " + name for name, _ in self.catalogs])

    def busy(self, text):
        self.status.set_text(text)
        self.scr.refresh_now()

    # ---------- actions ----------

    def open(self, index, item):
        try:
            if index == 0:
                self.from_url()
            elif index == 1:
                self.add_catalog()
            else:
                name, url = self.catalogs[index - 2]
                path = CatalogScreen(name, url, self).run()
                if path:
                    self.scr.close(path)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.busy("")
            _report(e)

    def from_url(self):
        url = _ask("https://github.com/", "GitHub or file URL")
        if not url:
            self.busy("No URL entered")
            return
        if "://" not in url:
            url = "https://" + url
        dest, count = installer.install_url(url, self.busy)
        self.busy("Installed scripts/" + dest)
        what = "%d files" % count if count > 1 else "1 file"
        ui.message("Installed %s to\nscripts/%s" % (what, dest), title="Done")

    def add_catalog(self):
        url = _ask("https://", "Catalog URL (index.json)")
        if not url:
            self.busy("No URL entered")
            return
        if "://" not in url:
            url = "https://" + url
        self.busy("Loading the catalog...")
        name = installer.add_catalog(url)
        self.reload()
        self.list.select(len(self.list.items) - 1)
        self.busy("Added catalog: " + name)

    def key(self, down):
        if down & switch.X:
            i = self.list.selected - 2
            if i >= 0 and self.list.focused:
                name, url = self.catalogs[i]
                if ui.confirm("Remove the catalog\n%s?" % name, yes="Remove", no="Cancel"):
                    installer.remove_catalog(url)
                    self.reload()
                    self.busy("Removed " + name)
            return True
        return False

    def run(self):
        return self.scr.run()


class CatalogScreen:
    """Packages of one catalog: list on the left, details on the right."""

    def __init__(self, name, url, store):
        self.url = url
        self.store = store
        store.busy("Loading " + name + "...")
        self.index = installer.fetch_catalog(url)
        store.busy("")
        self.packages = [p for p in self.index["packages"] if isinstance(p, dict) and p.get("name")]

        self.scr = ui.Screen(self.index.get("name") or name, hint="A: install / update    B: back")
        left = ui.VBox(spacing=12)
        self.list = left.add(ui.ListBox(rows=8, w=500, on_select=self.install,
                                        on_change=lambda i, item: self.show(i)))
        self.status = left.add(ui.Label("", color=ui.MUTED))

        right = ui.VBox(spacing=8)
        self.title = right.add(ui.Label("", w=ui.CHAR_W * DESC_CHARS))
        self.version = right.add(ui.Label("", color=ui.MUTED))
        right.add_spacing(8)
        self.desc = right.add(ui.Label("", color=ui.MUTED))
        right.add_stretch()

        root = ui.HBox(spacing=40)
        root.add(left, stretch=1)
        root.add(right)
        self.scr.set_layout(root)
        self.refresh()
        if not self.packages:
            self.status.set_text("This catalog is empty")

    def refresh(self):
        done = installer.installed()
        items = []
        for p in self.packages:
            label = p.get("title") or p["name"]
            have = done.get(p["name"])
            if have is not None:
                label += "  [installed]" if have == p.get("version", "") else "  [update]"
            items.append(label)
        self.list.set_items(items)
        self.show(self.list.selected)

    def show(self, i):
        if not self.packages:
            return
        p = self.packages[i]
        self.title.set_text(p.get("title") or p["name"])
        version = p.get("version")
        files = len(p.get("files") or [])
        self.version.set_text(("v%s, " % version if version else "") + "%d file(s)" % files)
        self.desc.set_text(ui.wrap(p.get("description", ""), DESC_CHARS))

    def busy(self, text):
        self.status.set_text(text)
        self.scr.refresh_now()

    def install(self, index, item):
        p = self.packages[index]
        title = p.get("title") or p["name"]
        if not ui.confirm("Install %s?" % title, yes="Install", no="Cancel"):
            return
        try:
            main = installer.install_package(self.url, p, self.busy)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.busy("")
            _report(e)
            return
        self.busy("Installed " + title)
        self.refresh()
        if main and ui.confirm("%s is installed.\nRun it now?" % title, yes="Run", no="Later"):
            self.scr.close(main)

    def run(self):
        return self.scr.run()


def run():
    """Show the store. Returns the path of a script to run now, or None."""
    return Store().run()