#!/usr/bin/env python3
"""Builds index.json for an NXToolBox script catalog.

Folder layout (one subfolder or one .py file = one package):

    my-catalog/
        snake/
            main.py
            board.py
            nxtoolbox.json    optional: {"title": "Snake", "version": "1.0",
                                      "description": "...", "main": "main.py"}
        hello.py

Usage:
    python3 tools/make_catalog.py my-catalog --name "My scripts"

Then publish the folder on any web server and add the URL of index.json on the Switch
(Get scripts -> Add a catalog):
    local network:  cd my-catalog && python3 -m http.server 8000
                    -> http://<computer IP>:8000/index.json
    GitHub:         push the folder to a repository
                    -> https://raw.githubusercontent.com/OWNER/REPO/main/index.json
"""
import argparse
import json
import sys
from pathlib import Path

MANIFEST = "nxtoolbox.json"
SKIP = {"__pycache__", ".DS_Store", "Thumbs.db", "index.json", MANIFEST}


def package_files(folder):
    files = []
    for f in sorted(folder.rglob("*")):
        rel = f.relative_to(folder)
        if f.is_file() and not any(p in SKIP or p.startswith(".") for p in rel.parts):
            files.append(rel.as_posix())
    return files


def main():
    ap = argparse.ArgumentParser(description="Build index.json for an NXToolBox script catalog")
    ap.add_argument("folder", help="catalog folder")
    ap.add_argument("--name", default=None, help="catalog name shown on the Switch")
    args = ap.parse_args()

    root = Path(args.folder)
    if not root.is_dir():
        sys.exit("not a folder: %s" % root)

    packages = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.name in SKIP or entry.name.startswith("."):
            continue
        if entry.is_dir():
            meta = {}
            manifest = entry / MANIFEST
            if manifest.is_file():
                meta = json.loads(manifest.read_text(encoding="utf-8"))
            files = ["%s/%s" % (entry.name, f) for f in package_files(entry)]
            if not files:
                continue
            main_name = meta.get("main") or ("main.py" if (entry / "main.py").is_file()
                                             else next((f.split("/", 1)[1] for f in files
                                                        if f.endswith(".py")), None))
            packages.append({
                "name": entry.name,
                "title": meta.get("title", entry.name),
                "version": str(meta.get("version", "")),
                "description": meta.get("description", ""),
                "files": files,
                "main": "%s/%s" % (entry.name, main_name) if main_name else None,
            })
        elif entry.suffix == ".py":
            packages.append({
                "name": entry.stem,
                "title": entry.stem,
                "version": "",
                "description": "",
                "files": [entry.name],
                "main": entry.name,
            })

    index = {"name": args.name or root.resolve().name, "packages": packages}
    out = root / "index.json"
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Wrote %s: %d package(s)" % (out, len(packages)))
    for p in packages:
        print("  %-20s %d file(s)%s" % (p["name"], len(p["files"]),
                                        ", main " + p["main"] if p["main"] else ""))


if __name__ == "__main__":
    main()