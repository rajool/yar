"""context-guard: flags private/context-specific content, allows placeholders.

The sample "private" strings are assembled at runtime from fragments (and ``@`` via
``chr(64)``) so no real-looking email, key, token, or home path ever appears as a
literal in this file — otherwise the guard (and the no-context CI gate) would, quite
correctly, block this test from being committed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

cg = load(".claude/hooks/context-guard.py", "context_guard")

AT = chr(64)        # "@"
DASH5 = "-" * 5


def kinds(line):
    return [kind for kind, _ in cg.findings_in_line(line)]


class FlagsPrivateContent(unittest.TestCase):
    def test_real_email(self):
        self.assertIn("email", kinds("reach " + "alice" + AT + "realmail" + ".io"))

    def test_home_path_with_real_user(self):
        self.assertIn("home-path", kinds("cd /Users/" + "alice" + "/secret"))

    def test_private_key_header(self):
        line = DASH5 + "BEGIN " + "RSA PRIVATE" + " KEY" + DASH5
        self.assertIn("private-key", kinds(line))

    def test_github_token(self):
        self.assertIn("github-token", kinds("token=" + "ghp" + "_" + "A" * 36))


class AllowsPlaceholdersAndMarkers(unittest.TestCase):
    def test_placeholder_email(self):
        self.assertEqual(kinds("see " + "you" + AT + "example" + ".com"), [])

    def test_placeholder_home_path(self):
        self.assertEqual(kinds("cd /Users/" + "you" + "/project"), [])

    def test_inline_allow_marker_skips_line(self):
        marker = "context-guard" + ":" + "allow"
        line = "alice" + AT + "realmail" + ".io   # " + marker
        self.assertEqual(cg.findings_in_line(line), [])

    def test_plain_text(self):
        self.assertEqual(kinds("just some ordinary english prose"), [])


if __name__ == "__main__":
    unittest.main()
