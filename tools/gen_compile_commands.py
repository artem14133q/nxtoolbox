#!/usr/bin/env python3
"""Creates compile_commands.json for CLion (and any clangd-based IDE).

Runs `make -n -B` (prints all build commands without running them),
picks the .c/.cpp compile commands from the output and saves them
to compile_commands.json in the project root.

Run from the project root:
    python3 tools/gen_compile_commands.py

Re-run after ./gen.sh and after adding new .c files.
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"              # build folder from the devkitPro template (BUILD := build)
SOURCE_EXTS = (".c", ".cpp", ".cc", ".cxx", ".m", ".s", ".S")
DROP_ARGS = {"-MMD", "-MP"}             # dependency-generation flags are not needed by the IDE


def is_compile_command(tokens):
    if not tokens or "-c" not in tokens:
        return False
    compiler = os.path.basename(tokens[0])
    return compiler.endswith(("gcc", "g++", "cc", "c++", "clang", "clang++"))


def clean_tokens(tokens):
    """Removes redirections, pipes and -MF <file>."""
    result = []
    skip_next = False
    for t in tokens:
        if skip_next:
            skip_next = False
            continue
        if t == "|":                    # an output filter follows, not part of the command
            break
        if t in DROP_ARGS:
            continue
        if t == "-MF":
            skip_next = True
            continue
        if t.startswith(("2>", ">", "1>")) or t in ("&&", ";"):
            continue
        result.append(t)
    return result


def find_source(tokens):
    i = tokens.index("-c")
    for t in tokens[i + 1:] + tokens[:i]:
        if t.endswith(SOURCE_EXTS) and not t.startswith("-"):
            return t
    return None


def main():
    if not os.environ.get("DEVKITPRO"):
        print("Warning: DEVKITPRO is not set, make may not find devkitPro.\n"
              "Usually: export DEVKITPRO=/opt/devkitpro", file=sys.stderr)

    # With make -n the outer Makefile does not create build/, but the inner make cds into it
    BUILD_DIR.mkdir(exist_ok=True)

    proc = subprocess.run(
        ["make", "-n", "-B"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    entries = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not is_compile_command(tokens):
            continue
        tokens = clean_tokens(tokens)
        src = find_source(tokens)
        if not src:
            continue
        src_path = Path(src) if os.path.isabs(src) else (BUILD_DIR / src)
        entries[str(src_path)] = {
            "directory": str(BUILD_DIR),
            "file": str(src_path),
            "arguments": tokens,
        }

    if not entries:
        print("No compile commands found. make output:\n", file=sys.stderr)
        print(proc.stdout[-3000:], file=sys.stderr)
        sys.exit(1)

    out = ROOT / "compile_commands.json"
    out.write_text(
        json.dumps(
            sorted(entries.values(), key=lambda e: e["file"]),
            indent=2,
            ensure_ascii=False
        )
    )
    print(f"Done: {out} ({len(entries)} files)")


if __name__ == "__main__":
    main()
