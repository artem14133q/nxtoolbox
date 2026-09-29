"""fat - pure-Python, read-only FAT12/16/32 reader for a usbmsc.Drive (or anything with
the same block_size/block_count/read_blocks() interface). No exFAT, no writing.

    import usbmsc, fat
    drive = usbmsc.Drive(usbmsc.drives()[0])
    vol = fat.mount(drive)
    for entry in vol.listdir("Pictures"):
        print(entry["name"], entry["dir"], entry["size"])
    with vol.open("Pictures/photo.jpg") as f:
        data = f.read()
    vol.close()

Handles both a "superfloppy" drive (a FAT boot sector straight at LBA 0, common on small
media) and a drive partitioned with a classic MBR (used by most real flash drives) - it
looks at LBA 0 and falls back to reading the first FAT-type partition from the MBR.
Long file names (VFAT LFN entries) are decoded; 8.3 names are used when there is no LFN.
"""
import struct

_DIR_ENTRY_LFN = 0x0F
_ATTR_DIR = 0x10
_ATTR_VOLUME = 0x08

_MBR_TYPES = (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E)   # FAT12, FAT16, FAT16, FAT32-LBA, FAT32-LBA, FAT16-LBA

_DOT_NAMES = (b".          ", b"..         ")


def _ascii(raw):
    """Bytes -> str, one code point per byte (short names are ASCII in practice;
    MicroPython's bytes.decode() only understands utf-8/ascii, not OEM code pages)."""
    return "".join(chr(b) for b in raw)


def _utf16le(raw):
    """UTF-16LE bytes -> str, stopping at the 0x0000 terminator or 0xFFFF padding
    (LFN directory entries; MicroPython's bytes.decode() has no utf-16 support)."""
    chars = []
    for i in range(0, len(raw) - 1, 2):
        cu = raw[i] | (raw[i + 1] << 8)
        if cu in (0x0000, 0xFFFF):
            break
        chars.append(chr(cu))
    return "".join(chars)


def _looks_like_fat_boot(sector):
    if len(sector) < 512 or sector[0] not in (0xEB, 0xE9):
        return False
    if sector[0x36:0x39] == b"FAT" or sector[0x52:0x55] == b"FAT":
        return True
    bps = struct.unpack_from("<H", sector, 11)[0]
    return bps in (512, 1024, 2048, 4096) and sector[13] in (1, 2, 4, 8, 16, 32, 64, 128)


def mount(drive):
    """Reads the boot sector (through an MBR partition if there is one) and returns a
    FatVolume. Raises OSError if no FAT12/16/32 filesystem is found."""
    sector0 = drive.read_blocks(0, 1)
    base_lba, boot = 0, sector0
    if not _looks_like_fat_boot(sector0):
        if sector0[0x1FE:0x200] != b"\x55\xAA":
            raise OSError("no MBR or FAT boot sector on this drive")
        base_lba = None
        for i in range(4):
            entry = sector0[0x1BE + i * 16: 0x1BE + i * 16 + 16]
            if entry[4] in _MBR_TYPES:
                start, count = struct.unpack_from("<II", entry, 8)
                if count:
                    base_lba = start
                    break
        if base_lba is None:
            raise OSError("no FAT partition found in the MBR")
        boot = drive.read_blocks(base_lba, 1)
        if not _looks_like_fat_boot(boot):
            raise OSError("partition is not FAT12/16/32")
    return FatVolume(drive, base_lba, boot)


