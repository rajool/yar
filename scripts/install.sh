#!/usr/bin/env bash
# install.sh — wire the git-level `pre-commit` guard (blocks committing binaries/secrets)
# into the CURRENT git repository. Run once per repo/clone, e.g. via:  /yar:install-guards
#
# Why this is needed: the other two guards (git-guard, branch-guard) are Claude Code hooks and
# run automatically once the plugin is enabled. `pre-commit` is a *git* hook, so it must be placed
# inside each repo to also catch commits made from a terminal or GUI (not just from Claude).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/pre-commit"
[ -f "$SRC" ] || { echo "✗ Can't find pre-commit next to install.sh ($SRC)." >&2; exit 1; }

# Target = the git repo of the current working directory.
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null)" || {
  echo "✗ Not inside a git repository. cd into your project, then run this again." >&2
  exit 1
}
GIT_DIR="$(cd "$GIT_DIR" && pwd)"
TOPLEVEL="$(git rev-parse --show-toplevel)"

# Honour an existing core.hooksPath; otherwise use the repo's .git/hooks.
HOOKS_PATH="$(git config --get core.hooksPath || true)"
if [ -n "$HOOKS_PATH" ]; then
  case "$HOOKS_PATH" in
    /*) DEST_DIR="$HOOKS_PATH" ;;
    *)  DEST_DIR="$TOPLEVEL/$HOOKS_PATH" ;;
  esac
else
  DEST_DIR="$GIT_DIR/hooks"
fi
mkdir -p "$DEST_DIR"
DEST="$DEST_DIR/pre-commit"

# Back up a pre-existing, foreign pre-commit so we don't clobber someone's hook.
if [ -e "$DEST" ] && ! grep -q "no binaries/secrets in git" "$DEST" 2>/dev/null; then
  BAK="$DEST.bak.$$"
  cp "$DEST" "$BAK"
  echo "ℹ︎ Backed up existing pre-commit → $BAK"
fi

cp "$SRC" "$DEST"
chmod +x "$DEST"

echo "✅ Installed pre-commit guard → $DEST"
echo "   • Blocks committing binaries/secrets on any git client (terminal, GUI, Claude)."
echo "   • git-guard (no bulk/force add) + branch-guard (no edits on main) run automatically via the plugin's Claude hooks."
echo "   Bypass a single commit (rare): git commit --no-verify"
