#!/bin/sh
set -eu
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo 'Usage: sh installer/install.sh PROJECT [auto|codex|claude|generic]' >&2
    exit 2
fi
project=$(cd "$1" && pwd -P)
root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
harness=auto
if [ "$#" -eq 2 ]; then harness=$2; fi
case "$harness" in auto|codex|claude|generic) ;; *) echo 'Unsupported harness' >&2; exit 2;; esac
if [ "$project" = / ] || [ "$project" = "$HOME" ]; then echo 'Select a project directory' >&2; exit 2; fi
os=$(uname -s)
arch=$(uname -m)
case "$os:$arch" in
    Darwin:arm64|Darwin:aarch64) key=macos-arm64-cp312 ;;
    Darwin:x86_64) key=macos-x86_64-cp312 ;;
    Linux:x86_64) key=linux-x86_64-cp312 ;;
    Linux:aarch64|Linux:arm64) key=linux-aarch64-cp312 ;;
    *) echo 'No matching bundled platform' >&2; exit 2 ;;
esac
case "$os" in Darwin)
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then key=macos-arm64-cp312; fi
    major=$(sw_vers -productVersion | cut -d. -f1)
    if [ "$major" -lt 13 ]; then echo 'Complete dependency stack requires macOS 13+' >&2; exit 2; fi ;;
esac
archive="$root/engines/$key.tar.gz"
expected=$(cat "$root/engines/$key.archive.sha256")
hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}';
    else shasum -a 256 "$1" | awk '{print $1}'; fi
}
descriptor="$project/.lotraAI-build/toolchain/core-runtime-$key.json"
if [ -f "$descriptor" ] && [ -f "$root/Update-manifest.json" ]; then
    engine_fields=$(tr '\r\n' '  ' < "$descriptor" | sed -n 's/.*"engine"[[:space:]]*:[[:space:]]*{\([^}]*\)}.*/\1/p')
    engine=$(printf '%s\n' "$engine_fields" | sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    engine_hash=$(printf '%s\n' "$engine_fields" | sed -n 's/.*"sha256"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    if [ -n "$engine" ] && [ -n "$engine_hash" ]; then
    case "$engine" in .lotraAI-build/*) ;; *) echo 'Invalid prepared engine path' >&2; exit 2;; esac
    case "$engine" in *..*|*\\*) echo 'Unsafe prepared engine path' >&2; exit 2;; esac
    if [ -f "$project/$engine" ] && [ "$(hash_file "$project/$engine")" = "$engine_hash" ]; then
        exec "$project/$engine" -I -X utf8 -B "$root/installer/online.py" --project "$project" --harness "$harness" --bundle-root "$root"
    fi
    fi
fi
if [ ! -f "$archive" ] && [ -f "$root/Update-manifest.json" ]; then
    mkdir -p "$project/.lotraAI-build/downloads/bootstrap"
    archive="$project/.lotraAI-build/downloads/bootstrap/$expected.tar.gz"
    if [ ! -f "$archive" ]; then
        curl --fail --location --retry 2 --connect-timeout 30 --max-time 1800 --continue-at - --output "$archive.part" "https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.33.0/$key.tar.gz"
        if [ "$(hash_file "$archive.part")" != "$expected" ]; then echo 'Bootstrap hash mismatch; partial retained' >&2; exit 2; fi
        mv -- "$archive.part" "$archive"
    fi
fi
if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$archive" | awk '{print $1}')
else
    actual=$(shasum -a 256 "$archive" | awk '{print $1}')
fi
if [ "$actual" != "$expected" ]; then echo 'Interpreter archive checksum mismatch' >&2; exit 2; fi
bootstrap="$project/.lotraAI-build/bundle-bootstrap"
if [ -L "$project/.lotraAI-build" ] || [ -L "$bootstrap" ]; then
    echo 'Preserve a redirected project/bootstrap path' >&2
    exit 2
fi
mkdir -p "$bootstrap"
scratch=$(mktemp -d "$bootstrap/owned-XXXXXXXX")
token=$(basename "$scratch")
printf '%s' "$token" > "$scratch/Owner.txt"
cleanup() {
    case "$scratch" in "$bootstrap"/owned-*) ;; *) return ;; esac
    if [ -d "$scratch" ] && [ ! -L "$scratch" ] && [ "$(cat "$scratch/Owner.txt")" = "$token" ]; then rm -rf -- "$scratch"; fi
}
trap cleanup EXIT HUP INT TERM
# The hash-bound source archive was audited at publication for exact internal
# links and python/ names. It is expanded only into this new owned directory.
tar -xzf "$archive" -C "$scratch"
python="$scratch/python/bin/python3.12"
expected=$(cat "$root/engines/$key.executable.sha256")
if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$python" | awk '{print $1}')
else
    actual=$(shasum -a 256 "$python" | awk '{print $1}')
fi
if [ "$actual" != "$expected" ]; then echo 'Bootstrap executable checksum mismatch' >&2; exit 2; fi
entry=install.py
if [ -f "$root/Differential-manifest.json" ]; then
    exec "$python" -I -X utf8 -B "$root/installer/differential.py" --project "$project" --harness "$harness" --catalog "$root/Differential-manifest.json"
fi
if [ -f "$root/Update-manifest.json" ]; then entry=online.py; fi
"$python" -I -X utf8 -B "$root/installer/$entry" --project "$project" --harness "$harness" --bundle-root "$root"