class FatVolume:
    def __init__(self, drive, base_lba, boot):
        bs = drive.block_size
        if struct.unpack_from("<H", boot, 11)[0] != bs:
            raise OSError("unsupported sector size")

        sec_per_clus = boot[13]
        reserved = struct.unpack_from("<H", boot, 14)[0]
        num_fats = boot[16]
        root_entries = struct.unpack_from("<H", boot, 17)[0]
        total16 = struct.unpack_from("<H", boot, 19)[0]
        fatsz16 = struct.unpack_from("<H", boot, 22)[0]
        total32 = struct.unpack_from("<I", boot, 32)[0]
        fatsz32 = struct.unpack_from("<I", boot, 36)[0]
        root_clus = struct.unpack_from("<I", boot, 44)[0]

        total_sectors = total16 or total32
        fat_size = fatsz16 or fatsz32
        if not (sec_per_clus and num_fats and fat_size and total_sectors):
            raise OSError("malformed FAT boot sector")

        root_dir_sectors = (root_entries * 32 + bs - 1) // bs
        first_data_sector = reserved + num_fats * fat_size + root_dir_sectors
        cluster_count = (total_sectors - first_data_sector) // sec_per_clus

        if cluster_count < 4085:
            fat_type = 12
        elif cluster_count < 65525:
            fat_type = 16
        else:
            fat_type = 32

        self.drive = drive
        self.base_lba = base_lba
        self.block_size = bs
        self.sectors_per_cluster = sec_per_clus
        self.fat_type = fat_type
        self.fat_start = reserved
        self.root_dir_sector = reserved + num_fats * fat_size    # FAT12/16 fixed root only
        self.root_dir_sectors = root_dir_sectors
        self.first_data_sector = first_data_sector
        self.root_cluster = root_clus if fat_type == 32 else None
        self.free_bytes = None                                  # unknown without FSInfo/full scan

        label = boot[0x47:0x52] if fat_type == 32 else boot[0x2B:0x36]
        self.label = _ascii(label).strip()

        self._fat_cache_index = None
        self._fat_cache = None
        self._fat12 = drive.read_blocks(self._lba(reserved), fat_size) if fat_type == 12 else None

    # ---------- FAT table ----------

    def _lba(self, sector):
        return self.base_lba + sector

    def _fat_entry(self, n):
        if self.fat_type == 12:
            off = n + n // 2
            two = self._fat12[off] | (self._fat12[off + 1] << 8)
            return (two >> 4) if (n & 1) else (two & 0x0FFF)
        size = 2 if self.fat_type == 16 else 4
        byte_off = n * size
        sector = self.fat_start + byte_off // self.block_size
        if sector != self._fat_cache_index:
            self._fat_cache = self.drive.read_blocks(self._lba(sector), 1)
            self._fat_cache_index = sector
        off = byte_off % self.block_size
        if self.fat_type == 16:
            return struct.unpack_from("<H", self._fat_cache, off)[0]
        return struct.unpack_from("<I", self._fat_cache, off)[0] & 0x0FFFFFFF

    def _end_of_chain(self, cluster):
        if self.fat_type == 12:
            return cluster >= 0xFF8
        if self.fat_type == 16:
            return cluster >= 0xFFF8
        return cluster >= 0x0FFFFFF8

    def _cluster_sector(self, cluster):
        return self.first_data_sector + (cluster - 2) * self.sectors_per_cluster

    def _read_cluster(self, cluster):
        return self.drive.read_blocks(self._lba(self._cluster_sector(cluster)), self.sectors_per_cluster)

    def _read_chain(self, cluster):
        """All bytes of a cluster chain (used for directories, which are small)."""
        out = bytearray()
        seen = set()
        while cluster >= 2 and not self._end_of_chain(cluster) and cluster not in seen:
            seen.add(cluster)
            out += self._read_cluster(cluster)
            cluster = self._fat_entry(cluster)
        return bytes(out)

    # ---------- directories ----------

    def _dir_bytes(self, cluster):
        if cluster is None:                             # the root: fixed area, or FAT32's chain
            if self.fat_type == 32:
                return self._read_chain(self.root_cluster)
            return self.drive.read_blocks(self._lba(self.root_dir_sector), self.root_dir_sectors)
        return self._read_chain(cluster)

    @staticmethod
    def _short_name(raw):
        base = _ascii(raw[0:8]).rstrip()
        ext = _ascii(raw[8:11]).rstrip()
        if base[:1] == "\x05":                            # 0xE5 as a real first character
            base = "\xE5" + base[1:]
        return base + "." + ext if ext else base

    def _parse_dir(self, raw):
        entries = []
        lfn_parts = []
        for off in range(0, len(raw), 32):
            e = raw[off:off + 32]
            first = e[0]
            if first == 0x00:
                break
            if first == 0xE5:
                lfn_parts = []
                continue
            attr = e[11]
            if attr == _DIR_ENTRY_LFN:
                lfn_parts.append(((e[0] & 0x1F), e[1:11] + e[14:26] + e[28:32]))
                continue
            if attr & _ATTR_VOLUME:                       # volume label (and not a directory)
                lfn_parts = []
                continue
            if e[0:11] in _DOT_NAMES:
                lfn_parts = []
                continue
            if lfn_parts:
                lfn_parts.sort(key=lambda p: p[0])
                name = _utf16le(b"".join(p[1] for p in lfn_parts))
            else:
                name = self._short_name(e[0:11])
            lfn_parts = []
            clus_hi = struct.unpack_from("<H", e, 20)[0]
            clus_lo = struct.unpack_from("<H", e, 26)[0]
            entries.append({
                "name": name,
                "dir": bool(attr & _ATTR_DIR),
                "size": struct.unpack_from("<I", e, 28)[0],
                "cluster": (clus_hi << 16) | clus_lo,
            })
        return entries

    def _dir_entries(self, cluster):
        return self._parse_dir(self._dir_bytes(cluster))

    def _resolve(self, path):
        node = {"name": "", "dir": True, "cluster": None, "size": 0}
        for part in [p for p in path.split("/") if p]:
            if not node["dir"]:
                raise OSError("not a directory: " + path)
            found = None
            for e in self._dir_entries(node["cluster"]):
                if e["name"].lower() == part.lower():
                    found = e
                    break
            if found is None:
                raise OSError("not found: " + path)
            node = found
        return node

    # ---------- public API ----------

    def listdir(self, path=""):
        """[{"name", "dir", "size"}, ...] of a folder ("" is the root)."""
        node = self._resolve(path)
        if not node["dir"]:
            raise OSError("not a directory: " + path)
        return self._dir_entries(node["cluster"])

    def open(self, path):
        """A read-only FatFile for the given path."""
        node = self._resolve(path)
        if node["dir"]:
            raise OSError("is a directory: " + path)
        return FatFile(self, node["cluster"], node["size"])

    def close(self):
        self.drive.close()


class FatFile:
    """Sequential, read-only access to one file's bytes."""

    def __init__(self, vol, cluster, size):
        self._vol = vol
        self._cluster = cluster
        self.size = size
        self._pos = 0
        self._buf = b""
        self._buf_off = 0

    def read(self, n=-1):
        left = self.size - self._pos
        if n < 0 or n > left:
            n = left
        out = bytearray()
        while n > 0:
            if self._buf_off >= len(self._buf):
                if self._cluster < 2 or self._vol._end_of_chain(self._cluster):
                    break
                self._buf = self._vol._read_cluster(self._cluster)
                self._buf_off = 0
                self._cluster = self._vol._fat_entry(self._cluster)
            take = min(n, len(self._buf) - self._buf_off)
            out += self._buf[self._buf_off:self._buf_off + take]
            self._buf_off += take
            self._pos += take
            n -= take
        return bytes(out)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
