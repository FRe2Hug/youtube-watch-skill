#!/bin/sh
# Runs ytwatch. On first use, downloads the self-contained binary for this OS
# into ~/.claude/bin (nothing else is installed, PATH is not touched).
set -e
REPO=FRe2Hug/youtube-watch-skill
DIR="$HOME/.claude/bin"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ASSET=ytwatch-windows-x64.exe; BIN="$DIR/ytwatch.exe" ;;
  Darwin)
    [ "$(uname -m)" = arm64 ] || { echo "ytwatch: only Apple Silicon (arm64) Macs are supported" >&2; exit 1; }
    ASSET=ytwatch-macos-arm64; BIN="$DIR/ytwatch" ;;
  Linux)
    [ "$(uname -m)" = x86_64 ] || { echo "ytwatch: only x86_64 Linux is supported" >&2; exit 1; }
    ASSET=ytwatch-linux-x64; BIN="$DIR/ytwatch" ;;
  *) echo "ytwatch: unsupported OS $(uname -s)" >&2; exit 1 ;;
esac
if [ ! -x "$BIN" ]; then
  mkdir -p "$DIR"
  echo "ytwatch: first run, downloading $ASSET (~100 MB) to $DIR ..." >&2
  curl -fL --retry 3 --progress-bar -o "$BIN.part" "https://github.com/$REPO/releases/latest/download/$ASSET"
  chmod +x "$BIN.part"
  mv "$BIN.part" "$BIN"
fi
exec "$BIN" "$@"
