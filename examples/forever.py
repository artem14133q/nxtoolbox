# Stop test: an endless loop without switch.running()
# Stop it with Ctrl+C on the computer or + and - together on the console
n = 0
while True:
    n += 1
    if n % 1000000 == 0:
        print("still running...", n)
