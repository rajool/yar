#!/usr/bin/env python3
"""git-guard — PreToolUse(Bash) hook logic.

Input: the hook JSON on stdin (key tool_input.command).
Work: splits the command into sub-commands (respecting quotes and &&/;/|), and if it sees a
git add with a bulk/force flag (-A/--all/-u/-f) or the "." path, or git commit -a,
it blocks it with exit 2 (the message goes back to Claude on stderr).

Philosophy: fail-open. Anything we're not sure about → exit 0 (allow), so that legitimate
or non-git work is never blocked. The only thing blocked is explicit unsafe patterns.
"""
import sys
import json
import shlex
import re


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


def base(tok):
    return tok.rsplit('/', 1)[-1]


def git_reason(toks):
    """If these tokens are an unsafe git add/commit, return the block reason; otherwise None."""
    if not toks or base(toks[0]) != 'git':
        return None
    # Skip git's global options until we reach the sub-command (git -C <path>, -c k=v, …)
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


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        fail_open()
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        fail_open()

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
            continue
        r = git_reason(toks)
        if r:
            reason = r
            break

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
