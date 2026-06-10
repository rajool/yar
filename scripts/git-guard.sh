#!/usr/bin/env bash
# git-guard — entry point for the PreToolUse(Bash) hook in Claude Code.
# This layer is *preventive*: it stops unsafe staging before it runs.
#   • git add -A / --all / -u / -f / .   → block
#   • git commit -a / -am                → block
# Mechanism: exit 2 means "block" (the stderr message goes back to Claude). exit 0 means "allow".
# fail-open: no python3 or any error → exit 0 (never block legitimate work).
# Deliberate bypass (rare): GIT_GUARD=off
set -u
[ "${GIT_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/git-guard.py"
