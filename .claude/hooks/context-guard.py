#!/usr/bin/env python3
# context-guard - keep the yar repo generic and public: no private/context-specific content.
#
# Two modes:
#   1. Hook mode (no CLI args): reads a PreToolUse hook JSON on stdin and blocks an
#      Edit/Write whose new content or filename carries private context. exit 2 = block.
#   2. Scan mode (--all | --scan FILE...): scans repo files as a pre-merge gate (used by
#      .github/workflows/no-context.yml), prints a report, exit 1 if anything is found.
#
# What counts as "context" (private / non-generic), detected generically:
#   - real email addresses (placeholders like you@example.com are fine)
#   - absolute home paths (/Users/<name>/, /home/<name>/) with a real user name
#   - embedded secrets (PEM private keys; GitHub/AWS/Google/Slack/Anthropic/Stripe tokens)
#   - any term in an optional, gitignored .claude/hooks/context-denylist.local.txt
#
# Escape hatches (so whoever is merging can continue):
#   - a genuine false positive (a placeholder that looks real): put "context-guard:allow"
#     on that line and it is skipped.
#   - a recurring private term to block repo-wide: add it to the local (gitignored) denylist.
#   - local one-off for the Claude hook only: CONTEXT_GUARD=off. The CI scan has NO env
#     bypass on purpose -- it is the merge gate.
#
# This file (and the .sh wrapper and the workflow yml) are self-skipped by the scanner so
# their own example patterns never trip it. Hook mode fails open: any error -> allow.
import json
import os
import re
import subprocess
import sys

SELF_SKIP = {"context-guard.py", "context-guard.sh", "no-context.yml"}
ALLOW_MARK = "context-guard:" "allow"  # split so this line does not self-exempt

