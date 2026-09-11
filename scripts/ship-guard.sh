#!/usr/bin/env bash
# ship-guard — entry point for the UserPromptSubmit / PostToolUse(Bash) / Stop hooks in Claude Code.
# Makes "ship" mean MERGED: a "ship" prompt arms a per-session marker and injects the full chain;
# `gh pr create` output is recorded and followed by a nudge; the Stop hook refuses to end the turn
# (at most 3 times) while a PR from this session is unmerged, commits are unpushed or have no PR,
# or nothing was committed at all. It verifies with `gh pr view` + git and releases itself on MERGED.
# Mechanism: hook JSON on stdin; JSON on stdout (additionalContext / decision=block); always exit 0.
# fail-open: no python3 or any error → exit 0 (never trap a session).
# Escape hatch (must state a reason):  ship-guard.sh release --marker <path> --reason "<why>"
# Deliberate bypass (rare): SHIP_GUARD=off
set -u
[ "${SHIP_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/ship-guard.py" "$@"
