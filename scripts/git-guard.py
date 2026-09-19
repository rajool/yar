#!/usr/bin/env python3
"""git-guard — PreToolUse(Bash) hook logic.

Input: the hook JSON on stdin (key tool_input.command).
Work: splits the command into sub-commands (respecting quotes and &&/;/|), and if it sees a
git add with a bulk/force flag (-A/--all/-u/-f) or the "." path, or git commit -a,
it blocks it with exit 2 (the message goes back to Claude on stderr).

It also gates remote-branch deletion on the pull request being merged: ``git push
<remote> --delete <branch>`` (or ``-d``, or the ``:<branch>`` refspec) is blocked when
it is chained in the same command as ``gh pr merge`` -- if the merge fails (conflict,
pending checks) the delete still runs and GitHub closes the open PR unmerged -- and,
standing alone, when ``gh pr view <branch>`` says the PR is still OPEN. MERGED, CLOSED,
no PR, or an unreachable gh -> allowed.

Philosophy: fail-open. Anything we're not sure about → exit 0 (allow), so that legitimate
or non-git work is never blocked. The only thing blocked is explicit unsafe patterns.
"""
import sys
import os
import json
import shlex
import re
import subprocess


def fail_open():
    sys.exit(0)


def split_segments(s):
    """Split the command on ; \n | & and && ||, respecting quotes."""
    segs, buf = [], []
    i, n, quote = 0, len(s), None
    while i < n:
        c = s[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            buf.append(c)
            i += 1
            continue
        if c == '\\' and i + 1 < n:
            buf.append(c)
            buf.append(s[i + 1])
            i += 2
            continue
        if c in (';', '\n', '&', '|'):
            segs.append(''.join(buf))
            buf = []
            if c in ('&', '|') and i + 1 < n and s[i + 1] == c:
                i += 2
            else:
                i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        segs.append(''.join(buf))
    return segs


# Fallback (only when shlex fails on a segment):
DANGER_RE = re.compile(
    r'\bgit\b[^|;&\n]*\badd\b[^|;&\n]*'
    r'(?:(?<![\w-])(?:-A|--all|-u|--update|-f|--force)(?![\w-])|(?:\s|^)\.(?:\s|/|$))'
)
COMMIT_A_RE = re.compile(
    r'\bgit\b[^|;&\n]*\bcommit\b[^|;&\n]*(?<![\w-])(?:-a\w*|--all)(?![\w-])'
)
MERGE_RE = re.compile(r'\bgh\s+pr\s+merge\b')
# Fallback for the deletion gate (only when shlex fails on a segment):
PUSH_DELETE_RE = re.compile(
    r'\bgit\b[^|;&\n]*\bpush\b[^|;&\n]*(?:(?<![\w-])(?:--delete|-d)(?![\w-])|\s:[^\s:]+)'
)
GH_TIMEOUT = 8


def base(tok):
    return tok.rsplit('/', 1)[-1]


def subcommand_index(toks):
    """Index of git's sub-command, skipping global options (git -C <path>, -c k=v, …);
    len(toks) when there is none."""
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in ('-C', '--git-dir', '--work-tree', '--namespace', '-c', '--exec-path'):
            i += 2
            continue
        if t.startswith('-'):
            i += 1
            continue
        break
    return i


def push_delete_target(toks):
    """If these tokens delete a remote branch -- ``git push [remote] --delete|-d <branch>``
    or ``git push <remote> :<branch>`` -- return the branch name; otherwise None."""
    if not toks or base(toks[0]) != 'git':
        return None
    i = subcommand_index(toks)
    if i >= len(toks) or toks[i] != 'push':
        return None
    delete, positional = False, []
    for r in toks[i + 1:]:
        if r in ('--delete', '-d'):
            delete = True
        elif r.startswith('-'):
            continue
        else:
            positional.append(r)
    if delete:
        # git push [<remote>] --delete <branch>: the branch is the positional after the remote
        if len(positional) >= 2:
            return positional[1]
        return positional[0] if positional else '<branch>'
    for p in positional[1:]:
        if p.startswith(':') and len(p) > 1:
            return p[1:]
    return None


def pr_state(branch, cwd=None):
    """(state, number) of the pull request whose head is ``branch``, via gh.
    ("NONE", None) when there is no PR; (None, None) when unknown (no gh, offline)."""
    env = dict(os.environ)
    env.update({"GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1"})
    try:
        p = subprocess.run(["gh", "pr", "view", branch, "--json", "state,number"],
                           cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
                           capture_output=True, text=True, timeout=GH_TIMEOUT, env=env)
    except Exception:
        return None, None
    if p.returncode != 0:
        low = (p.stderr or '').lower()
        if 'no pull requests found' in low or 'could not resolve' in low:
            return 'NONE', None
        return None, None
    try:
        d = json.loads(p.stdout)
        return d.get('state'), d.get('number')
    except Exception:
        return None, None


def git_reason(toks):
    """If these tokens are an unsafe git add/commit, return the block reason; otherwise None."""
    if not toks or base(toks[0]) != 'git':
        return None
    i = subcommand_index(toks)
    if i >= len(toks):
        return None
    sub = toks[i]
    rest = toks[i + 1:]
    if sub == 'add':
        for r in rest:
            if r in ('-A', '--all', '-u', '--update', '-f', '--force'):
                return "git add {}".format(r)
            if r.startswith('-') and not r.startswith('--') and re.search('[Auf]', r):
                return "git add {}".format(r)
        for r in rest:
            if r in ('.', './', '*', ':/', ':/.'):
                return "git add ."
        return None
    if sub == 'commit':
        # Options that consume the NEXT token as their value. We skip that value so a
        # message like  -m "- add a thing"  (starts with '-', contains 'a') is never
        # mistaken for the -a flag — a fail-open guard must not block a real commit.
        value_opts = {
            '-m', '--message', '-F', '--file', '-C', '--reuse-message',
            '-c', '--reedit-message', '-t', '--template', '--author', '--date',
            '--cleanup', '--pathspec-from-file', '--fixup', '--squash', '--trailer',
        }
        j = 0
        while j < len(rest):
            r = rest[j]
            if r in value_opts:
                j += 2  # skip the option and its value
                continue
            if r in ('-a', '--all'):
                return "git commit -a"
            if r.startswith('-') and not r.startswith('--') and 'a' in r:
                return "git commit {}".format(r)
            j += 1
        return None
    return None


def block_delete(kind, branch, number):
    """Refuse a remote-branch deletion (exit 2) with the reason and the safe sequence."""
    n = str(number) if number else "<N>"
    if kind == "chain":
        head = ("⛔ git-guard: «git push --delete {b}» chained to «gh pr merge» blocked.\n"
                "   Why: if the merge does not go through (conflict, pending checks), the delete still "
                "runs and GitHub closes the open PR unmerged — the branch is gone, the work is not on main.\n"
                ).format(b=branch)
    else:
        head = ("⛔ git-guard: «git push --delete {b}» blocked — PR #{n} for {b} is still OPEN.\n"
                "   Why: deleting the head branch of an open PR closes it unmerged (GitHub does that by "
                "itself); the work never reaches main.\n").format(b=branch, n=n)
    sys.stderr.write(
        head
        + "   Instead: run the merge on its own (gh pr merge {n} --squash), then in a SEPARATE command:\n"
          "     gh pr view {n} --json state --jq .state     -> must print MERGED\n"
          "     git push origin --delete {b}\n"
          "   Deliberate bypass (rare): GIT_GUARD=off <command>\n"
          "   — blocked by git-guard (PreToolUse). Delete a branch only after its PR is MERGED.\n"
          .format(n=n, b=branch)
    )
    sys.exit(2)


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        fail_open()
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        fail_open()

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    merge_in_chain = MERGE_RE.search(cmd) is not None

    reason = None
    for seg in split_segments(cmd):
        if not seg.strip():
            continue
        try:
            toks = shlex.split(seg, posix=True)
        except Exception:
            if DANGER_RE.search(seg) or COMMIT_A_RE.search(seg):
                reason = "unsafe staging pattern"
                break
            if merge_in_chain and PUSH_DELETE_RE.search(seg):
                block_delete("chain", "<branch>", None)
            continue
        r = git_reason(toks)
        if r:
            reason = r
            break
        branch = push_delete_target(toks)
        if branch:
            if merge_in_chain:
                block_delete("chain", branch, None)
            state, number = pr_state(branch, cwd)
            if state == "OPEN":
                block_delete("open", branch, number)

    if reason:
        sys.stderr.write(
            "⛔ git-guard: «{}» blocked.\n".format(reason)
            + "   Why: bulk/force staging may pull in a binary, a secret, or files from other sessions.\n"
            + "   Instead: git add <explicit path> …  (only the files for this task).\n"
            + "   Deliberate bypass (rare): GIT_GUARD=off <command>\n"
            + "   — blocked by git-guard (PreToolUse). Stage explicit paths; no bulk/force add.\n"
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
