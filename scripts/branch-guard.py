#!/usr/bin/env python3
# branch-guard — PreToolUse(Edit|Write|NotebookEdit) hook logic.
# If the target file is inside the repo and the current branch is main, it blocks the edit
# so that a branch is created first (git-workflow policy). exit 2 = block, exit 0 = allow.
# fail-open: any error / no git → exit 0 (never block legitimate work).
# Rare deliberate bypass: BRANCH_GUARD=off
import json
import os
import subprocess
import sys


def allow():
    sys.exit(0)


if os.environ.get("BRANCH_GUARD") == "off":
    allow()

try:
    data = json.load(sys.stdin)
except Exception:
    allow()

tool_input = (data or {}).get("tool_input", {}) or {}
path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
if not path:
    allow()

abspath = os.path.realpath(path)  # resolve symlinks so it matches git's output

# Find the nearest existing directory (a new file may not have been created yet).
d = os.path.dirname(abspath) or "."
while d and not os.path.isdir(d):
    parent = os.path.dirname(d)
    if parent == d:
        break
    d = parent


def git(args):
    return subprocess.check_output(
        ["git", "-C", d] + args, stderr=subprocess.DEVNULL
    ).decode().strip()


try:
    root = git(["rev-parse", "--show-toplevel"])
except Exception:
    allow()  # not inside a git repo → don't block
root = os.path.realpath(root)

# Only files inside this repo matter (not outside files like ~/.claude).
if not (abspath == root or abspath.startswith(root + os.sep)):
    allow()

try:
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"])
except Exception:
    allow()

if branch != "main":
    allow()

msg = (
    "⛔ Don't edit on the main branch (policy: real work happens on a branch).\n"
    "   First create a branch, then continue:\n"
    "       git switch -c feat/<summary>\n"
    "   Working in parallel? Create a worktree — git-workflow skill / reference/worktrees.md\n"
    "   Rare deliberate bypass: BRANCH_GUARD=off\n"
    "   — blocked by branch-guard: no edits on main."
)
sys.stderr.write(msg + "\n")
sys.exit(2)
