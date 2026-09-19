"""ship-guard: "ship" means MERGED.

Three hook events and a CLI, exercised end to end through subprocess against throwaway
git repos and a fake ``gh`` on PATH (its answers come from FAKE_GH_* env vars), so the
tests cover the real decision path: arm on "ship" -> record the PR -> refuse to stop
while it is open -> release once merged. Pure helpers (trigger words, URL parsing) are
tested directly.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO, load  # noqa: E402

SCRIPT = os.path.join(REPO, "scripts/ship-guard.py")
sg = load("scripts/ship-guard.py", "ship_guard")

FAKE_GH = r'''#!/usr/bin/env bash
# fake gh for tests: answers `gh pr view ... --json ...` from FAKE_GH_* env vars.
state="${FAKE_GH_STATE:-NONE}"
case "$state" in
  NONE) echo 'no pull requests found for branch "feat/x"' >&2; exit 1 ;;
  FAIL) echo 'error connecting to api.github.com' >&2; exit 4 ;;
esac
printf '{"state":"%s","number":%s,"url":"%s","headRefName":"feat/x","headRefOid":"%s","baseRefName":"main","isDraft":%s,"autoMergeRequest":null}\n' \
  "$state" "${FAKE_GH_NUMBER:-42}" "${FAKE_GH_URL:-https://github.com/acme/widgets/pull/42}" \
  "${FAKE_GH_OID:-}" "${FAKE_GH_DRAFT:-false}"
'''

PR_URL = "https://github.com/acme/widgets/pull/42"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class Sandbox:
    """A temp state dir, a fake gh on PATH, and a repo with an origin and a feature branch."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="yar-ship-")
        self.state = os.path.join(self.tmp, "state")
        self.bindir = os.path.join(self.tmp, "bin")
        os.makedirs(self.bindir)
        gh = os.path.join(self.bindir, "gh")
        with open(gh, "w") as fh:
            fh.write(FAKE_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)

        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q")
        git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        git(self.repo, "config", "user.email", "you@example.com")
        git(self.repo, "config", "user.name", "Test")
        self.write("README.md", "hello\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-q", "-m", "init")
        self.origin = os.path.join(self.tmp, "origin.git")
        subprocess.run(["git", "clone", "-q", "--bare", self.repo, self.origin],
                       check=True, capture_output=True)
        git(self.repo, "remote", "add", "origin", self.origin)
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "branch", "-q", "-u", "origin/main", "main")
        git(self.repo, "remote", "set-head", "origin", "main")

    def write(self, name, text):
        with open(os.path.join(self.repo, name), "w") as fh:
            fh.write(text)

    def feature(self, commits=1, push=False):
        git(self.repo, "switch", "-q", "-c", "feat/x")
        for i in range(commits):
            self.write("f{}.txt".format(i), "work {}\n".format(i))
            git(self.repo, "add", "f{}.txt".format(i))
            git(self.repo, "commit", "-q", "-m", "feat: step {}".format(i))
        if push:
            git(self.repo, "push", "-q", "-u", "origin", "feat/x")
        return git(self.repo, "rev-parse", "HEAD")

    def env(self, extra=None):
        env = dict(os.environ)
        env["SHIP_GUARD_STATE_DIR"] = self.state
        env["PATH"] = self.bindir + os.pathsep + env.get("PATH", "")
        env.pop("SHIP_GUARD_WORDS", None)
        env.pop("SHIP_GUARD", None)
        if extra:
            env.update(extra)
        return env

    def hook(self, payload, extra=None):
        p = subprocess.run([sys.executable, SCRIPT], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env(extra))
        out = p.stdout.strip()
        return p.returncode, (json.loads(out) if out else None)

    def cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                              text=True, env=self.env())

    def marker(self, sid="s1"):
        path = os.path.join(self.state, sid + ".json")
        if not os.path.exists(path):
            return None
        with open(path) as fh:
            return json.load(fh)

    def marker_path(self, sid="s1"):
        return os.path.join(self.state, sid + ".json")

    # payload builders
    def prompt(self, text, sid="s1", cwd=None):
        return {"hook_event_name": "UserPromptSubmit", "session_id": sid,
                "cwd": cwd or self.repo, "prompt": text}

    def post(self, command, stdout="", sid="s1", tool="Bash"):
        return {"hook_event_name": "PostToolUse", "session_id": sid, "cwd": self.repo,
                "tool_name": tool, "tool_input": {"command": command},
                "tool_response": {"stdout": stdout, "stderr": "", "exit_code": 0}}

    def stop(self, sid="s1", cwd=None, last=None):
        d = {"hook_event_name": "Stop", "session_id": sid, "cwd": cwd or self.repo,
             "stop_hook_active": False}
        if last is not None:
            d["last_assistant_message"] = last
        return d

    def arm(self, sid="s1"):
        self.hook(self.prompt("ship", sid=sid))

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TriggerWords(unittest.TestCase):
    def test_ship_as_a_word_triggers(self):
        for text in ("ship", "Ship", "ship it", "ship and merge", "please ship then",
                     "SHIP!", "ship \u06a9\u0646", "done; ship"):
            self.assertTrue(sg.is_ship_prompt(text), text)

    def test_ship_inside_other_words_does_not(self):
        for text in ("shipping address", "it shipped yesterday", "our relationship",
                     "the shipment arrived", "spaceship", "", "   "):
            self.assertFalse(sg.is_ship_prompt(text), text)

    def test_long_prompt_counts_only_near_start_or_end(self):
        filler = "x" * 300
        self.assertTrue(sg.is_ship_prompt(filler + " then ship it"))
        self.assertTrue(sg.is_ship_prompt("ship this: " + filler + filler))
        self.assertFalse(sg.is_ship_prompt(filler + " a ship sailed " + filler))

    def test_extra_words_from_env(self):
        os.environ["SHIP_GUARD_WORDS"] = "land it, merge it"
        try:
            self.assertTrue(sg.is_ship_prompt("ok, land it"))
            self.assertTrue(sg.is_ship_prompt("Merge It"))
            self.assertFalse(sg.is_ship_prompt("landing page"))
        finally:
            del os.environ["SHIP_GUARD_WORDS"]

    def test_pr_urls(self):
        text = "Creating pull request...\n{}\nsee also {}\n".format(PR_URL, PR_URL)
        self.assertEqual(sg.pr_urls(text), [PR_URL])
        self.assertEqual(sg.pr_number(PR_URL), 42)
        self.assertEqual(sg.pr_urls("no links here"), [])


