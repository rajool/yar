#!/usr/bin/env bash
# open-profile.sh — open a chrome-devtools login profile in a PLAIN (non-automated)
# Chrome window so the user can sign into accounts themselves. Some providers
# (notably Google) may refuse sign-in inside a WebDriver-controlled browser; a plain
# window avoids that. Sessions persist in the profile dir and are reused by the
# chrome-personal / chrome-work MCP servers afterwards.
#
# Usage:
#   open-profile.sh <personal|work|/abs/path> [--debug-port N]
#
#   --debug-port N   also enable Chrome's remote-debugging port, for attach mode
#                    (MCP flag --browser-url=http://127.0.0.1:N - see SKILL.md, 7)
#
# Env: CHROME_PROFILES_DIR (default ~/.claude/chrome-profiles)
set -euo pipefail

BASE="${CHROME_PROFILES_DIR:-$HOME/.claude/chrome-profiles}"
NAME="${1:-}"
if [ -z "$NAME" ]; then
  echo "usage: open-profile.sh <personal|work|/abs/path> [--debug-port N]" >&2
  exit 2
fi
shift

PORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --debug-port)   PORT="${2:-9222}"; shift 2 ;;
    --debug-port=*) PORT="${1#*=}"; shift ;;
    *) echo "x unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$NAME" in
  /*) DIR="$NAME" ;;
  *)  DIR="$BASE/$NAME" ;;
esac
mkdir -p "$DIR"

# Locate Chrome (macOS bundles first, then PATH).
CHROME=""
for c in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
  [ -x "$c" ] && CHROME="$c" && break
done
[ -n "$CHROME" ] || CHROME="$(command -v google-chrome || command -v chromium || command -v chrome || true)"
[ -n "$CHROME" ] || { echo "x Chrome not found. Install Google Chrome." >&2; exit 1; }

# A profile dir can be held by only one Chrome at a time - don't double-open.
if pgrep -f -- "--user-data-dir=$DIR" >/dev/null 2>&1; then
  echo "= a Chrome is already running on this profile ($DIR)."
  echo "  Use that window, or close it first to reopen."
  exit 0
fi

EXTRA=()
[ -n "$PORT" ] && EXTRA=("--remote-debugging-port=$PORT")

"$CHROME" "--user-data-dir=$DIR" --no-first-run --no-default-browser-check \
  ${EXTRA[@]+"${EXTRA[@]}"} >/dev/null 2>&1 &

echo "+ opened profile '$NAME' ($DIR) in a plain Chrome window (pid $!)."
echo "  1. Sign into the account(s) this profile should hold."
echo "  2. CLOSE the window when done - automation cannot start while it is open."
if [ -n "$PORT" ]; then
  echo "  attach mode: point the MCP server at --browser-url=http://127.0.0.1:$PORT"
fi
