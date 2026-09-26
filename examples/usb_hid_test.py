# USB HID test: shows the device description and all incoming reports in hex.
# Connect a HID device (gamepad, button panel, custom device).
# MINUS on the Switch quits.
import switch
import usbhid


def hexs(data):
    return " ".join("%02x" % b for b in data)


def main():
    found = usbhid.devices()
    print("HID interfaces:", len(found))
    for d in found:
        print("  VID %04x PID %04x iface %d proto %d" % (d["vid"], d["pid"], d["iface"], d["proto"]))
    if not found:
        print("No available HID devices. The system may be using keyboards/mice/official")
        print("controllers itself; custom HID devices should appear here.")
        return

    with usbhid.HID() as dev:
        print("Opened VID %04x PID %04x, report size %d" % (dev.vid, dev.pid, dev.report_size))
        try:
            desc = dev.report_descriptor()
            print("Report descriptor (%d bytes):" % len(desc))
            for i in range(0, len(desc), 16):
                print("  " + hexs(desc[i:i + 16]))
        except OSError as e:
            print("Report descriptor not available:", e)

        print("Use the device; changed reports are printed. MINUS: quit")
        last = None
        while switch.running():
            report = dev.read(timeout=50)
            if report is not None and report != last:
                print(hexs(report))
                last = report
            if switch.buttons_down() & switch.MINUS:
                break
    print("Closed.")


main()
