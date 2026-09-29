#!/usr/bin/env python3
"""Prepares the Python files that ship inside NXToolBox.nro (RomFS) and the manifest for
online updates. The Makefile runs it before every build.

Creates:
    romfs/launcher.py, romfs/lib/*.py   copies of app/launcher.py and lib/*.py
    romfs/VERSION                       newest modification time of those files (UTC,
                                        YYYYMMDDHHMMSS), so a newer build has a larger version
    romfs/update_url.txt                copy of update_url.txt, if it exists
    romfs/cacert.pem                    copy of cacert.pem, if it exists (trusted certificate
                                        authorities for HTTPS: https://curl.se/docs/caextract.html)
    romfs/themes/*.ini                  GUI themes from themes/ (installed to sys/themes)
    romfs/fonts/*.ttf                   GUI fonts from fonts/ (installed to sys/fonts; not part
                                        of online updates, they are large and rarely change)
    update.json                         manifest for online updates: commit and push it

On the Switch the app copies romfs/ to /switch/NXToolBox/sys/ whenever the bundled VERSION
is newer than the installed one. The launcher checks update_url.txt (the raw URL of
update.json in your repository) once per start and offers to install newer versions.
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROMFS = ROOT / "romfs"
UPDATE_URL = ROOT / "update_url.txt"
MANIFEST = ROOT / "update.json"


def sources():
    """{path on the Switch (relative to sys/): path in the project}"""
    files = {"launcher.py": "app/launcher.py"}
    for f in sorted((ROOT / "lib").glob("*.py")):
        files["lib/" + f.name] = "lib/" + f.name
    if (ROOT / "cacert.pem").is_file():
        files["cacert.pem"] = "cacert.pem"
    for f in sorted((ROOT / "themes").glob("*.ini")):
        files["themes/" + f.name] = "themes/" + f.name
    return files


def main():
    files = sources()
    missing = [src for src in files.values() if not (ROOT / src).is_file()]
    if missing:
        sys.exit("bundle: missing %s" % ", ".join(missing))

    newest = max((ROOT / src).stat().st_mtime for src in files.values())
    version = time.strftime("%Y%m%d%H%M%S", time.gmtime(newest))

    if ROMFS.exists():
        shutil.rmtree(ROMFS)
    (ROMFS / "lib").mkdir(parents=True)
    (ROMFS / "themes").mkdir()
    fonts = sorted((ROOT / "fonts").glob("*.ttf"))
    if fonts:
        (ROMFS / "fonts").mkdir()
        for f in fonts:
            shutil.copy2(f, ROMFS / "fonts" / f.name)
    for dest, src in files.items():
        shutil.copy2(ROOT / src, ROMFS / dest)
    (ROMFS / "VERSION").write_text(version + "\n")
    if UPDATE_URL.is_file():
        shutil.copy2(UPDATE_URL, ROMFS / "update_url.txt")

    manifest = {"version": version, "files": files}
    old = MANIFEST.read_text() if MANIFEST.is_file() else ""
    new = json.dumps(manifest, indent=2) + "\n"
    if new != old:
        MANIFEST.write_text(new)
    notes = []
    if not UPDATE_URL.is_file():
        notes.append("no update_url.txt: online updates off")
    if "cacert.pem" not in files:
        notes.append("no cacert.pem: HTTPS relies on the console's certificate store")
    if not fonts:
        notes.append("no fonts/*.ttf: the GUI uses the pixel font")
    print("bundle: version %s, %d files%s" % (version, len(files),
          "".join(" (%s)" % n for n in notes)))


if __name__ == "__main__":
    main()
