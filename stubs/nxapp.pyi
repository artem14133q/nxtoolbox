"""IDE hints: the built-in `nxapp` module (API for the Python start screen, app/launcher.py).

The launcher runs in its own interpreter. It cannot run scripts itself: it asks the app
with run() and closes its screen; the app runs the script and starts the launcher again.
"""
from typing import Dict, Optional, Tuple, Union


def run(path: str) -> None:
    """Run this script after the launcher exits. path as Python sees it, e.g.
    "/switch/NXToolBox/scripts/hello.py". Close the launcher screen right after calling it."""
    ...


def quit() -> None:
    """Exit the app after the launcher exits."""
    ...


def restart() -> None:
    """Start the launcher again after it exits (reloads launcher.py and libraries)."""
    ...


def poll() -> Optional[Tuple[str, str]]:
    """Handle pending network requests; call it every frame. Returns None or (kind, text):
    "upload" - a file was uploaded, text is the path relative to /switch/NXToolBox;
    "run"    - a script arrived over the network: the launcher must exit now;
    "info"   - a message (e.g. a rejected connection)."""
    ...


def state() -> str:
    """A string kept in memory between launcher runs (e.g. current folder and selection)."""
    ...


def set_state(s: str) -> None: ...


def info() -> Dict[str, Union[str, int, bool]]:
    """{"ip": str, "port": int, "password": str, "network": bool}"""
    ...