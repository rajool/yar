#!/usr/bin/env bash
# launch-chrome-debug.sh — open Google Chrome with the DevTools remote-debugging
# port so the chrome-devtools MCP can attach to a real, logged-in session.
#
# Uses a DEDICATED persistent profile (not your everyday Chrome) so:
#   - it won't conflict with an already-running Chrome, and
#   - logins you do in this window PERSIST for next time.
#
# Usage:
#   launch-chrome-debug.sh [PORT] [PROFILE_DIR]
#     PORT         default 9222
#     PROFILE_DIR  default ~/.cache/yar/chrome-devtools-profile
#
# After it opens: log into whatever account the task needs IN THIS WINDOW,
# then point the MCP at it with  --browser-url=http://127.0.0.1:PORT
set -euo pipefail

PORT="${1:-9222}"
PROFILE_DIR="${2:-$HOME/.cache/yar/chrome-devtools-profile}"

# Locate Chrome (macOS first, then PATH).
CHROME=""
for c in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
  [ -x "$c" ] && CHROME="$c" && break
done
if [ -z "$CHROME" ]; then
  CHROME="$(command -v google-chrome || command -v chromium || command -v chrome || true)"
fi
if [ -z "$CHROME" ]; then
  echo "✗ Chrome not found. Install Google Chrome." >&2
  exit 1
fi

# Already listening on the port? Then a debug Chrome is (probably) up already.
if curl -s "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "✓ A debuggable Chrome is already listening on port ${PORT}."
  echo "  MCP attach flag:  --browser-url=http://127.0.0.1:${PORT}"
  exit 0
fi

mkdir -p "$PROFILE_DIR"
echo "Launching Chrome on debug port ${PORT}"
echo "  profile: ${PROFILE_DIR}"
echo "  → log into the account the task needs in this window."
echo "  → MCP attach flag:  --browser-url=http://127.0.0.1:${PORT}"

"$CHROME" \
  --remote-debugging-port="${PORT}" \
  --user-data-dir="${PROFILE_DIR}" \
  --no-first-run \
  --no-default-browser-check \
  >/dev/null 2>&1 &

echo "✓ Launched (pid $!)."
