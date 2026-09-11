#!/usr/bin/env python3
"""install-perms — merge yar's recommended permission policy into THIS repo's
.claude/settings.local.json. Run once per repo, e.g. via:  /yar:install-perms

It writes a convenience allow-list (so common safe tools stop prompting) plus a
deny-list for destructive commands. Idempotent: re-running only adds what is
missing and never removes or reorders entries you already have. Any other keys in
settings.local.json (hooks, env, model, ...) are preserved untouched.

Why settings.local.json and not settings.json: the local file is personal and
git-ignored, so the policy stays on your machine — it never rides into a commit
or a push, and is never imposed on teammates. Claude Code merges all settings
sources, so permissions behave exactly as they would from the shared file (and a
`deny` beats an `allow` from any source). Because this script (not Claude Code)
creates the file, it also makes sure the file is actually git-ignored.

Layering: the deny-list written here is the *visible* policy (it shows up in
/permissions, and a settings `deny` always beats an `allow`). The plugin's
perms-guard PreToolUse hook is the always-on, unbypassable backstop for the same
destructive patterns — it travels with the plugin and needs no per-repo install;
this file is the opt-in convenience layer.
"""
import json
import os
import subprocess
import sys

# yar's recommended policy. Edit here to change what every `install-perms` run writes.
ALLOW = ["Bash(*)", "Read(*)", "Edit(*)", "Write(*)", "Grep(*)", "Glob(*)", "WebSearch"]
DENY = ["Bash(rm -rf *)", "Bash(docker rm -f *)"]


def repo_root():
    """The current git repo's top level, or the cwd if not inside a git repo."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:
        return os.getcwd()


def merge_list(existing, additions):
    """Append each addition not already present (order preserved). Return what was added."""
    seen = set(existing)
    added = []
    for a in additions:
        if a not in seen:
            existing.append(a)
            seen.add(a)
            added.append(a)
    return added


def ensure_ignored(root, rel_path):
    """Make sure rel_path is git-ignored so it can never be committed or pushed.

    Returns a one-line status for reporting, or None when root is not a git repo
    (nothing can be pushed from a non-repo, so there is nothing to do).
    """
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode

    if git("rev-parse", "--git-dir") != 0:
        return None
    if git("ls-files", "--error-unmatch", rel_path) == 0:
        return (
            "⚠ {0} is already TRACKED by git — run `git rm --cached {0}` "
            "so it stops being committed.".format(rel_path)
        )
    if git("check-ignore", "-q", rel_path) == 0:
        return "already git-ignored — never pushed"
    gitignore = os.path.join(root, ".gitignore")
    prefix = ""
    if os.path.exists(gitignore):
        with open(gitignore, "r", encoding="utf-8") as fh:
            content = fh.read()
        if content and not content.endswith("\n"):
            prefix = "\n"
    with open(gitignore, "a", encoding="utf-8") as fh:
        fh.write(prefix + rel_path + "\n")
    return "added to .gitignore — never pushed"


def main():
    root = repo_root()
    cfg_dir = os.path.join(root, ".claude")
    cfg_path = os.path.join(cfg_dir, "settings.local.json")

    data = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            sys.stderr.write(
                "✗ {} exists but is not valid JSON ({}).\n"
                "  Fix or remove it, then re-run — refusing to overwrite.\n".format(cfg_path, e)
            )
            sys.exit(1)
        if not isinstance(data, dict):
            sys.stderr.write(
                "✗ {} is not a JSON object. Aborting so nothing is lost.\n".format(cfg_path)
            )
            sys.exit(1)

    perms = data.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
        data["permissions"] = perms
    if not isinstance(perms.get("allow"), list):
        perms["allow"] = []
    if not isinstance(perms.get("deny"), list):
        perms["deny"] = []

    added_allow = merge_list(perms["allow"], ALLOW)
    added_deny = merge_list(perms["deny"], DENY)

    os.makedirs(cfg_dir, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    ignore_status = ensure_ignored(root, ".claude/settings.local.json")

    print("✅ yar permission policy merged into {}".format(cfg_path))
    print("   allow: +{} added, {} already present".format(
        len(added_allow), len(ALLOW) - len(added_allow)))
    print("   deny:  +{} added, {} already present".format(
        len(added_deny), len(DENY) - len(added_deny)))
    if added_allow:
        print("   added allow: " + ", ".join(added_allow))
    if added_deny:
        print("   added deny:  " + ", ".join(added_deny))
    if ignore_status:
        print("   local file: " + ignore_status)
    print("   Backstop: the plugin's perms-guard hook also blocks rm -rf / "
          "docker rm -f automatically (always on, no install).")


if __name__ == "__main__":
    main()
