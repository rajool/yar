"""sweep-scan.sh: branch classification, with merged pull requests as proof.

Run via subprocess against throwaway git repos and a fake ``gh`` on PATH (its answers
come from FAKE_GH_* env vars), so the tests cover the real decision path: a
multi-commit branch squash-merged on the remote reads ``UNIQUE(N)`` from git alone and
``PRMERGED(#N)`` once a merged PR vouches for it -- and every failure mode of the PR
lookup (no gh, no token, non-GitHub remote, failed call, stale default ref) falls back
to the git-only answer rather than inventing proof.

The in-use probe is covered the same way, with a fake ``lsof`` whose snapshot each test
writes: a worktree (or orphan dir, or parked primary) some process stands in reads
``INUSE=yes`` with one ``INUSE`` row per process, nobody reads ``no``, and no snapshot
(lsof failing or missing) reads ``?`` -- unknown, never "no".
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO  # noqa: E402

SCRIPT = os.path.join(REPO, "skills/repo-sweep/scripts/sweep-scan.sh")
GITHUB_URL = "https://github.com/acme/widgets.git"

FAKE_GH = r'''#!/usr/bin/env bash
# fake gh for tests: `gh auth token -h HOST` exits $FAKE_GH_AUTH (default 0);
# `gh pr list ...` appends its argv to $FAKE_GH_LOG, then prints the TSV rows in
# $FAKE_GH_PRS (exit $FAKE_GH_LIST, default 0). Anything else is unexpected.
case "$1 $2" in
  "auth token") exit "${FAKE_GH_AUTH:-0}" ;;
  "pr list")
    [ -n "${FAKE_GH_LOG:-}" ] && printf '%s\n' "$*" >> "$FAKE_GH_LOG"
    if [ "${FAKE_GH_LIST:-0}" != 0 ]; then echo "fake gh: failure" >&2; exit "${FAKE_GH_LIST}"; fi
    [ -n "${FAKE_GH_PRS:-}" ] && [ -f "$FAKE_GH_PRS" ] && cat "$FAKE_GH_PRS"
    exit 0 ;;
  *) echo "fake gh: unexpected: $*" >&2; exit 9 ;;
esac
'''

FAKE_LSOF = r'''#!/usr/bin/env bash
# fake lsof for tests: appends its argv to $FAKE_LSOF_LOG, then either fails with
# $FAKE_LSOF_RC (non-zero: no output) or prints the -F records in $FAKE_LSOF_OUT.
[ -n "${FAKE_LSOF_LOG:-}" ] && printf '%s\n' "$*" >> "$FAKE_LSOF_LOG"
if [ "${FAKE_LSOF_RC:-0}" != 0 ]; then echo "fake lsof: failure" >&2; exit "${FAKE_LSOF_RC}"; fi
[ -n "${FAKE_LSOF_OUT:-}" ] && [ -f "$FAKE_LSOF_OUT" ] && cat "$FAKE_LSOF_OUT"
exit 0
'''


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class Sandbox:
    """A scan root holding one repo with a bare origin, plus a fake gh and a fake lsof
    on PATH.

    The origin's configured URL is a GitHub URL; a ``url.<path>.insteadOf`` rewrite
    routes every push and fetch to the local bare repo, so the scan sees a GitHub
    remote while git talks to disk. The lsof snapshot starts with one process standing
    at ``/`` -- nobody in any checkout -- so every INUSE column reads ``no`` unless a
    test says otherwise (see ``processes``).
    """

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="yar-sweep-")
        self.bindir = os.path.join(self.tmp, "bin")
        os.makedirs(self.bindir)
        for name, text in (("gh", FAKE_GH), ("lsof", FAKE_LSOF)):
            tool = os.path.join(self.bindir, name)
            with open(tool, "w") as fh:
                fh.write(text)
            os.chmod(tool, os.stat(tool).st_mode | stat.S_IEXEC)
        self.prs = os.path.join(self.tmp, "prs.tsv")
        self.log = os.path.join(self.tmp, "gh.log")
        open(self.prs, "w").close()
        self.lsof_out = os.path.join(self.tmp, "lsof.txt")
        self.lsof_log = os.path.join(self.tmp, "lsof.log")
        self.processes((1, "launchd", "/"))

        self.root = os.path.join(self.tmp, "root")
        self.repo = os.path.join(self.root, "widgets")
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
        git(self.repo, "remote", "add", "origin", GITHUB_URL)
        git(self.repo, "config", "url.%s.insteadOf" % self.origin, GITHUB_URL)
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "branch", "-q", "-u", "origin/main", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.pr_rows = []

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.repo, name), "w") as fh:
            fh.write(text)

    def feature(self, name, commits=2, push=False, start="main"):
        """A branch off START with COMMITS one-file commits; back on main after."""
        git(self.repo, "switch", "-q", "-c", name, start)
        for i in range(commits):
            fn = "%s-%d.txt" % (name.replace("/", "-"), i)
            self.write(fn, "work %d on %s\n" % (i, name))
            git(self.repo, "add", fn)
            git(self.repo, "commit", "-q", "-m", "feat: %s step %d" % (name, i))
        tip = git(self.repo, "rev-parse", "HEAD")
        if push:
            git(self.repo, "push", "-q", "-u", "origin", name)
        git(self.repo, "switch", "-q", "main")
        return tip

    def commit_on(self, name, fn, text="more\n", msg="feat: more"):
        git(self.repo, "switch", "-q", name)
        self.write(fn, text)
        git(self.repo, "add", fn)
        git(self.repo, "commit", "-q", "-m", msg)
        tip = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "switch", "-q", "main")
        return tip

    def squash_merge(self, name, number, merged_at="2026-09-09T10:00:00Z"):
        """Squash NAME onto main like GitHub does, push, and record the PR row."""
        head = git(self.repo, "rev-parse", name)
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--squash", name)
        git(self.repo, "commit", "-q", "-m", "feat: %s (#%d)" % (name, number))
        merge = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "fetch", "-q", "origin")
        self.add_pr(number, name, head, merge, merged_at=merged_at)
        return head, merge

    def add_pr(self, number, head_ref, head_oid, merge_oid, base="main",
               merged_at="2026-09-09T10:00:00Z", newest=True):
        row = "\t".join([str(number), head_ref, head_oid, base, merge_oid, merged_at])
        if newest:
            self.pr_rows.insert(0, row)      # gh output is newest merge first
        else:
            self.pr_rows.append(row)
        with open(self.prs, "w") as fh:
            for r in self.pr_rows:
                fh.write(r + "\n")

    def processes(self, *procs):
        """Write the fake lsof snapshot: one (pid, command, cwd) per live process, in
        the ``-Fpcn`` record shape the scan parses (p, c, fcwd, n lines)."""
        with open(self.lsof_out, "w") as fh:
            for pid, cmd, cwd in procs:
                fh.write("p%s\nc%s\nfcwd\nn%s\n" % (pid, cmd, cwd))

    def scan(self, *flags, github=True, auth=0, list_rc=0, lsof_rc=0, path=None):
        """Run the scan over the sandbox root; return (rows-by-type, stderr, rc).

        PATH is the fake-tools dir (gh, lsof) ahead of the real PATH, or exactly
        ``path`` when given. A non-zero ``lsof_rc`` makes the fake lsof fail.
        """
        if not github:
            git(self.repo, "remote", "set-url", "origin", self.origin)
        env = dict(os.environ)
        env["PATH"] = path if path else self.bindir + os.pathsep + env.get("PATH", "")
        env["FAKE_GH_PRS"] = self.prs
        env["FAKE_GH_LOG"] = self.log
        env["FAKE_GH_AUTH"] = str(auth)
        env["FAKE_GH_LIST"] = str(list_rc)
        env["FAKE_LSOF_OUT"] = self.lsof_out
        env["FAKE_LSOF_LOG"] = self.lsof_log
        env["FAKE_LSOF_RC"] = str(lsof_rc)
        env.pop("DAILY_REPO_ROOTS", None)
        env.pop("DAILY_SCAN_DEPTH", None)
        p = subprocess.run(["bash", SCRIPT, *flags, self.root], capture_output=True,
                           text=True, env=env)
        rows = {}
        for line in p.stdout.splitlines():
            cols = line.split("\t")
            rows.setdefault(cols[0], []).append(cols)
        return rows, p.stderr, p.returncode

    def gh_calls(self):
        return logged_calls(self.log)

    def lsof_calls(self):
        return logged_calls(self.lsof_log)


def logged_calls(log):
    """The argv lines a fake tool appended to LOG, one per call."""
    if not os.path.exists(log):
        return []
    with open(log) as fh:
        return [ln for ln in fh.read().splitlines() if ln]


def branch_state(rows, name):
    for r in rows.get("BRANCH", []):
        if r[2] == name:
            return r[3]
    return None


def rbranch_state(rows, name):
    for r in rows.get("RBRANCH", []):
        if r[2] == name:
            return r[3]
    return None


def wt_row(rows, head_desc):
    for r in rows.get("WT", []):
        if r[3] == head_desc:
            return r
    return None


def summary(rows):
    line = rows["SUMMARY"][0]
    return dict(kv.split("=", 1) for kv in line[1:])


def minimal_tools(tmp):
    """A PATH dir holding every tool the scan needs and no gh or lsof at all.

    Dropping the directories that contain them would not do: on Linux /usr/bin holds
    bash, gh and lsof alike, and a real gh or lsof must not answer for a "not
    installed" run.
    """
    tools = os.path.join(tmp, "tools")
    os.makedirs(tools)
    for name in ("bash", "git", "sed", "tr", "find", "sort", "grep", "cut",
                 "du", "head", "python3"):
        real = shutil.which(name)
        if real:
            os.symlink(real, os.path.join(tools, name))
    return tools


class SweepScanBase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()


class MultiCommitSquashMerge(SweepScanBase):
    """The case that motivated the proof: 2+ commits squash-merged as one."""

    def setUp(self):
        super().setUp()
        self.head, self.merge = None, None
        self.sb.feature("feat/multi", commits=2, push=True)
        self.head, self.merge = self.sb.squash_merge("feat/multi", 7)

    def test_git_alone_reads_unique(self):
        rows, _, rc = self.sb.scan("--no-pr")
        self.assertEqual(rc, 0)
        self.assertEqual(branch_state(rows, "feat/multi"), "UNIQUE(2)")
        self.assertEqual(rbranch_state(rows, "feat/multi"), "UNIQUE(2)")
        s = summary(rows)
        self.assertEqual(s["pr-proof"], "off")
        self.assertEqual(s["stale-local-branches"], "0")
        self.assertEqual(s["pr-merged-local"], "0")
        self.assertEqual(self.sb.gh_calls(), [])

    def test_merged_pr_proves_local_and_remote(self):
        rows, _, rc = self.sb.scan()
        self.assertEqual(rc, 0)
        self.assertEqual(branch_state(rows, "feat/multi"), "PRMERGED(#7)")
        self.assertEqual(rbranch_state(rows, "feat/multi"), "PRMERGED(#7)")
        s = summary(rows)
        self.assertEqual(s["stale-local-branches"], "1")
        self.assertEqual(s["stale-remote-branches"], "1")
        self.assertEqual(s["pr-merged-local"], "1")
        self.assertEqual(s["pr-merged-remote"], "1")
        self.assertEqual(s["pr-proof"], "1/1")

    def test_one_gh_call_per_repo_with_the_documented_arguments(self):
        self.sb.scan()
        calls = self.sb.gh_calls()
        self.assertEqual(len(calls), 1, calls)
        for needle in ("pr list", "--repo github.com/acme/widgets", "--state merged",
                       "--base main", "--limit 500", "--json "):
            self.assertIn(needle, calls[0])

    def test_merges_from_main_after_the_pr_still_prove(self):
        git(self.sb.repo, "switch", "-q", "feat/multi")
        git(self.sb.repo, "merge", "-q", "--no-edit", "origin/main")
        git(self.sb.repo, "switch", "-q", "main")
        self.assertNotEqual(git(self.sb.repo, "rev-parse", "feat/multi"), self.head)
        rows, _, _ = self.sb.scan()
        self.assertEqual(branch_state(rows, "feat/multi"), "PRMERGED(#7)")

    def test_real_work_after_the_pr_stays_unique(self):
        self.sb.commit_on("feat/multi", "later.txt")
        rows, _, _ = self.sb.scan()
        self.assertEqual(branch_state(rows, "feat/multi"), "UNIQUE(3)")
        self.assertEqual(summary(rows)["pr-merged-local"], "0")

    def test_merge_then_real_work_stays_unique(self):
        git(self.sb.repo, "switch", "-q", "feat/multi")
        git(self.sb.repo, "merge", "-q", "--no-edit", "origin/main")
        git(self.sb.repo, "switch", "-q", "main")
        self.sb.commit_on("feat/multi", "later.txt")
        rows, _, _ = self.sb.scan()
        self.assertTrue(branch_state(rows, "feat/multi").startswith("UNIQUE("))

    def test_tip_behind_the_pr_head_proves(self):
        first = git(self.sb.repo, "rev-parse", "feat/multi~1")
        git(self.sb.repo, "branch", "-q", "-f", "feat/multi", first)
        rows, _, _ = self.sb.scan()
        self.assertEqual(branch_state(rows, "feat/multi"), "PRMERGED(#7)")

    def test_renamed_local_branch_matches_the_pr_by_commit(self):
        git(self.sb.repo, "branch", "-q", "feat/renamed", self.head)
        rows, _, _ = self.sb.scan()
        self.assertEqual(branch_state(rows, "feat/renamed"), "PRMERGED(#7)")

    def test_rebased_after_merge_stays_unique(self):
        # Rewriting the commits breaks the ancestry to the PR head: no proof.
        git(self.sb.repo, "switch", "-q", "feat/multi")
        git(self.sb.repo, "commit", "-q", "--amend", "--no-edit", "-m", "feat: reworded")
        git(self.sb.repo, "switch", "-q", "main")
        rows, _, _ = self.sb.scan()
        self.assertEqual(branch_state(rows, "feat/multi"), "UNIQUE(2)")

    def test_worktrees_at_the_pr_head_read_contained(self):
        detached = os.path.join(self.sb.tmp, "wt-detached")
        on_branch = os.path.join(self.sb.tmp, "wt-branch")
        git(self.sb.repo, "worktree", "add", "-q", "--detach", detached, self.head)
        git(self.sb.repo, "worktree", "add", "-q", on_branch, "feat/multi")
        rows, _, _ = self.sb.scan()
        det = wt_row(rows, "DETACHED@" + self.head[:7])
        self.assertIsNotNone(det, rows.get("WT"))
        self.assertEqual(det[4], "PRMERGED(#7)")
        br = wt_row(rows, "feat/multi")
        self.assertEqual(br[4], "PRMERGED(#7)")
        for r in rows["BRANCH"]:
            if r[2] == "feat/multi":
                self.assertEqual(r[5], "yes")   # checked out -> the skill skips it

    def test_parked_primary_on_the_merged_branch(self):
        git(self.sb.repo, "switch", "-q", "feat/multi")
        rows, _, _ = self.sb.scan()
        parked = rows["PARKED"][0]
        self.assertEqual(parked[2], "feat/multi")
        self.assertEqual(parked[3], "PRMERGED(#7)")
        git(self.sb.repo, "switch", "-q", "main")

    def test_a_newer_failing_candidate_does_not_hide_an_older_proof(self):
        # The name was reused: PR #9 (newest) is unrelated work under the same
        # head ref; PR #7 is the one that merged this tip.
        other = self.sb.feature("feat/other", commits=1, push=False)
        _, merge9 = self.sb.squash_merge("feat/other", 9, merged_at="2026-09-09T12:00:00Z")
        self.sb.pr_rows = []
        self.sb.add_pr(9, "feat/multi", other, merge9, merged_at="2026-09-09T12:00:00Z")
        self.sb.add_pr(7, "feat/multi", self.head, self.merge, newest=False)
        rows, _, _ = self.sb.scan()
        self.assertEqual(branch_state(rows, "feat/multi"), "PRMERGED(#7)")


class NoProofWithoutEvidence(SweepScanBase):
    """Every way the PR lookup can be wrong or unavailable must leave UNIQUE."""

    def setUp(self):
        super().setUp()
        self.sb.feature("feat/multi", commits=2, push=True)
        self.head, self.merge = self.sb.squash_merge("feat/multi", 7)

    def _unique(self, rows):
        self.assertEqual(branch_state(rows, "feat/multi"), "UNIQUE(2)")
        self.assertEqual(rbranch_state(rows, "feat/multi"), "UNIQUE(2)")
        self.assertEqual(summary(rows)["pr-merged-local"], "0")

    def test_merge_commit_not_on_the_default_branch(self):
        # A merge commit that exists but never reached origin/main: the PR may be
        # merged on GitHub, but local refs cannot confirm it -> conservative.
        stray = self.sb.feature("feat/stray", commits=1)
        self.sb.pr_rows = []
        self.sb.add_pr(7, "feat/multi", self.head, stray)
        rows, _, _ = self.sb.scan()
        self._unique(rows)

    def test_unknown_merge_commit(self):
        self.sb.pr_rows = []
        self.sb.add_pr(7, "feat/multi", self.head, "0" * 40)
        rows, _, _ = self.sb.scan()
        self._unique(rows)

    def test_missing_merge_commit(self):
        self.sb.pr_rows = []
        self.sb.add_pr(7, "feat/multi", self.head, "-")
        rows, _, _ = self.sb.scan()
        self._unique(rows)

    def test_pr_into_another_base(self):
        self.sb.pr_rows = []
        self.sb.add_pr(7, "feat/multi", self.head, self.merge, base="develop")
        rows, _, _ = self.sb.scan()
        self._unique(rows)

    def test_non_github_remote_skips_gh(self):
        rows, _, rc = self.sb.scan(github=False)
        self.assertEqual(rc, 0)
        self._unique(rows)
        self.assertEqual(summary(rows)["pr-proof"], "0/0")
        self.assertEqual(self.sb.gh_calls(), [])

    def test_no_token_for_the_host(self):
        rows, err, rc = self.sb.scan(auth=1)
        self.assertEqual(rc, 0)
        self._unique(rows)
        self.assertEqual(summary(rows)["pr-proof"], "0/1")
        self.assertEqual(self.sb.gh_calls(), [])
        self.assertIn("no token", err)

    def test_failed_list_call_is_best_effort(self):
        rows, err, rc = self.sb.scan(list_rc=1)
        self.assertEqual(rc, 0)
        self._unique(rows)
        self.assertEqual(summary(rows)["pr-proof"], "0/1")
        self.assertIn("gh pr list failed", err)

    def test_no_gh_on_path(self):
        rows, err, rc = self.sb.scan(path=minimal_tools(self.sb.tmp))
        self.assertEqual(rc, 0)
        self._unique(rows)
        self.assertEqual(summary(rows)["pr-proof"], "off")
        self.assertIn("gh not installed", err)


class GitOnlyProofsUnchanged(SweepScanBase):
    """MERGED and EQUIV keep their meaning; the PR proof only adds a third."""

    def test_ancestor_is_merged_and_single_squash_is_equiv(self):
        anc = self.sb.feature("feat/ancestor", commits=1)
        git(self.sb.repo, "merge", "-q", "--ff-only", "feat/ancestor")
        git(self.sb.repo, "push", "-q", "origin", "main")
        git(self.sb.repo, "fetch", "-q", "origin")
        self.sb.feature("feat/single", commits=1, push=True)
        self.sb.squash_merge("feat/single", 8)
        rows, _, _ = self.sb.scan("--no-pr")
        self.assertEqual(branch_state(rows, "feat/ancestor"), "MERGED")
        self.assertEqual(branch_state(rows, "feat/single"), "EQUIV")
        self.assertEqual(rbranch_state(rows, "feat/single"), "EQUIV")
        self.assertTrue(branch_state(rows, "main").startswith("DEFAULT("))
        self.assertEqual(git(self.sb.repo, "rev-parse", "feat/ancestor"), anc)
        s = summary(rows)
        self.assertEqual(s["stale-local-branches"], "2")
        self.assertEqual(s["stale-remote-branches"], "1")

    def test_equiv_worktree_reads_contained_equiv(self):
        head = self.sb.feature("feat/single", commits=1)
        self.sb.squash_merge("feat/single", 8)
        wt = os.path.join(self.sb.tmp, "wt-equiv")
        git(self.sb.repo, "worktree", "add", "-q", "--detach", wt, head)
        rows, _, _ = self.sb.scan("--no-pr")
        row = wt_row(rows, "DETACHED@" + head[:7])
        self.assertEqual(row[4], "EQUIV")

    def test_unique_worktree_reads_no(self):
        head = self.sb.feature("feat/open", commits=1)
        wt = os.path.join(self.sb.tmp, "wt-open")
        git(self.sb.repo, "worktree", "add", "-q", "--detach", wt, head)
        rows, _, _ = self.sb.scan("--no-pr")
        row = wt_row(rows, "DETACHED@" + head[:7])
        self.assertEqual(row[4], "no")


class InUseProbe(SweepScanBase):
    """A checkout some live process is standing in is flagged -- never guessed."""

    def setUp(self):
        super().setUp()
        self.sb.feature("feat/live", commits=1)
        self.sb.feature("feat/idle", commits=1)
        self.live = os.path.join(self.sb.tmp, "wt-live")
        self.idle = os.path.join(self.sb.tmp, "wt-idle")
        git(self.sb.repo, "worktree", "add", "-q", self.live, "feat/live")
        git(self.sb.repo, "worktree", "add", "-q", self.idle, "feat/idle")
        self.real = os.path.realpath(self.live)   # what lsof prints: the resolved path

    def test_a_process_standing_in_a_worktree_reads_in_use(self):
        deep = os.path.join(self.real, "src", "deep")
        self.sb.processes((4242, "zsh", self.real), (4243, "node", deep),
                          (4244, "zsh", self.real + "-other"),          # same prefix
                          (4245, "bash", os.path.dirname(self.real)))   # the parent
        rows, err, rc = self.sb.scan()
        self.assertEqual(rc, 0)
        live = wt_row(rows, "feat/live")
        self.assertEqual(live[7], "yes")
        self.assertEqual(wt_row(rows, "feat/idle")[7], "no")
        hits = sorted((r[3], r[4], r[5]) for r in rows["INUSE"] if r[2] == live[2])
        self.assertEqual(hits, [("4242", "zsh", self.real), ("4243", "node", deep)])
        self.assertEqual(len(rows["INUSE"]), 2)
        self.assertEqual(summary(rows)["in-use"], "1")
        self.assertIn("in-use probe via lsof: on", err)

    def test_matching_ignores_letter_case_and_keeps_the_command(self):
        self.sb.processes((7, "Claude Helper", self.real.upper()))
        rows, _, _ = self.sb.scan()
        self.assertEqual(wt_row(rows, "feat/live")[7], "yes")
        self.assertEqual(rows["INUSE"][0][3:5], ["7", "Claude Helper"])

    def test_parked_primary_and_orphan_dir_carry_the_column(self):
        self.sb.feature("feat/parked", commits=1)
        git(self.sb.repo, "switch", "-q", "feat/parked")
        repo = os.path.realpath(self.sb.repo)
        dead = os.path.join(repo, ".claude", "worktrees", "dead")
        os.makedirs(dead)
        with open(os.path.join(dead, ".git"), "w") as fh:
            fh.write("gitdir: %s\n" % os.path.join(self.sb.tmp, "gone", ".git",
                                                   "worktrees", "dead"))
        self.sb.processes((11, "claude", repo), (12, "zsh", os.path.join(dead, "sub")))
        rows, _, _ = self.sb.scan()
        parked = rows["PARKED"][0]
        self.assertEqual(parked[2], "feat/parked")
        self.assertEqual(parked[6], "yes")
        orphan = rows["ORPHAN"][0]
        self.assertEqual(orphan[4], "no")      # not repairable
        self.assertEqual(orphan[7], "yes")
        by_path = {}
        for r in rows["INUSE"]:
            by_path.setdefault(r[2], []).append(r[3])
        self.assertEqual(sorted(by_path[parked[1]]), ["11", "12"])   # orphan sits inside
        self.assertEqual(by_path[orphan[2]], ["12"])
        self.assertEqual(wt_row(rows, "feat/live")[7], "no")
        self.assertEqual(summary(rows)["in-use"], "2")

    def test_a_failing_lsof_reads_unknown(self):
        self.sb.processes((4242, "zsh", self.real))
        rows, err, rc = self.sb.scan(lsof_rc=1)
        self.assertEqual(rc, 0)
        self.assertEqual(wt_row(rows, "feat/live")[7], "?")
        self.assertEqual(wt_row(rows, "feat/idle")[7], "?")
        self.assertNotIn("INUSE", rows)
        self.assertEqual(summary(rows)["in-use"], "?")
        self.assertIn("lsof failed", err)

    def test_no_lsof_on_path_reads_unknown(self):
        rows, err, rc = self.sb.scan(path=minimal_tools(self.sb.tmp))
        self.assertEqual(rc, 0)
        self.assertEqual(wt_row(rows, "feat/live")[7], "?")
        self.assertEqual(summary(rows)["in-use"], "?")
        self.assertIn("lsof not installed", err)

    def test_one_lsof_call_per_run_with_the_documented_arguments(self):
        self.sb.scan()
        calls = self.sb.lsof_calls()
        self.assertEqual(len(calls), 1, calls)
        for needle in ("-a", "-d cwd", "-Fpcn"):
            self.assertIn(needle, calls[0])


class Help(unittest.TestCase):
    def test_help_documents_the_new_state_and_columns(self):
        p = subprocess.run(["bash", SCRIPT, "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        for needle in ("PRMERGED(#N)", "--no-pr", "RBRANCH REPO NAME STATE LASTCOMMIT",
                       "pr-merged-local", "pr-proof", "--limit 500"):
            self.assertIn(needle, p.stdout)

    def test_help_documents_the_in_use_probe(self):
        p = subprocess.run(["bash", SCRIPT, "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        for needle in ("lsof", "WT REPO PATH HEAD CONTAINED DIRTY PRUNABLE INUSE",
                       "INUSE REPO PATH PID COMMAND CWD",
                       "ORPHAN REPO PATH GITDIR_TARGET REPAIRABLE SIZE_KB FILES INUSE",
                       "PARKED REPO CURRENT_BRANCH STATE DEFAULT DEFAULT_BEHIND INUSE",
                       "in-use"):
            self.assertIn(needle, p.stdout)


if __name__ == "__main__":
    unittest.main()
