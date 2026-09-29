"""usbmsc - USB Mass Storage (SCSI over Bulk-Only Transport) block access, built on the
built-in usbhost module. Lets scripts read raw sectors off a USB flash drive or SD/USB
card reader the way the system itself would, since NXToolBox does not claim mass storage
interfaces for itself (see usbhost.devices()).

    import usbmsc
    found = usbmsc.drives()
    if found:
        drive = usbmsc.Drive(found[0])
        print(drive.block_count, drive.block_size)
        boot_sector = drive.read_blocks(0, 1)
        drive.close()

Read-only (no SCSI WRITE support) and only the first LUN of each device is used - enough
for lib/fat.py to mount a FAT-formatted drive. Not a general SCSI driver: error recovery
is best-effort (a couple of retries, no full reset/clear-stall state machine), matching
what ordinary USB flash drives need in practice.
"""
import struct
import switch
import usbhost

CLASS_MSC = 0x08
SUBCLASS_SCSI = 0x06
PROTO_BBB = 0x50                # bulk-only transport

_CBW_SIG = 0x43425355            # 'USBC'
_CSW_SIG = 0x53425355            # 'USBS'
_CBW_DATA_IN = 0x80

_MAX_XFER = 4096                 # cap of a single usbhost bulk transfer (see modusb.c)
_CHUNK_BLOCKS = 128              # sectors per SCSI READ(10) command (128 * 512 = 64 KB)


def drives():
    """USB interfaces that look like SCSI mass storage (bulk-only transport): pass one
    of these to Drive()."""
    return [d for d in usbhost.devices()
            if d["cls"] == CLASS_MSC and d["subcls"] == SUBCLASS_SCSI and d["proto"] == PROTO_BBB]


class Drive:
    """LUN 0 of a USB Mass Storage device, opened for block reads."""

    def __init__(self, info):
        self.vid, self.pid = info["vid"], info["pid"]
        self.bus, self.dev = info["bus"], info["dev"]
        self._h = usbhost.open(info["id"])
        self._ep_in = self._ep_out = None
        for addr, typ, _size in info["eps"]:
            if typ != usbhost.BULK:
                continue
            if addr & 0x80:
                self._ep_in = addr
            else:
                self._ep_out = addr
        if self._ep_in is None or self._ep_out is None:
            usbhost.close(self._h)
            raise OSError("mass storage device has no bulk endpoints")
        self._tag = 0
        self.block_size = 512
        self.block_count = 0
        try:
            self._open()
        except BaseException:
            self.close()
            raise

    # ---------- Bulk-Only Transport ----------

    def _clear_halt(self, ep):
        try:
            usbhost.ctrl(self._h, 0x02, 1, 0, ep, b"")   # CLEAR_FEATURE(ENDPOINT_HALT)
        except OSError:
            pass

    def _csw(self, tag):
        raw = usbhost.read(self._h, self._ep_in, 13, 2000)
        if not raw or len(raw) < 13:
            raise OSError("mass storage: no status (CSW)")
        sig, rtag, _residue, status = struct.unpack("<IIIB", raw)
        if sig != _CSW_SIG or rtag != tag:
            raise OSError("mass storage: bad status (CSW)")
        if status != 0:
            raise OSError("mass storage: command failed (status %d)" % status)

    def _command(self, cb, data_len=0):
        """Runs a 6/10-byte SCSI command block; returns the data-in phase (if any)."""
        self._tag = (self._tag + 1) & 0xFFFFFFFF
        cb_len = len(cb)                    # bCBWCBLength: the real command length, not padded
        cbw = struct.pack("<IIIBBB16s", _CBW_SIG, self._tag, data_len,
                          _CBW_DATA_IN if data_len else 0, 0, cb_len, cb + b"\x00" * (16 - cb_len))
        try:
            usbhost.write(self._h, self._ep_out, cbw, 2000)
            data = b""
            while len(data) < data_len:
                chunk = usbhost.read(self._h, self._ep_in, min(data_len - len(data), _MAX_XFER), 3000)
                if not chunk:
                    raise OSError("mass storage: timed out")
                data += chunk
            self._csw(self._tag)
        except OSError:
            self._clear_halt(self._ep_in)
            self._clear_halt(self._ep_out)
            raise
        return data

    # ---------- setup ----------

    def _open(self):
        ready = False
        for _ in range(3):
            try:
                self._command(b"\x00" * 6)          # TEST UNIT READY
                ready = True
                break
            except OSError:
                switch.sleep_ms(150)
        if not ready:
            self._command(b"\x00" * 6)              # let the error propagate

        # READ CAPACITY (10): 4-byte last LBA + 4-byte block size, both big-endian
        cap = self._command(bytes([0x25, 0, 0, 0, 0, 0, 0, 0, 0, 0]), 8)
        last_lba, block_size = struct.unpack(">II", cap)
        self.block_count = last_lba + 1
        self.block_size = block_size or 512

    # ---------- reads ----------

    def read_blocks(self, lba, count):
        """count * block_size bytes starting at sector lba."""
        out = bytearray()
        while count > 0:
            n = min(count, _CHUNK_BLOCKS)
            cb = struct.pack(">BBIBHB", 0x28, 0, lba, 0, n, 0)     # READ(10)
            out += self._command(cb, n * self.block_size)
            lba += n
            count -= n
        return bytes(out)

    def ping(self):
        """True if the device still responds to a basic command; False if it is gone
        (unplugged, or any other I/O failure). usbhost.devices() cannot tell - it does
        not list interfaces that are already open, which is exactly this one."""
        try:
            self._command(b"\x00" * 6)          # TEST UNIT READY
            return True
        except OSError:
            return False

    def close(self):
        try:
            usbhost.close(self._h)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
