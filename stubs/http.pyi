"""IDE hints: the built-in `http` module from NXToolBox (libcurl, runs only on the Switch).
Most scripts use lib/requests.py, which wraps it.

HTTPS certificates are checked against /switch/NXToolBox/cacert.pem (see README);
verify=False disables the check. Transfers stop on + and - / Ctrl+C like any script.
"""
from typing import Dict, Optional, Tuple, Union


def request(method: str, url: str, data: Optional[Union[bytes, str]] = None,
            headers: Optional[Dict[str, str]] = None, timeout: int = 30,
            verify: bool = True, max_size: int = 1048576) -> Tuple[int, bytes]:
    """Perform a request; returns (status, body). Follows redirects.
    OSError on network errors or if the body is larger than max_size."""
    ...


def download(url: str, path: str, timeout: int = 300, verify: bool = True) -> int:
    """Stream the response into a file ("/switch/..." path); returns the status.
    The file is written (replacing the old one) only if the status is 2xx."""
    ...
