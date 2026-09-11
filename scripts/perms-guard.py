#!/usr/bin/env python3
"""perms-guard — PreToolUse(Bash) hook logic.

Input: the hook JSON on stdin (key tool_input.command).
Work: splits the command into sub-commands (respecting quotes and &&/;/|), and blocks
the destructive patterns in yar's deny policy:
  • rm with BOTH recursive and force flags (rm -rf / -fr / -Rf / -r -f / --recursive --force),
    including a leading `sudo` (sudo rm -rf ...).
  • docker rm / docker container rm with a force flag (-f / --force).
A match is blocked with exit 2 (the message goes back to Claude on stderr).

This is the always-on, plugin-shipped backstop for the same deny rules that
`/yar:install-perms` writes into a repo's settings.json. Unlike a settings `deny`,
this hook fires for every project the plugin is enabled in, with no per-repo install.

Philosophy: fail-open. Anything we're not sure about → exit 0 (allow), so legitimate
work is never blocked. Only explicit destructive patterns are blocked.
Deliberate bypass (rare): PERMS_GUARD=off
"""
import sys
import json
import shlex
import re
import os


def fail_open():
    sys.exit(0)


def split_segments(s):
    """Split the command on ; \\n | & and && ||, respecting quotes."""
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


# Fallbacks (only when shlex fails on a segment). Deliberately loose but conservative.
RM_FALLBACK = re.compile(r'\brm\s+-[A-Za-z]*(?:[rR][A-Za-z]*f|f[A-Za-z]*[rR])')
DOCKER_FALLBACK = re.compile(r'\bdocker\b[^|;&\n]*\brm\b[^|;&\n]*(?:-[A-Za-z]*f|--force)')

# Global options that consume the NEXT token as their value (so we skip past it
# when scanning for the real sub-command).
SUDO_VALUE_OPTS = {"-u", "--user", "-g", "--group", "-p", "--prompt"}
DOCKER_VALUE_OPTS = {
    "-H", "--host", "-c", "--context", "--config", "-l", "--log-level",
    "--tlscacert", "--tlscert", "--tlskey",
}


def base(tok):
    return tok.rsplit('/', 1)[-1]


def has_force(toks):
    """True if any token is a force flag (-f / --force / a combined short flag with f)."""
    for t in toks:
        if t == "--force" or t.startswith("--force="):
            return True
        if t.startswith('-') and not t.startswith('--') and t != '-':
            if 'f' in t[1:]:
                return True
    return False


def strip_leading(toks, value_opts):
    """Skip leading option tokens (and the values of value-taking options); return the rest."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in value_opts:
            i += 2
            continue
        if t.startswith('-') and t != '-':
            i += 1
            continue
        break
    return toks[i:]


def rm_reason(toks):
    """If these tokens are an unsafe `rm` (recursive AND force), return the block reason."""
    if not toks or base(toks[0]) != 'rm':
        return None
    recursive = force = False
    for t in toks[1:]:
        if t == '--':            # end of options; the rest are paths
            break
        if t == '--recursive':
            recursive = True
        elif t == '--force':
            force = True
        elif t.startswith('-') and not t.startswith('--') and t != '-':
            letters = t[1:]
            if 'r' in letters or 'R' in letters:
                recursive = True
            if 'f' in letters:
                force = True
    if recursive and force:
        return "rm -rf"
    return None


def docker_reason(toks):
    """If these tokens are `docker rm -f` / `docker container rm -f`, return the reason."""
    if not toks or base(toks[0]) != 'docker':
        return None
    rest = strip_leading(toks[1:], DOCKER_VALUE_OPTS)  # skip docker's global options
    if not rest:
        return None
    sub = rest[0]
    if sub == 'rm':
        return "docker rm -f" if has_force(rest[1:]) else None
    if sub == 'container':
        after = strip_leading(rest[1:], set())
        if after and after[0] == 'rm':
            return "docker container rm -f" if has_force(after[1:]) else None
    return None


def reason_for_segment(seg):
    """Tokenize one segment and return a block reason, or None."""
    try:
        toks = shlex.split(seg, posix=True)
    except Exception:
        if RM_FALLBACK.search(seg) or DOCKER_FALLBACK.search(seg):
            return "destructive command"
        return None
    if not toks:
        return None
    if base(toks[0]) == 'sudo':                       # unwrap a leading sudo
        toks = strip_leading(toks[1:], SUDO_VALUE_OPTS)
        if not toks:
            return None
    return rm_reason(toks) or docker_reason(toks)


def main():
    if os.environ.get("PERMS_GUARD") == "off":
        fail_open()
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
        r = reason_for_segment(seg)
        if r:
            reason = r
            break

    if reason:
        sys.stderr.write(
            "⛔ perms-guard: «{}» blocked.\n".format(reason)
            + "   Why: this matches yar's destructive-command deny policy "
              "(force-recursive delete / force container removal).\n"
            + "   Instead: delete explicit, intended paths — or run it yourself in a terminal.\n"
            + "   Deliberate bypass (rare): PERMS_GUARD=off <command>\n"
            + "   — blocked by perms-guard (PreToolUse): no force-recursive deletes.\n"
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
