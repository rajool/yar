"""context-guard: flags private/context-specific content, allows placeholders.

The sample "private" strings are assembled at runtime from fragments (and ``@`` via
``chr(64)``) so no real-looking email, key, token, or home path ever appears as a
literal in this file — otherwise the guard (and the no-context CI gate) would, quite
correctly, block this test from being committed.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO, load  # noqa: E402

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


class ProjectPaths(unittest.TestCase):
    def test_home_relative_path_into_a_specific_project(self):
        self.assertIn("project-path", kinds("cd ~/Proj" + "ects/some-repo"))

    def test_bare_roots_are_fine(self):
        self.assertEqual(kinds("roots: ~/Projects ~/Code ~/repos ~/src"), [])
        self.assertEqual(kinds("DAILY_REPO_ROOTS=~/Projects:~/Clients"), [])

    def test_placeholder_project_is_fine(self):
        self.assertEqual(kinds("clone it into ~/Projects/<repo>"), [])
        self.assertEqual(kinds("cd ~/Projects/your-project"), [])


class NoreplyAddresses(unittest.TestCase):
    def test_bot_and_privacy_senders_are_not_personal(self):
        self.assertEqual(kinds("Co-Authored-By: Bot <noreply" + AT + "somevendor.com>"), [])
        self.assertEqual(kinds("handle" + AT + "users.noreply.github.com"), [])


GUARD = os.path.join(REPO, ".claude", "hooks", "context-guard.py")


def run_hook(tool_name, tool_input):
    """Feed one PreToolUse payload to the guard in hook mode; return the process."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=REPO)
    env.pop("CONTEXT_GUARD", None)
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run([sys.executable, GUARD], input=payload, capture_output=True,
                          text=True, env=env, cwd=REPO)


class HookModeReadsProseCommands(unittest.TestCase):
    def test_commit_message_with_private_content_is_blocked(self):
        cmd = 'git commit -m "ask ' + "alice" + AT + "realmail.io" + '" -- a.py'
        r = run_hook("Bash", {"command": cmd})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("email", r.stderr)

    def test_pr_text_with_private_content_is_blocked(self):
        cmd = "gh pr edit 7 --body 'tested in ~/Proj" + "ects/some-repo'"
        r = run_hook("Bash", {"command": cmd})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("project-path", r.stderr)

    def test_attribution_trailer_is_fine(self):
        cmd = ('git commit -m "fix: x" -m "Co-Authored-By: Bot <noreply' + AT
               + 'somevendor.com>" -- a.py')
        r = run_hook("Bash", {"command": cmd})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_commands_are_not_read(self):
        r = run_hook("Bash", {"command": "grep -rn " + "alice" + AT + "realmail.io ."})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_edit_payloads_still_work(self):
        r = run_hook("Edit", {"file_path": os.path.join(REPO, "README.md"),
                              "new_string": "see /Users/" + "alice" + "/secret"})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("home-path", r.stderr)


if __name__ == "__main__":
    unittest.main()
