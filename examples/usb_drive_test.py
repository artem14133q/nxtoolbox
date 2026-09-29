# Mounts the first FAT12/16/32 USB flash drive found and prints its contents as a tree.
# Connect the drive to a dock USB port, or through a USB-C OTG adapter in handheld mode.
import usbmsc
import fat

found = usbmsc.drives()
if not found:
    print("No USB mass storage device found.")
else:
    drive = usbmsc.Drive(found[0])
    print("VID %04x PID %04x  %d x %d bytes" % (drive.vid, drive.pid, drive.block_count, drive.block_size))
    try:
        vol = fat.mount(drive)
        print("FAT%d  label %r" % (vol.fat_type, vol.label))

        def tree(path, indent=0):
            for e in sorted(vol.listdir(path), key=lambda e: (not e["dir"], e["name"].lower())):
                print("  " * indent + ("[DIR] " if e["dir"] else "      ") + e["name"] +
                      ("" if e["dir"] else " (%d bytes)" % e["size"]))
                if e["dir"]:
                    tree((path + "/" if path else "") + e["name"], indent + 1)

        tree("")
        vol.close()
    except OSError as e:
        print("Could not read a filesystem on this drive:", e)
        drive.close()
