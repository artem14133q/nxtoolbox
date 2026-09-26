#!/usr/bin/env python3
"""Prepares the Python files that ship inside nxtest.nro (RomFS) and the manifest for
online updates. The Makefile runs it before every build.

Creates:
    romfs/launcher.py, romfs/lib/*.py   copies of app/launcher.py and lib/*.py
    romfs/VERSION                       newest modification time of those files (UTC,
                                        YYYYMMDDHHMMSS), so a newer build has a larger version
    romfs/update_url.txt                copy of update_url.txt, if it exists
    update.json                         manifest for online updates: commit and push it

On the Switch the app copies romfs/ to /switch/nxtest/sys/ whenever the bundled VERSION
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
    print("bundle: version %s, %d files%s" % (version, len(files),
                                              "" if UPDATE_URL.is_file() else " (no update_url.txt: online updates off)"))


if __name__ == "__main__":
    main()