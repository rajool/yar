"""pre-commit: rejects staged binaries/secrets, allows text/code and .env.example.

Run via subprocess against throwaway git repos. The hook reads ``git diff --cached``,
so each case stages one file and runs the hook with the repo as the working directory.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO  # noqa: E402

HOOK = os.path.join(REPO, "scripts/pre-commit")


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def staged_repo(filename, content="x\n"):
    repo = tempfile.mkdtemp(prefix="yar-pc-")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "you@example.com")
    git(repo, "config", "user.name", "Test")
    with open(os.path.join(repo, filename), "w") as fh:
        fh.write(content)
    git(repo, "add", filename)
    return repo


def run_hook(repo):
    proc = subprocess.run(["bash", HOOK], cwd=repo, capture_output=True, text=True)
    return proc.returncode


class PreCommit(unittest.TestCase):
    def setUp(self):
        self.tmpdirs = []

    def tearDown(self):
        for d in self.tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def _staged(self, filename, content="x\n"):
        repo = staged_repo(filename, content)
        self.tmpdirs.append(repo)
        return repo

    def test_allows_text_and_code(self):
        self.assertEqual(run_hook(self._staged("notes.md")), 0)
        self.assertEqual(run_hook(self._staged("script.py", "print(1)\n")), 0)

    def test_blocks_binaries(self):
        for fn in ("doc.pdf", "image.png", "audio.m4a", "archive.zip"):
            self.assertEqual(run_hook(self._staged(fn)), 1, fn)

    def test_blocks_secrets(self):
        for fn in ("id_rsa", "server.key", "cert.pem", "prod.env"):
            self.assertEqual(run_hook(self._staged(fn)), 1, fn)

    def test_allows_env_example(self):
        self.assertEqual(run_hook(self._staged(".env.example")), 0)


if __name__ == "__main__":
    unittest.main()
