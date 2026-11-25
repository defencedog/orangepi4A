#!/usr/bin/env bash
# Build the patched Mesa 26.0.8 Teflon delegate (libteflon.so) for the
# Allwinner T527 VIP9000 NPU (Orange Pi 4A).
#
# Usage:
#   ./build.sh /path/to/mesa-26.0.8 --native
#   ./build.sh /path/to/mesa-26.0.8 --cross /path/to/cross_aarch64.txt
#
# The source directory must be a clean Mesa 26.0.8 tree
# (mesa_26.0.8.orig.tar.xz extracted). The script applies
# ../patches/mesa-26.0.8-vip9000-teflon.patch, configures Meson, and builds
# the Teflon target.
#
# Cross-compile example (x86_64 host -> aarch64 Orange Pi 4A):
#   tar -xf mesa_26.0.8.orig.tar.xz
#   ./build.sh ./mesa-26.0.8 --cross ./cross_aarch64.txt
#
# Native example (on the Orange Pi 4A):
#   tar -xf mesa_26.0.8.orig.tar.xz
#   ./build.sh ./mesa-26.0.8 --native

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
PATCH="$BUNDLE/patches/mesa-26.0.8-vip9000-teflon.patch"

if [ $# -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi

MESA_SRC="$1"
shift
MODE="native"
CROSS_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --native) MODE="native"; shift ;;
        --cross)
            [ $# -ge 2 ] || { echo "--cross needs a cross file" >&2; exit 2; }
            CROSS_FILE="$2"; MODE="cross"; shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ ! -f "$MESA_SRC/meson.build" ]; then
    echo "error: '$MESA_SRC' does not look like a Mesa source tree" >&2
    exit 1
fi
if [ ! -f "$PATCH" ]; then
    echo "error: patch not found: $PATCH" >&2
    exit 1
fi

cd "$MESA_SRC"

echo "[*] applying $PATCH"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git apply --check "$PATCH" >/dev/null 2>&1; then
        git apply "$PATCH"
    else
        echo "[!] patch does not apply cleanly (already applied?); continuing"
    fi
else
    if patch --dry-run -p1 <"$PATCH" >/dev/null 2>&1; then
        patch -p1 <"$PATCH"
    else
        echo "[!] patch does not apply cleanly (already applied?); continuing"
    fi
fi

CROSS_ARGS=()
if [ "$MODE" = "cross" ]; then
    [ -n "$CROSS_FILE" ] || { echo "error: --cross needs a cross file" >&2; exit 2; }
    CROSS_ARGS+=("--cross-file=$CROSS_FILE")
    echo "[*] cross-compiling with $CROSS_FILE"
else
    echo "[*] native build"
fi

if [ -d build ]; then
    echo "[*] meson setup build --reconfigure"
    SETUP_ARGS=(setup build --reconfigure)
else
    echo "[*] meson setup build"
    SETUP_ARGS=(setup build)
fi

meson "${SETUP_ARGS[@]}" \
    -Dbuildtype=release \
    -Dgallium-drivers=etnaviv \
    -Dteflon=true \
    -Dvulkan-drivers= \
    -Dplatforms= \
    -Dglx=disabled \
    -Dgbm=disabled \
    -Degl=disabled \
    -Dgles1=disabled \
    -Dgles2=disabled \
    -Dopengl=false \
    -Dshared-glapi=disabled \
    -Dllvm=disabled \
    "${CROSS_ARGS[@]}"

echo "[*] ninja libteflon.so"
ninja -C build src/gallium/targets/teflon/libteflon.so

OUT="$(pwd)/build/src/gallium/targets/teflon/libteflon.so"
echo "[*] built: $OUT"
ls -la "$OUT"
sha256sum "$OUT"
