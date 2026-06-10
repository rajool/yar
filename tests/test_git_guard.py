"""git-guard: blocks bulk/force staging, allows explicit-path staging.

Mirrors the decision in ``git-guard.py`` ``main()``: split the command into
segments, tokenize each, and ask ``git_reason``. Every case here maps to a line in
the script's own docstring — the tests turn that documentation into executable specs.
"""
import os
import shlex
import sys
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
