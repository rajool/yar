#!/usr/bin/env bash
# english-guard — entry point for the PreToolUse(Edit|Write|NotebookEdit|MultiEdit) hook.
# Enforces the repo policy "yar is English-only": it blocks any Write/Edit whose new
# content or target filename contains a non-Latin writing system, so non-English text
# never lands in the repo. The stderr message goes back to Claude, which rewrites it in English.
# exit 2 = block (stderr message goes back to Claude). exit 0 = allow.
# fail-open: no python3 or any error → exit 0. Rare deliberate bypass: ENGLISH_GUARD=off
set -u
[ "${ENGLISH_GUARD:-}" = "off" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/english-guard.py"
