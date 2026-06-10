"""branch-guard: blocks edits on the default branch, allows them on a feature branch.

Run via subprocess against throwaway git repos (the script's logic executes at import
time and shells out to git). Covers: on ``main`` -> block; on a feature branch ->
allow; a file outside any repo -> allow; the ``BRANCH_GUARD=off`` bypass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO  # noqa: E402

SCRIPT = os.path.join(REPO, "scripts/branch-guard.py")


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def make_repo(branch):
    repo = tempfile.mkdtemp(prefix="yar-bg-")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "you@example.com")
    git(repo, "config", "user.name", "Test")
    with open(os.path.join(repo, "f.txt"), "w") as fh:
        fh.write("hi\n")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "branch", "-M", branch)
    return repo


def run(file_path, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps({"tool_input": {"file_path": file_path}}),
        capture_output=True, text=True, env=env,
    )
    return proc.returncode


class BranchGuard(unittest.TestCase):
    def setUp(self):
        self.tmpdirs = []

    def tearDown(self):
        for d in self.tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def _repo(self, branch):
        repo = make_repo(branch)
        self.tmpdirs.append(repo)
        return repo

    def test_blocks_on_main(self):
        repo = self._repo("main")
        self.assertEqual(run(os.path.join(repo, "f.txt")), 2)

    def test_allows_on_feature_branch(self):
        repo = self._repo("feat-x")
        self.assertEqual(run(os.path.join(repo, "f.txt")), 0)

    def test_allows_outside_any_repo(self):
        plain = tempfile.mkdtemp(prefix="yar-nogit-")
        self.tmpdirs.append(plain)
        self.assertEqual(run(os.path.join(plain, "f.txt")), 0)

    def test_env_bypass(self):
        repo = self._repo("main")
        self.assertEqual(run(os.path.join(repo, "f.txt"), {"BRANCH_GUARD": "off"}), 0)


if __name__ == "__main__":
    unittest.main()