PLACEHOLDER_EMAIL_LOCAL = {
    "you", "user", "username", "name", "email", "your", "yourname", "me",
    "someone", "first.last", "firstname.lastname", "your-email", "youremail",
}
PLACEHOLDER_EMAIL_DOMAINS = (
    "example.com", "example.org", "example.net", "domain.com", "email.com",
    "test.com", "company.com", "yourcompany.com", "acme.com",
)
PLACEHOLDER_NAMES = {
    "you", "user", "username", "name", "me", "yourname", "your-name", "youruser",
    "someone", "home", "<user>", "<you>", "<name>",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HOME_RES = [
    re.compile(r"/Users/([A-Za-z0-9._\-]+)"),
    re.compile(r"/home/([A-Za-z0-9._\-]+)"),
    re.compile(r"[Cc]:\\\\Users\\\\([A-Za-z0-9._\-]+)"),
]
PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
TOKEN_RES = [
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("github-pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("aws-key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("google-key", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("slack-token", re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("anthropic-key", re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}")),
    ("stripe-key", re.compile(r"(?:sk|pk)_(?:live|test)_[0-9A-Za-z]{16,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
]


def _load_denylist():
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        "context-denylist.local.txt")
    terms = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                t = line.strip()
                if t and not t.startswith("#"):
                    terms.append(t)
    except Exception:
        pass
    return terms


DENY_TERMS = _load_denylist()


def findings_in_line(line):
    """Return [(kind, snippet), ...] for one line, honoring the inline allow marker."""
    if ALLOW_MARK in line:
        return []
    out = []
    for m in EMAIL_RE.finditer(line):
        email = m.group(0)
        local, _, domain = email.partition("@")
        if local.lower() in PLACEHOLDER_EMAIL_LOCAL:
            continue
        if domain.lower().endswith(PLACEHOLDER_EMAIL_DOMAINS):
            continue
        out.append(("email", email))
    for rx in HOME_RES:
        for m in rx.finditer(line):
            who = m.group(1)
            if who.lower() in PLACEHOLDER_NAMES or who.startswith(("<", "$")):
                continue
            out.append(("home-path", m.group(0)))
    if PEM_RE.search(line):
        out.append(("private-key", "-----BEGIN ... PRIVATE KEY-----"))
    for kind, rx in TOKEN_RES:
        m = rx.search(line)
        if m:
            tok = m.group(0)
            out.append((kind, "{}...({} chars)".format(tok[:6], len(tok))))
    low = line.lower()
    for term in DENY_TERMS:
        if term.lower() in low:
            out.append(("denylisted-term", term))
    return out


def scan_text(text):
    """Return [(line_no, kind, snippet), ...] for a blob of text."""
    res = []
    for i, line in enumerate(text.splitlines() or [text], 1):
        for kind, snip in findings_in_line(line):
            res.append((i, kind, snip))
    return res


HELP = (
    "\ncontext-guard: the yar repo is PUBLIC and must stay GENERIC -- no personal\n"
    "emails, home paths, secrets, or references to private/internal systems.\n"
    "\n"
    "How to continue:\n"
    "  - Real context (an email, a path, a secret, a private name)? Remove or\n"
    "    generalize it (use a placeholder: /Users/you/..., you@example.com).\n"
    "  - Genuine false positive (a placeholder that looks real)? Put the marker\n"
    "    'context-guard:" "allow' on that line.\n"
    "  - Recurring private term to block repo-wide? Add it to the gitignored\n"
    "    .claude/hooks/context-denylist.local.txt (never committed).\n"
    "Then re-run / re-push. (Local hook one-off bypass: CONTEXT_GUARD=off --\n"
    "the CI merge gate has no bypass.)\n"
)


# ---- repo-scope helper (hook mode) -------------------------------------------------

def find_repo_root(path):
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return os.path.realpath(env)
    start = path if path else os.getcwd()
    d = os.path.dirname(os.path.realpath(start)) or "."
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    try:
        out = subprocess.check_output(
            ["git", "-C", d, "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL)
        return os.path.realpath(out.decode().strip())
    except Exception:
        return None


# ---- mode 1: PreToolUse hook -------------------------------------------------------

def hook_mode():
    if os.environ.get("CONTEXT_GUARD") == "off":
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    ti = (data or {}).get("tool_input", {}) or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    base = os.path.basename(path) if isinstance(path, str) else ""
    if base in SELF_SKIP:
        sys.exit(0)
    root = find_repo_root(path)
    if path and root:
        ap = os.path.realpath(path)
        if not (ap == root or ap.startswith(root + os.sep)):
            sys.exit(0)

    blobs = []
    if base:
        blobs.append(("filename", base))
    for key in ("content", "new_string", "new_source"):
        v = ti.get(key)
        if isinstance(v, str) and v:
            blobs.append((key, v))
    edits = ti.get("edits")
    if isinstance(edits, list):
        for idx, e in enumerate(edits):
            if isinstance(e, dict):
                v = e.get("new_string") or e.get("new_source")
                if isinstance(v, str) and v:
                    blobs.append(("edits[{}]".format(idx), v))

    for label, text in blobs:
        hits = scan_text(text)
        if hits:
            sys.stderr.write("context-guard: private/context-specific content in `{}`.\n".format(label))
            if path:
                sys.stderr.write("   File: {}\n".format(path))
            for _, kind, snip in hits[:8]:
                sys.stderr.write("   - {}: {}\n".format(kind, snip))
            sys.stderr.write(HELP)
            sys.stderr.write("   -- blocked by context-guard (PreToolUse): keep yar generic.\n")
            sys.exit(2)
    sys.exit(0)


# ---- mode 2: CLI scan (CI merge gate) ----------------------------------------------

def list_tracked():
    try:
        out = subprocess.check_output(["git", "ls-files", "-z"], stderr=subprocess.DEVNULL)
        return [f for f in out.decode("utf-8", "replace").split("\0") if f]
    except Exception:
        return []


def scan_mode(files):
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    total = 0
    for f in files:
        if os.path.basename(f) in SELF_SKIP:
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            continue  # binary / unreadable -> skip
        for line_no, kind, snip in scan_text(text):
            total += 1
            print("  {}:{}: {} -> {}".format(f, line_no, kind, snip))
            if in_ci:
                print("::error file={},line={}::context-guard: {} ({}). Remove it -- "
                      "the yar repo must stay generic/public.".format(f, line_no, kind, snip))
    if total:
        sys.stdout.write(HELP)
        print("context-guard: {} item(s) of private/context-specific content found. "
              "Merge blocked.".format(total))
        sys.exit(1)
    print("context-guard: clean -- no private/context-specific content found.")
    sys.exit(0)


def main():
    args = sys.argv[1:]
    if "--all" in args:
        scan_mode(list_tracked())
    elif "--scan" in args:
        scan_mode(args[args.index("--scan") + 1:])
    else:
        hook_mode()


if __name__ == "__main__":
    main()
