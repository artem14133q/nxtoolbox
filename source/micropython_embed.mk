# Generates the MicroPython core. Invoked by gen.sh (which passes MICROPYTHON_TOP).
MICROPYTHON_TOP ?= ../../micropython
PACKAGE_DIR = ../micropython_embed

# The embed port does not scan the filesystem (VFS) sources for qstrs and
# root pointers on its own, so list them explicitly.
SRC_QSTR += $(MICROPYTHON_TOP)/extmod/vfs.c $(MICROPYTHON_TOP)/extmod/vfs_posix.c \
            $(MICROPYTHON_TOP)/extmod/vfs_posix_file.c $(MICROPYTHON_TOP)/extmod/vfs_reader.c \
            $(MICROPYTHON_TOP)/extmod/modos.c

include $(MICROPYTHON_TOP)/ports/embed/embed.mk
