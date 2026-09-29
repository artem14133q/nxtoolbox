#!/usr/bin/env python3
"""NXToolBox - run Python scripts and upload files to a Nintendo Switch.

Works on Windows, macOS and Linux. Requires Python 3.8+, no third-party packages.

Commands:
    send.py run SCRIPT.py                     run a script and show its output
    send.py upload FILE_OR_FOLDER ... [--to FOLDER]
                                              upload to /switch/NXToolBox/scripts
                                              (--to lib for modules, --to . for /switch/NXToolBox itself)
    send.py screenshot [-o FILE.png]          save a PNG of whatever is on screen right now,
                                              into screenshots/<timestamp>.png by default
                                              (graphics mode must be active - it is whenever
                                              the launcher or a script with a GUI is running)
    send.py input button A [B ...] [--hold MS]     fake holding button(s), for automated tests
    send.py input tap X Y [--hold MS]              fake a touch at (X, Y), 1280x720
    send.py input swipe X0 Y0 X1 Y1 [--ms MS]      fake a drag from one point to another
    send.py input release                          cancel any pending synthetic input

Connection (can be omitted if the environment variables are set):
    -H/--host  Switch IP address     or NXTOOLBOX_HOST
    -p/--password  password          or NXTOOLBOX_PASSWORD

Ctrl+C during run stops the script on the Switch; a second Ctrl+C exits immediately.
"""
import argparse
import codecs
import hashlib
import hmac
import os
import socket
import struct
import sys
import time
import zlib
from pathlib import Path, PurePosixPath

PORT = 5555
MAGIC = b"NXPY"
VERSION = 2
NONCE_SIZE = 16

CMD_RUN = b"R"
CMD_UPLOAD = b"U"
CMD_SCREENSHOT = b"S"
CMD_INPUT = b"I"

# Matches switch.A / switch.B / ... on the console (modules/switch/switch_hw.h)
BUTTON_BITS = {
    "A": 1 << 0, "B": 1 << 1, "X": 1 << 2, "Y": 1 << 3,
    "LSTICK": 1 << 4, "RSTICK": 1 << 5, "L": 1 << 6, "R": 1 << 7,
    "ZL": 1 << 8, "ZR": 1 << 9, "PLUS": 1 << 10, "MINUS": 1 << 11,
    "LEFT": 1 << 12, "UP": 1 << 13, "RIGHT": 1 << 14, "DOWN": 1 << 15,
}

CHUNK = 64 * 1024
MAX_UPLOAD = 256 * 1024 * 1024

# System files that are skipped when uploading a folder
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__"}


class NxError(Exception):
    pass


