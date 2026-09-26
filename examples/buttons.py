import switch

print("Battery:", switch.battery(), "%")
print("A - count, B - show held buttons, MINUS - quit")

n = 0
while switch.running():
    down = switch.buttons_down()

    if down & switch.A:
        n += 1
        print("A pressed", n, "times")

    if down & switch.B:
        print("held mask:", hex(switch.buttons()))

    if down & switch.MINUS:
        print("bye")
        break

    switch.sleep_ms(16)  # ~60 times per second
