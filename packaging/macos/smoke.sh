#!/bin/bash
# Checks on this machine that what build.py made starts: the app from the
# disk image, the way a double-click runs it. Run after build.py, on an
# Apple Silicon Mac. It does not see what a downloaded copy sees: files
# built here carry no "from the internet" mark, so Gatekeeper stays out of it.
set -euo pipefail
image=$(ls dist/troedel-*-macos-arm64.dmg | head -1)
work=$(mktemp -d)
hdiutil attach "$image" -nobrowse -readonly -mountpoint "$work/volume" >/dev/null
window=
trap '[ -n "$window" ] && kill $window 2>/dev/null; hdiutil detach "$work/volume" -force >/dev/null || true' EXIT
app="$work/volume/Troedel.app"
python="$app/Contents/Resources/python/bin/python3"

[ -L "$work/volume/Applications" ] || { echo "the disk image has no link to Applications"; exit 1; }
[ -x "$app/Contents/MacOS/Troedel" ] || { echo "the app's start file is not a program"; exit 1; }
codesign --verify "$app"
plutil -lint "$app/Contents/Info.plist" >/dev/null

"$python" -I -B -c "import tkinter, segno, rembg, onnxruntime, pillow_heif, argon2; tkinter.Tcl().eval('package require Tk'); print('imports ok')"

# Straight from the read-only image: the app must not need to write into itself.
export TROEDEL_DATA_DIR="$work/data" TROEDEL_PORT=8765
"$app/Contents/MacOS/Troedel" &
window=$!
for _ in $(seq 60); do
    curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1 && up=1 && break
    sleep 1
done
[ "${up:-}" = 1 ] || { cat "$work/data/troedel.log" 2>/dev/null; echo "Troedel did not answer on /health within a minute"; exit 1; }
curl -fsS http://127.0.0.1:8765/setup | grep -q troedel.css || { echo "the setup page came without its stylesheet"; exit 1; }
