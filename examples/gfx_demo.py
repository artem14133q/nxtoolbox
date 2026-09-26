# Graphics demo: bouncing balls, a square moved with the left stick, FPS counter.
# B quits (or + and - together).
import switch
import gfx

W, H = gfx.WIDTH, gfx.HEIGHT
TOP = 48                                    # height of the title bar
BG = gfx.rgb(20, 24, 40)
BAR = gfx.rgb(40, 50, 80)

# x, y, dx, dy, radius, color
balls = [
    [200, 150, 7, 5, 30, gfx.RED],
    [600, 400, -6, 4, 45, gfx.GREEN],
    [1000, 200, 5, -7, 25, gfx.CYAN],
]
px, py = W // 2, H // 2
fps, frames, t0 = 0, 0, switch.ticks_ms()

while switch.running():
    if switch.buttons_down() & switch.B:
        break

    # Player square: stick up is +, but screen y grows downwards
    sx, sy = switch.stick(0)
    px = max(0, min(W - 60, px + int(sx * 12)))
    py = max(TOP, min(H - 60, py - int(sy * 12)))

    for b in balls:
        b[0] += b[2]
        b[1] += b[3]
        if b[0] < b[4] or b[0] > W - b[4]:
            b[2] = -b[2]
        if b[1] < TOP + b[4] or b[1] > H - b[4]:
            b[3] = -b[3]

    gfx.clear(BG)
    gfx.fill_rect(0, 0, W, TOP, BAR)
    gfx.text(16, 8, "NXToolBox gfx demo", gfx.WHITE, 2)
    label = "FPS %d" % fps
    gfx.text(W - 16 - gfx.text_width(label, 2), 8, label, gfx.YELLOW, 2)
    for x, y, _, _, r, color in balls:
        gfx.fill_circle(x, y, r, color)
    gfx.fill_rect(px, py, 60, 60, gfx.ORANGE)
    gfx.rect(px, py, 60, 60, gfx.WHITE)
    gfx.text(16, H - 24, "Left stick: move    B: quit", gfx.GRAY)
    gfx.present()

    frames += 1
    now = switch.ticks_ms()
    if now - t0 >= 1000:
        fps = frames * 1000 // (now - t0)
        frames, t0 = 0, now
