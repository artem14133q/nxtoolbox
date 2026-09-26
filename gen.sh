#!/bin/bash
# Generates micropython_embed/ with the switch and usbhost modules.
# Re-run every time you change modules/ or source/mpconfigport.h.
set -e

# === PATH TO THE MICROPYTHON REPOSITORY (default: ../micropython, or set MICROPYTHON_DIR) ===
MPY="${MICROPYTHON_DIR:-$(dirname "$0")/../micropython}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
MPY="$(cd "$MPY" 2>/dev/null && pwd || echo "$MPY")"

if [ ! -f "$MPY/ports/embed/embed.mk" ]; then
    echo "ERROR: $MPY/ports/embed/embed.mk not found"
    echo "Check the MicroPython path (MICROPYTHON_DIR) or update the repository (git pull)."
    exit 1
fi

echo "== Removing old files =="
rm -rf "$ROOT/micropython_embed" "$ROOT/source/build-embed"

echo "== Generating the MicroPython core =="
cd "$ROOT/source"
make -f micropython_embed.mk MICROPYTHON_TOP="$MPY" USER_C_MODULES="$ROOT/modules"

echo "== Redirecting Python output to app_output() =="
cat > "$ROOT/micropython_embed/port/mphalport.c" <<'CEOF'
#include "py/mphal.h"

void app_output(const char *str, size_t len);  // defined in source/main.c

void mp_hal_stdout_tx_strn_cooked(const char *str, size_t len) {
    app_output(str, len);
}
CEOF

echo "== Adding filesystem (VFS) sources =="
mkdir -p "$ROOT/micropython_embed/extmod"
for f in vfs.c vfs_posix.c vfs_posix_file.c vfs_reader.c modos.c modjson.c; do
    cp "$MPY/extmod/$f" "$ROOT/micropython_embed/extmod/"
done
cp "$MPY"/extmod/*.h "$ROOT/micropython_embed/extmod/"

echo "== Checking =="
if grep -q "buttons_down" "$ROOT/micropython_embed/genhdr/qstrdefs.generated.h"; then
    echo "OK: the switch module is in place. Now run: make clean && make"
else
    echo "ERROR: the switch module did not make it into the build. Check the output above."
    exit 1
fi
