# USB-Serial test. Flash arduino/serial_echo/serial_echo.ino to the board.
# Buttons: A - LED on, B - LED off, X - send "hello", MINUS - quit.
import switch
from usbserial import Serial, ports


def main():
    found = ports()
    print("USB serial devices:", len(found))
    for p in found:
        print("  VID %04x PID %04x" % (p["vid"], p["pid"]))
    if not found:
        print("Connect a board with native USB (ESP32-C3, STM32 with USB CDC, Arduino Uno R3...).")
        return

    with Serial(baudrate=115200) as port:
        print("Opened VID %04x PID %04x" % (port.vid, port.pid))
        print("A: LED on   B: LED off   X: send hello   MINUS: quit")
        commands = {switch.A: "on", switch.B: "off", switch.X: "hello"}
        while switch.running():
            line = port.readline(timeout=50)
            if line is not None:
                print("<", line)
            down = switch.buttons_down()
            for button, cmd in commands.items():
                if down & button:
                    port.write(cmd + "\n")
                    print(">", cmd)
            if down & switch.MINUS:
                break
    print("Closed.")


main()
