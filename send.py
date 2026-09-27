#!/usr/bin/env python3
"""NXToolBox - run Python scripts and upload files to a Nintendo Switch.

Works on Windows, macOS and Linux. Requires Python 3.8+, no third-party packages.

Commands:
    send.py run SCRIPT.py                     run a script and show its output
    send.py upload FILE_OR_FOLDER ... [--to FOLDER]
                                              upload to /switch/NXToolBox/scripts
                                              (--to lib for modules, --to . for /switch/NXToolBox itself)

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
from pathlib import Path, PurePosixPath

PORT = 5555
MAGIC = b"NXPY"
VERSION = 2
NONCE_SIZE = 16

CMD_RUN = b"R"
CMD_UPLOAD = b"U"

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
