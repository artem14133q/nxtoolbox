# Lists the USB interfaces available to scripts.
# Connect a device (docked: to a dock USB port; handheld:
# through a USB-C OTG adapter) and run the script.
import usbhost

TYPES = {0: "control", 1: "iso", 2: "bulk", 3: "interrupt"}
CLASSES = {
    0x01: "audio", 0x02: "CDC comm (serial)", 0x03: "HID", 0x07: "printer",
    0x08: "mass storage", 0x0A: "CDC data (serial)", 0x0E: "video", 0xFF: "vendor-specific",
}

devs = usbhost.devices()
if not devs:
    print("No available USB interfaces.")
    print("Note: devices the system uses itself (official controllers etc.) are not listed.")

for d in devs:
    print("VID %04x PID %04x  bus %d dev %d  iface %d  class %02x/%02x/%02x %s" % (
        d["vid"], d["pid"], d["bus"], d["dev"], d["iface"],
        d["cls"], d["subcls"], d["proto"], CLASSES.get(d["cls"], "")))
    for addr, typ, size in d["eps"]:
        print("    ep 0x%02x  %-3s  %-9s  %d bytes" % (
            addr, "IN" if addr & 0x80 else "OUT", TYPES.get(typ, "?"), size))
