import os

print("cwd:", os.getcwd())            # /switch/NXToolBox/scripts
print("SD root:", os.listdir("/"))

# Write and read a file next to the scripts
with open("hello.txt", "w") as f:
    f.write("Hello from Switch!\n")

with open("hello.txt") as f:
    print("read back:", f.read().strip())

print("size:", os.stat("hello.txt")[6], "bytes")

# Modules for import live in /switch/NXToolBox/lib
with open("/switch/NXToolBox/lib/greet.py", "w") as f:
    f.write("def hello(name):\n    return 'Hello, ' + name + '!'\n")

import greet
print(greet.hello("Switch"))

print("scripts dir:", os.listdir())
print("lib dir:", os.listdir("/switch/NXToolBox/lib"))
