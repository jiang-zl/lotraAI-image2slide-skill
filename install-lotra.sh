#!/bin/sh
set -eu
project=$(cd "$1" && pwd -P)
case "$project" in /|"$HOME") echo 'Choose a project directory' >&2; exit 2;; esac
root="$project/.lotraAI-build/releases/1.33.0"
mkdir -p "$root"
if [ ! -f "$root/update.zip" ]; then
 curl --fail --location --retry 2 --connect-timeout 30 --max-time 1800 --continue-at - --output "$root/update.zip.part" 'https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.33.0/lotraAI-image2slide-v1.33.0-update.zip'
 [ "$(sha256sum "$root/update.zip.part" | awk '{print $1}')" = '3718fb5b5b99205577a113a318fddda71b128ef2b8cbd5130b9840ff5035e080' ] || { echo 'Update hash mismatch; partial retained' >&2; exit 2; }
 mv -- "$root/update.zip.part" "$root/update.zip"
fi
[ "$(sha256sum "$root/update.zip" | awk '{print $1}')" = '3718fb5b5b99205577a113a318fddda71b128ef2b8cbd5130b9840ff5035e080' ] || exit 2
# Publisher-controlled hash-bound ZIP contains only relative regular files.
unzip -oq "$root/update.zip" -d "$root"
exec sh "$root/installer/install.sh" "$project"