def setup_console():
    """Do not crash on characters the console cannot display (mostly Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise NxError("the Switch closed the connection")
        buf += chunk
    return buf


def connect(host, password, cmd):
    """Connect, pass the password check and send the command."""
    try:
        sock = socket.create_connection((host, PORT), timeout=5)
    except OSError as e:
        raise NxError(f"cannot connect to {host}:{PORT} ({e}). "
                      "Is NXToolBox running on the Switch? Is it on the same network?")
    try:
        hello = recv_exact(sock, 5 + NONCE_SIZE)
        if hello[:4] != MAGIC:
            raise NxError("something other than NXToolBox is answering at this address")
        if hello[4] != VERSION:
            raise NxError(f"protocol version mismatch: Switch has {hello[4]}, send.py has {VERSION}. "
                          "Update the app on the Switch or send.py")
        mac = hmac.new(password.encode("utf-8"), hello[5:], hashlib.sha256).digest()
        sock.sendall(mac + cmd)
        return sock
    except BaseException:
        sock.close()
        raise


def read_all_text(sock, timeout=30):
    """Read the server reply until the connection is closed."""
    sock.settimeout(timeout)
    data = b""
    while True:
        try:
            chunk = sock.recv(4096)
        except ConnectionResetError:
            break
        if not chunk:
            break
        data += chunk
    return data.decode("utf-8", errors="replace").strip()


# ---------- run ----------

def stream_output(sock):
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    # Short timeout instead of blocking forever: on Windows Ctrl+C does not
    # interrupt a blocked recv, so we give it a chance every 0.3 s.
    sock.settimeout(0.3)
    stopping = False
    while True:
        try:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except ConnectionResetError:
                break  # the Switch closed the connection before reading our data (e.g. wrong password)
            if not chunk:
                break
            sys.stdout.write(decoder.decode(chunk))
            sys.stdout.flush()
        except KeyboardInterrupt:
            if stopping:
                raise  # second Ctrl+C: exit immediately
            stopping = True
            print("\n[stopping the script... press Ctrl+C again to exit immediately]",
                  file=sys.stderr, flush=True)
            # Close only our sending side: the Switch raises KeyboardInterrupt,
            # and we keep reading to see the traceback
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass
    sys.stdout.write(decoder.decode(b"", final=True))
    sys.stdout.flush()


def cmd_run(args):
    script = Path(args.script)
    if not script.is_file():
        raise NxError(f"file not found: {script}")
    data = script.read_bytes()
    sock = connect(args.host, args.password, CMD_RUN)
    with sock:
        sock.sendall(struct.pack(">I", len(data)) + data)
        stream_output(sock)
    return 0


# ---------- upload ----------

def normalize_remote_dir(to):
    """--to lib/sub or lib\\sub -> PurePosixPath('lib/sub'); checks that the path is safe."""
    if not to:
        return PurePosixPath()
    parts = [p for p in to.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or ":" in p for p in parts):
        raise NxError(f"--to must be a path inside /switch/NXToolBox without '..': {to}")
    return PurePosixPath(*parts)


def collect_files(paths, remote_dir):
    """List of (local file, path on the Switch) pairs. Folders are walked recursively."""
    result = []
    for p in paths:
        local = Path(p)
        if local.is_file():
            result.append((local, remote_dir / local.name))
        elif local.is_dir():
            base = local.resolve()
            for f in sorted(base.rglob("*")):
                rel = f.relative_to(base)
                if any(part in SKIP_NAMES or part.startswith(".") for part in rel.parts):
                    continue
                if f.is_file():
                    # The folder keeps its name: upload mylib --to lib -> lib/mylib/...
                    result.append((f, remote_dir / base.name / PurePosixPath(*rel.parts)))
        else:
            raise NxError(f"not found: {local}")
    return result


def upload_one(args, local, remote):
    size = local.stat().st_size
    if size > MAX_UPLOAD:
        return False, "file is larger than 256 MB"
    path_bytes = str(remote).encode("utf-8")
    sock = connect(args.host, args.password, CMD_UPLOAD)
    with sock:
        sock.settimeout(30)
        try:
            sock.sendall(struct.pack(">H", len(path_bytes)) + path_bytes + struct.pack(">I", size))
            with local.open("rb") as f:
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    sock.sendall(chunk)
        except OSError:
            pass  # the Switch may have rejected us and closed early; the reply is read below
        reply = read_all_text(sock)
    if reply.startswith("ok"):
        return True, f"{size} bytes"
    return False, reply or "no reply from the Switch"


def cmd_upload(args):
    remote_dir = normalize_remote_dir(args.to)
    files = collect_files(args.paths, remote_dir)
    if not files:
        print("Nothing to upload.")
        return 0

    failed = 0
    for local, remote in files:
        ok, info = upload_one(args, local, remote)
        mark = "ok   " if ok else "ERROR"
        print(f"  {mark} /switch/NXToolBox/{remote}  ({info})")
        if not ok:
            failed += 1

    print(f"Uploaded: {len(files) - failed} of {len(files)}")
    return 1 if failed else 0


# ---------- screenshot ----------

# Next to send.py itself, not the current directory: screenshots always land in the same
# place in the project no matter where this is run from (gitignored - see .gitignore).
SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"


def _screenshot_path():
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = SCREENSHOTS_DIR / f"{stamp}.png"
    n = 1
    while path.exists():           # more than one screenshot within the same second
        n += 1
        path = SCREENSHOTS_DIR / f"{stamp}-{n}.png"
    return path


def _png_chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + \
        struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, width, height, rgba):
    """A minimal, valid PNG (8-bit RGBA, no filtering) from raw rgba bytes
    (width * height * 4, row by row) - no third-party packages, just zlib."""
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)                            # filter type 0 (None) for this row
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)   # 8 bpc, color type 6 = RGBA
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_png_chunk(b"IHDR", ihdr))
        f.write(_png_chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(_png_chunk(b"IEND", b""))


def cmd_screenshot(args):
    sock = connect(args.host, args.password, CMD_SCREENSHOT)
    with sock:
        sock.settimeout(15)
        if recv_exact(sock, 1) != b"\x01":
            raise NxError(read_all_text(sock) or "screenshot failed")
        width, height = struct.unpack(">II", recv_exact(sock, 8))
        size = width * height * 4
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(min(CHUNK, size - len(data)))
            if not chunk:
                raise NxError("connection lost while receiving the screenshot")
            data += chunk
    path = Path(args.output) if args.output else _screenshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_png(str(path), width, height, bytes(data))
    print(f"Saved {path} ({width}x{height})")
    return 0


# ---------- input (for automated testing) ----------
# Applied over the app's own frame loop on the console, so this command returns as soon
# as the Switch has set it up - it does not itself wait for hold/duration to elapse.
# The settle sleep below is what actually waits, so a screenshot taken right after sees
# the result rather than racing ahead of it.

_SETTLE_MARGIN = 0.05   # seconds added on top of hold/duration - a few frames to settle


def _send_input(args, payload):
    sock = connect(args.host, args.password, CMD_INPUT)
    with sock:
        sock.settimeout(10)
        sock.sendall(payload)
        reply = read_all_text(sock)
    if not reply.startswith("ok"):
        raise NxError(reply or "no reply from the Switch")


def cmd_input_button(args):
    mask = 0
    for name in args.buttons:
        key = name.strip().upper()
        if key not in BUTTON_BITS:
            raise NxError(f"unknown button {name!r} (known: {', '.join(BUTTON_BITS)})")
        mask |= BUTTON_BITS[key]
    _send_input(args, bytes([0]) + struct.pack(">IH", mask, args.hold))
    time.sleep(args.hold / 1000 + _SETTLE_MARGIN)
    return 0


def cmd_input_tap(args):
    _send_input(args, bytes([1]) + struct.pack(">HHH", args.x, args.y, args.hold))
    time.sleep(args.hold / 1000 + _SETTLE_MARGIN)
    return 0


def cmd_input_swipe(args):
    _send_input(args, bytes([2]) + struct.pack(">HHHHH", args.x0, args.y0, args.x1, args.y1, args.ms))
    time.sleep(args.ms / 1000 + _SETTLE_MARGIN)
    return 0


def cmd_input_release(args):
    _send_input(args, bytes([3]))
    return 0


# ---------- main ----------

def main():
    setup_console()

    common = argparse.ArgumentParser(add_help=False)

    common.add_argument(
        "-H",
        "--host",
        default=os.environ.get("NXTOOLBOX_HOST"),
        help="Switch IP address (default: NXTOOLBOX_HOST)"
    )

    common.add_argument(
        "-p",
        "--password",
        default=os.environ.get("NXTOOLBOX_PASSWORD"),
        help="password (default: NXTOOLBOX_PASSWORD)"
    )

    parser = argparse.ArgumentParser(description="Run scripts and upload files to a Nintendo Switch (NXToolBox)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", parents=[common], help="run a script")
    p_run.add_argument("script", help="path to a .py file")
    p_run.set_defaults(func=cmd_run)

    p_up = sub.add_parser("upload", parents=[common], help="upload files or folders")
    p_up.add_argument("paths", nargs="+", help="files and/or folders")
    p_up.add_argument(
        "--to",
        default="scripts",
        help="folder inside /switch/NXToolBox: scripts (default, shown in the menu), "
            "lib (modules for import), . (/switch/NXToolBox itself)"
    )
    p_up.set_defaults(func=cmd_upload)

    p_shot = sub.add_parser("screenshot", parents=[common], help="save a PNG of the current screen")
    p_shot.add_argument("-o", "--output",
                        help="output file (default: screenshots/<timestamp>.png next to send.py)")
    p_shot.set_defaults(func=cmd_screenshot)

    # -H/-p live only on the action subparsers below (button/tap/swipe/release), not here:
    # argparse would otherwise apply each subparser's own default for the same dest and
    # silently overwrite whatever was parsed at this level, if it were also defined here.
    p_in = sub.add_parser("input", help="fake a button press or touch, for automated testing")
    in_sub = p_in.add_subparsers(dest="action", required=True)

    p_btn = in_sub.add_parser("button", parents=[common], help="hold one or more buttons")
    p_btn.add_argument("buttons", nargs="+",
                       help="A, B, X, Y, L, R, ZL, ZR, PLUS, MINUS, UP, DOWN, LEFT, RIGHT, "
                            "LSTICK, RSTICK")
    p_btn.add_argument("--hold", type=int, default=120, help="milliseconds held (default: 120)")
    p_btn.set_defaults(func=cmd_input_button)

    p_tap = in_sub.add_parser("tap", parents=[common], help="touch one point (1280x720)")
    p_tap.add_argument("x", type=int)
    p_tap.add_argument("y", type=int)
    p_tap.add_argument("--hold", type=int, default=80, help="milliseconds held (default: 80)")
    p_tap.set_defaults(func=cmd_input_tap)

    p_swipe = in_sub.add_parser("swipe", parents=[common], help="drag from one point to another")
    p_swipe.add_argument("x0", type=int)
    p_swipe.add_argument("y0", type=int)
    p_swipe.add_argument("x1", type=int)
    p_swipe.add_argument("y1", type=int)
    p_swipe.add_argument("--ms", type=int, default=300, help="duration in milliseconds (default: 300)")
    p_swipe.set_defaults(func=cmd_input_swipe)

    p_rel = in_sub.add_parser("release", parents=[common],
                              help="cancel any pending synthetic input right away")
    p_rel.set_defaults(func=cmd_input_release)

    args = parser.parse_args()
    if not args.host:
        parser.error("Switch address required: -H IP or the NXTOOLBOX_HOST environment variable")
    if not args.password:
        parser.error("password required: -p PASSWORD or the NXTOOLBOX_PASSWORD environment variable")

    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except NxError as e:
        sys.exit(f"Error: {e}")
    except OSError as e:
        sys.exit(f"Connection error: {e}")
