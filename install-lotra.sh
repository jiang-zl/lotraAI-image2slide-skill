#!/bin/sh
set -eu
[ "$#" -ge 1 ] || { echo 'Pass the project path' >&2; exit 2; }
project=$(cd "$1" && pwd -P)
shift
case "$project" in /|"$HOME") echo 'Choose a project directory' >&2; exit 2;; esac
# Local bundle dispatch uses the common bundled coordinator.
if [ "${1:-}" = --bundle-root ]; then
 [ "$#" -eq 2 ] || { echo 'Usage: PROJECT --bundle-root EXTRACTED_ROOT' >&2; exit 2; }
 local_root=$(CDPATH= cd -- "$2" && pwd -P)
 [ -f "$local_root/installer/install.sh" ] || { echo 'Bundle installer missing' >&2; exit 2; }
 exec sh "$local_root/installer/install.sh" "$project" codex
fi
hash_file() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi; }
case "$(uname -s):$(uname -m)" in
 Darwin:arm64|Darwin:aarch64) key=macos-arm64-cp312 ;;
 Darwin:x86_64) key=macos-x86_64-cp312 ;;
 Linux:x86_64) key=linux-x86_64-cp312 ;;
 Linux:aarch64|Linux:arm64) key=linux-aarch64-cp312 ;;
 *) echo 'Unsupported platform' >&2; exit 2;;
esac
if [ "$(uname -s)" = Darwin ]; then
 [ "$(sw_vers -productVersion | cut -d. -f1)" -ge 13 ] || { echo 'Requires macOS 13+' >&2; exit 2; }
 if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then key=macos-arm64-cp312; fi
fi
case "$key" in
 linux-aarch64-cp312) engine_url="https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.34.0/linux-aarch64-cp312.tar.gz"; engine_api_url="https://api.github.com/repos/jiang-zl/lotraAI-image2slide-skill-runtime/releases/assets/647394840"; engine_hash="2e1ba0e7f22e01c534caebf7f09e7820322bc0d055271d3434af671e8400f96f"; exe_hash="dab6ef4f6c7847ec9f123756e3472cb0212b8d2043af623c6c3a4e806bde6e90"; executable="python/bin/python3.12" ;;
 linux-x86_64-cp312) engine_url="https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.34.0/linux-x86_64-cp312.tar.gz"; engine_api_url="https://api.github.com/repos/jiang-zl/lotraAI-image2slide-skill-runtime/releases/assets/647771853"; engine_hash="ffa8f85f1b56e88b687f08d743d817015524b86a9365fd921243132b80f1a36d"; exe_hash="708fefcd7df61b1327cb7b9740fafd42cb2f6cd1d387378892d4a28b7479fb78"; executable="python/bin/python3.12" ;;
 macos-arm64-cp312) engine_url="https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.34.0/macos-arm64-cp312.tar.gz"; engine_api_url="https://api.github.com/repos/jiang-zl/lotraAI-image2slide-skill-runtime/releases/assets/647393262"; engine_hash="233f8e15255b3e1d1fd47ea5dd5230dfed803f371138e896e54d98c60ae19f6f"; exe_hash="83deb939c9034c3e85a377eeb04e7d9992f8881652a22289cd0eeeb83b98a565"; executable="python/bin/python3.12" ;;
 macos-x86_64-cp312) engine_url="https://github.com/jiang-zl/lotraAI-image2slide-skill-runtime/releases/download/v1.34.0/macos-x86_64-cp312.tar.gz"; engine_api_url="https://api.github.com/repos/jiang-zl/lotraAI-image2slide-skill-runtime/releases/assets/647392282"; engine_hash="fb3187d95334813b88940db0f1ca57b84cedfd552739c3a5771c3ea0e49988c9"; exe_hash="63a792c5f90bedbb2309549a5d85726ff21ee65c0af9ae01627140e9b2b83aaa"; executable="python/bin/python3.12" ;;
esac
[ ! -L "$project/.lotraAI-build" ] || { echo 'Preserve redirected storage' >&2; exit 2; }
state="$project/.lotraAI-build/install-entry"
mkdir -p "$state"
get() {
 url=$1; file=$2; expected=$3; api=${4:-}
 if [ -f "$file" ]; then [ "$(hash_file "$file")" = "$expected" ] || { echo 'Preserve changed cached file' >&2; exit 2; }; return; fi
 mkdir -p "$(dirname "$file")"
 if ! curl --silent --show-error --fail --location --retry 2 --connect-timeout 30 --max-time 1800 --continue-at - --output "$file.part" "$url" >>"$state/Download.log" 2>&1; then
  [ -n "$api" ] || { echo 'Download failed; verified cache and partial retained' >&2; exit 2; }
  curl --silent --show-error --fail --location --retry 2 --connect-timeout 30 --max-time 1800 --continue-at - -H 'Accept: application/octet-stream' --output "$file.part" "$api" >>"$state/Download.log" 2>&1
 fi
 [ "$(hash_file "$file.part")" = "$expected" ] || { echo 'Download hash mismatch; partial retained' >&2; exit 2; }
 mv -- "$file.part" "$file"
}
python=''
descriptor="$project/.lotraAI-build/toolchain/core-runtime-$key.json"
if [ -f "$descriptor" ]; then
    engine_fields=$(tr '\r\n' '  ' < "$descriptor" | sed -n 's/.*"engine"[[:space:]]*:[[:space:]]*{\([^}]*\)}.*/\1/p')
    engine=$(printf '%s\n' "$engine_fields" | sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    expected=$(printf '%s\n' "$engine_fields" | sed -n 's/.*"sha256"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
 if [ -n "$engine" ] && [ -n "$expected" ]; then
 case "$engine" in .lotraAI-build/*) ;; *) echo 'Invalid prepared engine path' >&2; exit 2;; esac
 case "$engine" in *..*|*\\*) echo 'Unsafe engine path' >&2; exit 2;; esac
 if [ -f "$project/$engine" ] && [ "$(hash_file "$project/$engine")" = "$expected" ]; then python="$project/$engine"; fi
 fi
fi
if [ -z "$python" ]; then
 archive="$state/$engine_hash.tar.gz"
 get "$engine_url" "$archive" "$engine_hash" "$engine_api_url"
 base="$project/.lotraAI-build/bootstrap/$engine_hash"
 [ ! -L "$base" ] || { echo 'Preserve redirected bootstrap' >&2; exit 2; }
 mkdir -p "$base"
 if [ ! -f "$base/$executable" ]; then tar -xzf "$archive" -C "$base"; fi
 python="$base/$executable"
 [ "$(hash_file "$python")" = "$exe_hash" ] || { echo 'Python executable differs' >&2; exit 2; }
fi
entry="$project/.lotraAI-build/bootstrap/ae1a062cab42fe36e5c851fc1e3d70c64f5817bd8837378350a7b9ca56022694/install_lotra.py"
get 'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill-runtime/1.37.2/tools/install_lotra.py' "$entry" 'ae1a062cab42fe36e5c851fc1e3d70c64f5817bd8837378350a7b9ca56022694'
exec "$python" -I -X utf8 -B "$entry" --project "$project" "$@"
