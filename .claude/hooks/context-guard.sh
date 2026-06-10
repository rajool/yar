#!/usr/bin/env bash
# context-guard - entry point for the PreToolUse(Edit|Write|NotebookEdit|MultiEdit) hook.
# Keeps the yar repo generic/public: blocks writing private/context-specific content
# (emails, home paths, secrets, denylisted private terms) into the repo.
# exit 2 = block (stderr message goes back to Claude). exit 0 = allow.
# fail-open: no python3 or any error -> exit 0. Local one-off bypass: CONTEXT_GUARD=off
set -u
[ "${CONTEXT_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/context-guard.py"
