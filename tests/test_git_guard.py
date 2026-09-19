"""git-guard: blocks bulk/force staging, allows explicit-path staging.

Mirrors the decision in ``git-guard.py`` ``main()``: split the command into
segments, tokenize each, and ask ``git_reason``. Every case here maps to a line in
the script's own docstring — the tests turn that documentation into executable specs.
"""
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

gg = load("scripts/git-guard.py", "git_guard")


def decide(cmd):
    """Return git-guard's block reason for a full command line, or None to allow."""
    for seg in gg.split_segments(cmd):
        if not seg.strip():
            continue
        try:
            toks = shlex.split(seg, posix=True)
        except Exception:
            if gg.DANGER_RE.search(seg) or gg.COMMIT_A_RE.search(seg):
                return "unsafe"
            continue
        reason = gg.git_reason(toks)
        if reason:
            return reason
    return None


class BlocksBulkStaging(unittest.TestCase):
    def test_add_flag_variants(self):
        for cmd in ("git add -A", "git add --all", "git add -u",
                    "git add --update", "git add -f x", "git add --force x"):
            self.assertIsNotNone(decide(cmd), cmd)

    def test_add_dot_and_globs(self):
        for cmd in ("git add .", "git add ./", "git add *", "git add :/"):
            self.assertIsNotNone(decide(cmd), cmd)

    def test_commit_all(self):
        for cmd in ("git commit -a", "git commit -am 'x'", "git commit --all -m x"):
            self.assertIsNotNone(decide(cmd), cmd)

    def test_combined_short_flags(self):
        self.assertIsNotNone(decide("git add -Av"))          # contains A
        self.assertIsNotNone(decide("git commit -am 'msg'"))  # contains a

    def test_inside_compound_command(self):
        self.assertIsNotNone(decide("git status && git add -A"))
        self.assertIsNotNone(decide("echo hi; git add ."))

    def test_commit_all_after_message(self):
        # a real -a / --all after the message is still caught
        self.assertIsNotNone(decide("git commit -m 'msg' -a"))
        self.assertIsNotNone(decide("git commit -m 'msg' --all"))


class AllowsExplicitStaging(unittest.TestCase):
    def test_explicit_paths(self):
        for cmd in ("git add src/file.py", "git add a/b.txt c/d.txt",
                    "git commit -m 'feat: x'", "git status", "git diff --cached"):
            self.assertIsNone(decide(cmd), cmd)

    def test_global_options_are_skipped(self):
        self.assertIsNotNone(decide("git -C /tmp/x add -A"))    # still catches add -A
        self.assertIsNone(decide("git -C /tmp/x add file.py"))  # explicit path is fine

    def test_non_git_commands(self):
        for cmd in ("echo git add -A", "ls -A", "rm -rf x"):
            self.assertIsNone(decide(cmd), cmd)

    def test_commit_message_value_is_not_a_flag(self):
        # a -m / -F value that begins with "-" and contains "a" must not look like -a
        for cmd in ("git commit -m '- add a thing'",
                    "git commit -m 'fix: handle the -a edge case'",
                    "git commit -F /tmp/msg.txt",
                    "git commit -m 'msg' -- file.py"):
            self.assertIsNone(decide(cmd), cmd)


if __name__ == "__main__":
    unittest.main()


# ---- remote-branch deletion gate ---------------------------------------------------
_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts", "git-guard.py")
_FAKE_GH = r'''#!/usr/bin/env bash
# fake gh for tests: `gh pr view <branch> --json state,number` answers from FAKE_GH_STATE.
state="${FAKE_GH_STATE:-NONE}"
case "$state" in
  NONE) echo 'no pull requests found for branch "feat/x"' >&2; exit 1 ;;
  FAIL) echo 'error connecting to api.github.com' >&2; exit 4 ;;
esac
printf '{"state":"%s","number":14}\n' "$state"
'''


def _run_guard(cmd, gh_state=None):
    """Run git-guard.py as the PreToolUse hook would; return (exit code, stderr)."""
    tmp = tempfile.mkdtemp(prefix="yar-gg-")
    try:
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w") as fh:
            fh.write(_FAKE_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        env = dict(os.environ)
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
        if gh_state:
            env["FAKE_GH_STATE"] = gh_state
        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": tmp}
        p = subprocess.run([sys.executable, _SCRIPT], input=json.dumps(payload),
                    capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class BranchDeletionGate(unittest.TestCase):
    def test_push_delete_target_recognizes_every_spelling(self):
        for cmd in ("git push origin --delete feat/x", "git push --delete origin feat/x",
                    "git push -d origin feat/x", "git push origin :feat/x",
                    "git -C /some/repo push origin --delete feat/x",
                    "git push -q origin --delete feat/x"):
            self.assertEqual(gg.push_delete_target(shlex.split(cmd)), "feat/x", cmd)

    def test_ordinary_pushes_are_not_deletions(self):
        for cmd in ("git push origin feat/x", "git push -u origin HEAD",
                    "git push --force-with-lease", "git push origin main:main",
                    "git branch -D feat/x", "gh pr merge 14 --squash --delete-branch"):
            self.assertIsNone(gg.push_delete_target(shlex.split(cmd)), cmd)

    def test_delete_chained_to_merge_is_blocked_without_asking_gh(self):
        rc, err = _run_guard("gh pr merge 14 --squash && git push origin --delete feat/x",
                             gh_state="MERGED")
        self.assertEqual(rc, 2)
        self.assertIn("chained", err)
        self.assertIn("MERGED", err)
        rc, err = _run_guard("gh pr merge 14 --squash; git push origin :feat/x")
        self.assertEqual(rc, 2)

    def test_standalone_delete_is_blocked_while_the_pr_is_open(self):
        rc, err = _run_guard("git push origin --delete feat/x", gh_state="OPEN")
        self.assertEqual(rc, 2)
        self.assertIn("still OPEN", err)
        self.assertIn("#14", err)

    def test_standalone_delete_is_allowed_once_merged_closed_or_without_pr(self):
        for state in ("MERGED", "CLOSED", "NONE", "FAIL"):
            rc, err = _run_guard("git push origin --delete feat/x", gh_state=state)
            self.assertEqual((rc, err), (0, ""), state)

    def test_merge_with_gh_delete_branch_flag_is_allowed(self):
        # gh deletes the branch only after a successful merge -- that is the safe form
        rc, err = _run_guard("gh pr merge 14 --squash --delete-branch", gh_state="OPEN")
        self.assertEqual((rc, err), (0, ""))
