#!/bin/sh
# Build the optional framebuffer copier for the Pi 1 ARMv6 hard-float ABI.
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
launcher_repo=${PI_GAMES_LAUNCHER_REPO:-$repo/../pi-games-launcher}
sysroot=${PI286_SYSROOT:-$launcher_repo/.cache/pi286-sysroot}
cross=${CROSS_COMPILE:-arm-linux-gnueabihf-}
cc=${cross}gcc
suffix=${PYTHON_EXTENSION_SUFFIX:-.cpython-313-arm-linux-gnueabihf.so}
output=${FBCOPY_OUTPUT:-$repo/src/common/_fbcopy$suffix}
flags='-O3 -fPIC -shared -marm -march=armv6zk -mtune=arm1176jzf-s -mfpu=vfp -mfloat-abi=hard'

command -v "$cc" >/dev/null 2>&1 || { echo "Missing compiler: $cc" >&2; exit 1; }
[ -f "$sysroot/usr/include/python3.13/Python.h" ] || {
    echo "Missing Pi Python headers in $sysroot; sync the launcher sysroot first." >&2
    exit 1
}

mkdir -p "$(dirname -- "$output")"
"$cc" --sysroot="$sysroot" $flags -nostartfiles -nodefaultlibs -I"$sysroot/usr/include/python3.13" \
    "$repo/src/common/_fbcopy.c" -o "$output"
file "$output"
