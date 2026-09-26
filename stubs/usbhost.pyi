"""IDE hints: the built-in `usbhost` module from nxtest (runs only on the Switch).

Low-level access to USB devices connected to the Switch.
For everyday tasks lib/usbserial.py and lib/usbhid.py are more convenient.
All open interfaces are closed automatically when the script ends.
"""
from typing import List, Optional, Tuple, TypedDict, Union

BULK: int
"""Endpoint type: bulk (2)."""
INTERRUPT: int
"""Endpoint type: interrupt (3)."""


class InterfaceInfo(TypedDict):
    id: int            # pass to open()
    vid: int
    pid: int
    bus: int
    dev: int           # bus + dev identify the device
    path: str
    iface: int         # bInterfaceNumber
    cls: int           # interface class: 0x02 CDC, 0x03 HID, 0x0A CDC data, 0xFF vendor...
    subcls: int
    proto: int
    eps: List[Tuple[int, int, int]]   # (address, type, packet size); address & 0x80 means IN


def devices() -> List[InterfaceInfo]:
    """Interfaces available to open. Already open ones and those used by the system are not listed."""
    ...


def open(id: int) -> int:
    """Acquire an interface and return a handle."""
    ...


def close(handle: int) -> None: ...


def ctrl(handle: int, bm_request_type: int, b_request: int, w_value: int, w_index: int,
         data_or_length: Union[bytes, int] = ...) -> Union[bytes, int]:
    """Control request via endpoint 0.
    IN (bmRequestType & 0x80): the last argument is a length, returns bytes.
    OUT: the last argument is the data, returns the number of bytes sent."""
    ...


def read(handle: int, ep: int, size: int = 512, timeout_ms: int = 100) -> Optional[bytes]:
    """Read from a bulk/interrupt IN endpoint. None means timeout (the request stays active,
    the next read keeps waiting for it). timeout_ms < 0 waits without a limit."""
    ...


def write(handle: int, ep: int, data: bytes, timeout_ms: int = 1000) -> int:
    """Write to a bulk/interrupt OUT endpoint. OSError on timeout."""
    ...