class HookFlow(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    # -- UserPromptSubmit --------------------------------------------------------
    def test_ship_prompt_arms_and_injects_contract(self):
        rc, out = self.sb.hook(self.sb.prompt("ship"))
        self.assertEqual(rc, 0)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("MERGED", ctx)
        self.assertIn("gh pr merge", ctx)
        m = self.sb.marker()
        self.assertIsNone(m["released"])
        self.assertEqual(m["repo_root"], os.path.realpath(self.sb.repo))

    def test_other_prompts_are_silent(self):
        rc, out = self.sb.hook(self.sb.prompt("fix the shipping label"))
        self.assertEqual(rc, 0)
        self.assertIsNone(out)
        self.assertIsNone(self.sb.marker())

    # -- PostToolUse -------------------------------------------------------------
    def test_pr_create_is_recorded_and_nudged(self):
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.post("gh pr create --fill", PR_URL + "\n"))
        self.assertEqual(rc, 0)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("gh pr merge 42 --squash", ctx)
        self.assertIn("MERGED", ctx)
        self.assertEqual(self.sb.marker()["prs"], [PR_URL])

    def test_pr_list_urls_are_not_recorded(self):
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.post("gh pr list", PR_URL + "\n"))
        self.assertIsNone(out)
        self.assertEqual(self.sb.marker().get("prs"), [])

    def test_post_tool_ignores_when_not_armed(self):
        rc, out = self.sb.hook(self.sb.post("gh pr create --fill", PR_URL + "\n"))
        self.assertIsNone(out)
        self.assertIsNone(self.sb.marker())

    # -- Stop --------------------------------------------------------------------
    def test_stop_without_marker_allows(self):
        self.sb.feature()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "OPEN"})
        self.assertEqual((rc, out), (0, None))

    def test_open_pr_blocks_with_merge_instructions(self):
        self.sb.feature(push=True)
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "OPEN"})
        self.assertEqual(rc, 0)
        self.assertEqual(out["decision"], "block")
        self.assertIn("OPEN", out["reason"])
        self.assertIn("gh pr merge 42 --squash --delete-branch", out["reason"])
        self.assertIn("release --marker", out["reason"])
        self.assertEqual(self.sb.marker()["blocks"], 1)

    def test_recorded_pr_is_checked_even_outside_the_repo(self):
        self.sb.arm()
        self.sb.hook(self.sb.post("gh pr create --fill", PR_URL + "\n"))
        elsewhere = os.path.join(self.sb.tmp, "not-a-repo")
        os.makedirs(elsewhere)
        rc, out = self.sb.hook(self.sb.stop(cwd=elsewhere), {"FAKE_GH_STATE": "OPEN"})
        self.assertEqual(out["decision"], "block")
        self.assertIn("#42", out["reason"])

    def test_commits_without_pr_block(self):
        self.sb.feature(commits=2)
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "NONE"})
        self.assertEqual(out["decision"], "block")
        self.assertIn("no pull request", out["reason"])
        self.assertIn("gh pr create --fill", out["reason"])

    def test_merged_and_clean_releases(self):
        head = self.sb.feature()
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": head})
        self.assertEqual((rc, out), (0, None))
        self.assertIn("verified", self.sb.marker()["released"]["reason"])

    def test_commits_after_the_merged_pr_block(self):
        first = self.sb.feature()
        self.sb.write("late.txt", "late\n")
        git(self.sb.repo, "add", "late.txt")
        git(self.sb.repo, "commit", "-q", "-m", "feat: after merge")
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": first})
        self.assertEqual(out["decision"], "block")
        self.assertIn("AFTER PR #42", out["reason"])

    def test_contract_gates_the_delete_on_merged(self):
        rc, out = self.sb.hook(self.sb.prompt("ship"))
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("SEPARATE command", ctx)
        self.assertIn("git reset --hard origin/<default>", ctx)
        self.assertIn("never from the old HEAD", ctx)
        rc, out = self.sb.hook(self.sb.post("gh pr create --fill", PR_URL + "\n"))
        nudge = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("--jq .state", nudge)
        self.assertIn("only after MERGED", nudge)

    def test_dead_pre_squash_commits_block_until_the_branch_is_reset(self):
        head = self.sb.feature()                      # feat/x: f0.txt, one commit
        # simulate the squash-merge on origin/main: same tree, a different commit
        git(self.sb.repo, "switch", "-q", "main")
        self.sb.write("f0.txt", "work 0\n")
        git(self.sb.repo, "add", "f0.txt")
        git(self.sb.repo, "commit", "-q", "-m", "feat: step 0 (#42)")
        git(self.sb.repo, "push", "-q", "origin", "main")
        git(self.sb.repo, "switch", "-q", "feat/x")
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": head})
        self.assertEqual(out["decision"], "block")
        self.assertIn("pre-squash", out["reason"])
        self.assertIn("git branch -D feat/x", out["reason"])   # plain checkout, not a worktree
        # the prescribed cleanup releases the guard
        git(self.sb.repo, "switch", "-q", "main")
        git(self.sb.repo, "branch", "-D", "feat/x")
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": head})
        self.assertEqual((rc, out), (0, None))

    def test_dead_commits_in_a_worktree_prescribe_a_reset(self):
        head = self.sb.feature()
        git(self.sb.repo, "switch", "-q", "main")
        self.sb.write("f0.txt", "work 0\n")
        git(self.sb.repo, "add", "f0.txt")
        git(self.sb.repo, "commit", "-q", "-m", "feat: step 0 (#42)")
        git(self.sb.repo, "push", "-q", "origin", "main")
        wt = os.path.join(self.sb.tmp, "wt")
        git(self.sb.repo, "worktree", "add", "-q", wt, "feat/x")
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(cwd=wt), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": head})
        self.assertEqual(out["decision"], "block")
        self.assertIn("git reset --hard origin/main", out["reason"])
        git(wt, "reset", "-q", "--hard", "origin/main")
        rc, out = self.sb.hook(self.sb.stop(cwd=wt), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": head})
        self.assertEqual((rc, out), (0, None))

    def test_default_branch_clean_releases(self):
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop())
        self.assertEqual((rc, out), (0, None))
        self.assertTrue(self.sb.marker()["released"])

    def test_dirty_tree_with_nothing_merged_blocks(self):
        self.sb.feature(commits=0)
        self.sb.write("wip.txt", "uncommitted\n")
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "NONE"})
        self.assertEqual(out["decision"], "block")
        self.assertIn("uncommitted", out["reason"])

    def test_dirty_tree_after_a_merge_does_not_block(self):
        head = self.sb.feature()
        self.sb.write("journal.md", "auto-logged\n")
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "MERGED", "FAKE_GH_OID": head})
        self.assertEqual((rc, out), (0, None))

    def test_claimed_shipped_is_called_out(self):
        self.sb.feature(push=True)
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(last="Shipped: PR #42 is ready."),
                               {"FAKE_GH_STATE": "OPEN"})
        self.assertTrue(out["reason"].startswith("ship-guard: your last message"))

    def test_gh_failure_is_fail_open_but_keeps_the_marker_armed(self):
        self.sb.feature()
        self.sb.arm()
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "FAIL"})
        self.assertEqual((rc, out), (0, None))
        self.assertIsNone(self.sb.marker()["released"])

    def test_gives_up_after_max_blocks(self):
        self.sb.feature(push=True)
        self.sb.arm()
        for i in range(sg.MAX_BLOCKS):
            rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "OPEN"})
            self.assertEqual(out["decision"], "block", i)
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "OPEN"})
        self.assertIsNone(out)
        self.assertEqual(self.sb.marker()["blocks"], sg.MAX_BLOCKS)

    def test_new_ship_prompt_rearms_and_resets_blocks(self):
        self.sb.feature(push=True)
        self.sb.arm()
        self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "OPEN"})
        self.assertEqual(self.sb.marker()["blocks"], 1)
        self.sb.hook(self.sb.prompt("ok, ship it"))
        self.assertEqual(self.sb.marker()["blocks"], 0)

    # -- release CLI -------------------------------------------------------------
    def test_release_lets_the_turn_end_and_needs_a_reason(self):
        self.sb.feature(push=True)
        self.sb.arm()
        short = self.sb.cli("release", "--marker", self.sb.marker_path(), "--reason", "no")
        self.assertEqual(short.returncode, 2)
        ok = self.sb.cli("release", "--marker", self.sb.marker_path(),
                         "--reason", "needs a human review of the migration")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("UNFINISHED", ok.stdout)
        rc, out = self.sb.hook(self.sb.stop(), {"FAKE_GH_STATE": "OPEN"})
        self.assertEqual((rc, out), (0, None))

    def test_release_by_session_and_status(self):
        self.sb.arm()
        ok = self.sb.cli("release", "--session", "s1", "--reason", "waiting for the user")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        st = self.sb.cli("status")
        self.assertIn("released", st.stdout)

    def test_env_bypass_via_wrapper(self):
        wrapper = os.path.join(REPO, "scripts/ship-guard.sh")
        p = subprocess.run(["bash", wrapper], input=json.dumps(self.sb.prompt("ship")),
                           capture_output=True, text=True, env=self.sb.env({"SHIP_GUARD": "off"}))
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertIsNone(self.sb.marker())


if __name__ == "__main__":
    unittest.main()
