#!/usr/bin/env bash
# alias-guard -- entry point for the UserPromptSubmit hook in Claude Code.
# Reads the user's own alias table (~/.claude/yar-aliases.json or the project's) and,
# when a prompt uses one of their shorthands, hands Claude the mapping: which skill to
# invoke and that it is to be run in full. yar ships no aliases, so this is silent
# until the user writes a table.
# Mechanism: hook JSON on stdin; JSON on stdout (additionalContext); always exit 0.
# fail-open: no python3 or any error -> exit 0 (never trap a session).
# CLI:  alias-guard.sh list  |  alias-guard.sh example
# Deliberate bypass (rare): ALIAS_GUARD=off  (or YAR_ALIASES=off for the table alone)
set -u
[ "${ALIAS_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/alias-guard.py" "$@"
