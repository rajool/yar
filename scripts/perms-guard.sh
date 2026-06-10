#!/usr/bin/env bash
# perms-guard — entry point for the PreToolUse(Bash) hook in Claude Code.
# Enforces yar's destructive-command deny policy (the always-on backstop for the
# same rules that /yar:install-perms writes into a repo's settings.json):
#   • rm -rf / -fr / -Rf / -r -f / --recursive --force (incl. `sudo rm -rf`) → block
#   • docker rm -f / docker container rm -f                                  → block
# Mechanism: exit 2 means "block" (the stderr message goes back to Claude). exit 0 = allow.
# fail-open: no python3 or any error → exit 0 (never block legitimate work).
# Deliberate bypass (rare): PERMS_GUARD=off
set -u
[ "${PERMS_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/perms-guard.py"
