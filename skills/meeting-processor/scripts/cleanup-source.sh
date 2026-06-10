#!/usr/bin/env bash
# cleanup-source.sh — safely remove a *processed* source recording (audio/video)
# AFTER its transcript + summary have been saved. By default the file is moved to
# the macOS Trash (recoverable); pass --hard (or MEETING_DELETE_HARD=1) to delete
# it permanently. The script refuses to touch anything that isn't a regular media
# file, so it can never remove a transcript, raw.json, or summary by mistake.
#
# Usage:
#   cleanup-source.sh [--hard] <path-to-source-media>
#
# Exit codes: 0 done · 1 refused/failed · 2 bad usage
set -euo pipefail

HARD="${MEETING_DELETE_HARD:-0}"
FILE=""
for arg in "$@"; do
  case "$arg" in
    --hard) HARD=1 ;;
    -*)     echo "cleanup-source: unknown flag: $arg" >&2; exit 2 ;;
    *)      FILE="$arg" ;;
  esac
done

[ -n "$FILE" ] || { echo "usage: cleanup-source.sh [--hard] <path-to-source-media>" >&2; exit 2; }
[ -e "$FILE" ] || { echo "cleanup-source: nothing to delete (not found): $FILE" >&2; exit 0; }
[ -f "$FILE" ] || { echo "cleanup-source: refusing — not a regular file: $FILE" >&2; exit 1; }

# Guard: only ever delete known audio/video source files. Never a transcript,
# JSON, Markdown summary, or any other deliverable.
ext="${FILE##*.}"
ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"
case "$ext" in
  mp4|mov|m4v|mkv|avi|webm|mpg|mpeg|3gp|wmv) : ;;            # video
  m4a|mp3|wav|aac|flac|ogg|oga|opus|wma|aiff|aif|caf) : ;;   # audio
  *) echo "cleanup-source: refusing to delete non-media file (.$ext): $FILE" >&2; exit 1 ;;
esac

# Absolute path (Finder/Trash need it; also clearer in the log line).
ABS="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"

if [ "$HARD" = 1 ]; then
  rm -f "$ABS"
  echo "Permanently deleted: $ABS"
  exit 0
fi

# Recoverable delete → macOS Trash via Finder (gives a proper "Put Back").
if command -v osascript >/dev/null 2>&1 \
   && osascript -e "tell application \"Finder\" to delete (POSIX file \"$ABS\" as alias)" >/dev/null 2>&1; then
  echo "Moved to Trash: $ABS"
  exit 0
fi

# Fallback: best-effort move into ~/.Trash (recoverable, no "Put Back"), unique name.
TRASH="$HOME/.Trash"
if [ -d "$TRASH" ]; then
  base="$(basename "$ABS")"; dest="$TRASH/$base"; n=2
  while [ -e "$dest" ]; do dest="$TRASH/${base%.*}-$n.${base##*.}"; n=$((n+1)); done
  if mv "$ABS" "$dest" 2>/dev/null; then
    echo "Moved to Trash: $dest"
    exit 0
  fi
fi

echo "cleanup-source: could not move to Trash (no Finder / cross-volume?)." >&2
echo "  Re-run with --hard to delete permanently, or remove it manually: $ABS" >&2
exit 1
