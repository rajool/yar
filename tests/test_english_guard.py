"""english-guard: blocks non-Latin scripts inside the repo, allows English + symbols.

Run via subprocess because the script's logic executes at import time. The non-Latin
and symbol inputs are built with ``chr(0x....)`` from code points so this source file
stays pure ASCII (the same technique the guard itself uses) -- otherwise the guard
would block this test from being committed. Python materializes the real characters
before they reach the subprocess on stdin.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO  # noqa: E402

SCRIPT = os.path.join(REPO, ".claude/hooks/english-guard.py")

# Persian/Arabic "salaam" -- a non-Latin script the guard must block.
PERSIAN = "".join(chr(c) for c in (0x0633, 0x0644, 0x0627, 0x0645))
# Accented Latin, Greek mu, an arrow and a check mark -- all allowed (not blocked).
ENGLISH_WITH_SYMBOLS = (
    "caf" + chr(0x00E9) + " na" + chr(0x00EF) + "ve "   # cafe, naive
    + chr(0x03BC) + " " + chr(0x2192) + " " + chr(0x2713) + " done"
)


def run(tool_input, env_extra=None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = REPO
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps({"tool_input": tool_input}),
        capture_output=True, text=True, env=env,
    )
    return proc.returncode


class BlocksNonEnglish(unittest.TestCase):
    def test_non_latin_content(self):
        rc = run({"file_path": os.path.join(REPO, "scratch.md"),
                  "content": PERSIAN + " hello"})
        self.assertEqual(rc, 2)

    def test_non_latin_filename(self):
        rc = run({"file_path": os.path.join(REPO, PERSIAN + ".md"), "content": "ok"})
        self.assertEqual(rc, 2)


class AllowsEnglishAndSymbols(unittest.TestCase):
    def test_english_with_accents_and_symbols(self):
        rc = run({"file_path": os.path.join(REPO, "scratch.md"),
                  "content": ENGLISH_WITH_SYMBOLS})
        self.assertEqual(rc, 0)

    def test_file_outside_repo_is_ignored(self):
        rc = run({"file_path": "/tmp/yar-outside-scratch.md", "content": PERSIAN})
        self.assertEqual(rc, 0)

    def test_env_bypass(self):
        rc = run({"file_path": os.path.join(REPO, "scratch.md"), "content": PERSIAN},
                 env_extra={"ENGLISH_GUARD": "off"})
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
