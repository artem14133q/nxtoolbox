# Finger painting on the touch screen (handheld mode only).
# Y: next color, X: clear, B: quit.
import switch
import gfx

COLORS = [gfx.WHITE, gfx.RED, gfx.ORANGE, gfx.YELLOW, gfx.GREEN, gfx.CYAN, gfx.BLUE, gfx.MAGENTA]
BAR_H = 40
RADIUS = 6
color = 0


def toolbar():
    gfx.fill_rect(0, 0, gfx.WIDTH, BAR_H, gfx.rgb(40, 50, 80))
    gfx.text(12, 4, "Touch to draw   Y: color   X: clear   B: quit", gfx.WHITE, 2)
    gfx.fill_rect(gfx.WIDTH - 60, 4, 48, 32, COLORS[color])
    gfx.rect(gfx.WIDTH - 60, 4, 48, 32, gfx.WHITE)


gfx.clear()
toolbar()
last = {}   # touch index -> previous point, to draw continuous strokes

while switch.running():
    down = switch.buttons_down()
    if down & switch.B:
        break
    if down & switch.Y:
        color = (color + 1) % len(COLORS)
        toolbar()
    if down & switch.X:
        gfx.clear()
        toolbar()

    current = {}
    for i, (x, y) in enumerate(switch.touches()):
        if y < BAR_H + RADIUS:
            continue
        lx, ly = last.get(i, (x, y))
        steps = max(abs(x - lx), abs(y - ly)) // 3 + 1
        for s in range(steps + 1):
            gfx.fill_circle(lx + (x - lx) * s // steps, ly + (y - ly) * s // steps, RADIUS, COLORS[color])
        current[i] = (x, y)
    last = current

    gfx.present()
