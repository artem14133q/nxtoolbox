# ui demo: widgets, layouts and dialogs. Needs lib/ui.py on the Switch:
#   python3 send.py upload lib/ui.py --to lib
#
# D-pad moves the focus, A activates, B goes back; touch works too.
import switch
import ui

scr = ui.Screen("NXToolBox UI demo", hint="D-pad: move   A: select   B: exit   Left/Right: change slider")


def on_volume(value):
    bar.set(value / 100)
    status.set_text("Volume set to %d" % value)
    if rumble.checked:
        switch.rumble(0.3, 30)


def on_rumble(checked):
    status.set_text("Rumble feedback " + ("on" if checked else "off"))


def on_board(index, name):
    ui.message("You picked:\n%s" % name, title="Board")
    status.set_text("Selected: " + name)


def on_reset():
    if ui.confirm("Reset the volume to 30?"):
        volume.set(30)
        status.set_text("Volume reset")


def on_mode():
    modes = ["Normal", "Quiet", "Loud", "Custom"]
    i = ui.choose("Choose a mode", modes)
    status.set_text("Mode: " + modes[i] if i is not None else "Mode not changed")


def on_exit():
    if ui.confirm("Close the demo?", yes="Close", no="Stay"):
        scr.close()


# Settings form: labels in column 0, controls in column 1 (which takes the free width)
form = ui.Grid(spacing=24, row_spacing=20)
form.add(ui.Label("Volume"), 0, 0)
volume = form.add(ui.Slider(value=30, maximum=100, step=5, on_change=on_volume), 0, 1)
form.add(ui.Label("Level"), 1, 0)
bar = form.add(ui.ProgressBar(value=0.3), 1, 1)
rumble = form.add(ui.Checkbox("Rumble feedback", checked=True, on_change=on_rumble), 2, 0, colspan=2)
form.add(ui.Checkbox("Dark mode", checked=True), 3, 0, colspan=2)
form.set_column_stretch(1, 1)

# A list with its caption
boards = ui.VBox(spacing=12)
boards.add(ui.Label("Boards"))
boards.add(ui.ListBox(["Arduino Uno", "Pro Mini", "STM32F4", "STM32F0", "ESP32-C3",
                       "Orange Pi Zero 2", "Raspberry Pi Pico", "Leonardo", "ESP32-S3"],
                      rows=6, w=440, on_select=on_board,
                      on_change=lambda i, name: status.set_text("Highlighted: " + name)))

top = ui.HBox(spacing=60)
top.add(form, stretch=1)
top.add(boards)

buttons = ui.HBox(spacing=24)
buttons.add(ui.Button("Reset", on_click=on_reset))
buttons.add(ui.Button("Mode...", on_click=on_mode))
buttons.add(ui.Button("Exit", on_click=on_exit))
buttons.add_stretch()

footer = ui.HBox()
status = footer.add(ui.Label("Ready", color=ui.MUTED))
footer.add_stretch()
battery = footer.add(ui.Label("", color=ui.MUTED, w=ui.CHAR_W * 12, align="right"))

root = ui.VBox(spacing=32)
root.add(top, stretch=1)
root.add(buttons)
root.add(footer)
scr.set_layout(root)

# update() runs every frame: refresh the battery label once per second
_last = [0]


def update():
    now = switch.ticks_ms()
    if now - _last[0] >= 1000:
        _last[0] = now
        try:
            battery.set_text("Battery %d%%" % switch.battery())
        except OSError:
            pass


scr.update = update
scr.on_back = on_exit      # B asks before closing
scr.run()
print("UI demo finished")