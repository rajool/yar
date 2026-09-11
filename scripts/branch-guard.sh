#!/usr/bin/env bash
# branch-guard — entry point for the PreToolUse(Edit|Write|NotebookEdit) hook in Claude Code.
# On the main branch, it blocks edits to files inside the repo so that a branch is created first.
# This mechanically enforces the rule "real work on a branch, not directly on main" (same philosophy as git-guard).
# exit 2 = block (stderr message goes back to Claude). exit 0 = allow.
# fail-open: no python3 or any error → exit 0. Rare deliberate bypass: BRANCH_GUARD=off
set -u
[ "${BRANCH_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/branch-guard.py"
