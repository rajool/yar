#!/usr/bin/env python3
# english-guard - PreToolUse(Edit|Write|NotebookEdit|MultiEdit) hook logic.
#
# Policy: the yar repo is English-only. All source, docs, comments, and filenames
# must be in English. This guard blocks any Write/Edit whose new content (or target
# filename) contains a non-Latin writing system (Arabic/Persian, Hebrew, Cyrillic,
# CJK, Hangul, Devanagari, Thai). The stderr message goes back to Claude, which then
# rewrites the content in English -- i.e. the hook turns non-English into English.
#
# Scope: only files INSIDE this repo. Writing a genuinely non-English file elsewhere
# (e.g. /tmp, ~/.claude, a Persian document the user asked for) is allowed.
# Detection deliberately ignores accented Latin (cafe, naive), Greek letters
# (math symbols like mu, pi), emoji, arrows, box-drawing, and smart quotes, so it
# only fires on actual foreign-language text, never on legitimate symbols.
#
# The script range table uses hex codepoints + chr() so this file stays pure ASCII
# and the guard never flags its own source.
#
# exit 2 = block (stderr -> Claude). exit 0 = allow.
# fail-open: any error / undetermined input -> exit 0 (never block legitimate work).
# Rare deliberate bypass: ENGLISH_GUARD=off
import json
import os
import re
import subprocess
import sys


def allow():
    sys.exit(0)


if os.environ.get("ENGLISH_GUARD") == "off":
    allow()

try:
    data = json.load(sys.stdin)
except Exception:
    allow()

tool_input = (data or {}).get("tool_input", {}) or {}

# (start, end) codepoints of non-Latin LETTER scripts to block.
# Excluded on purpose: Greek (math symbols mu/pi), Latin Extended (accented Latin
# like cafe/naive), and all symbols/emoji/punctuation -- so the guard only fires on
# real foreign-language text.
_RANGES = [
    (0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),  # Arabic / Persian
    (0xFB50, 0xFDFF), (0xFE70, 0xFEFF),                    # Arabic presentation forms
    (0x0590, 0x05FF),                                      # Hebrew
    (0x0400, 0x052F),                                      # Cyrillic
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF),                    # CJK (Han)
    (0x3040, 0x30FF),                                      # Hiragana + Katakana
    (0xAC00, 0xD7AF),                                      # Hangul
    (0x0900, 0x097F),                                      # Devanagari
    (0x0E00, 0x0E7F),                                      # Thai
]
NON_LATIN = re.compile(
    "[" + "".join("{}-{}".format(chr(a), chr(b)) for a, b in _RANGES) + "]"
)


def find_repo_root(path):
    """Best-effort repo root: $CLAUDE_PROJECT_DIR, else `git rev-parse` from the file."""
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
            ["git", "-C", d, "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        )
        return os.path.realpath(out.decode().strip())
    except Exception:
        return None


def candidates(ti):
    """(path, [(label, text), ...]) -- every chunk of content this tool would write."""
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    items = []
    if isinstance(path, str) and path:
        items.append(("filename", os.path.basename(path)))
    for key in ("content", "new_string", "new_source"):
        v = ti.get(key)
        if isinstance(v, str) and v:
            items.append((key, v))
    edits = ti.get("edits")
    if isinstance(edits, list):
        for i, e in enumerate(edits):
            if isinstance(e, dict):
                v = e.get("new_string") or e.get("new_source")
                if isinstance(v, str) and v:
                    items.append(("edits[{}].new_string".format(i), v))
    return (path if isinstance(path, str) else ""), items


path, items = candidates(tool_input)
if not items:
    allow()

# Only guard files inside the yar repo. Anything clearly outside is none of our business.
root = find_repo_root(path)
if path and root:
    ap = os.path.realpath(path)
    if not (ap == root or ap.startswith(root + os.sep)):
        allow()

for label, text in items:
    m = NON_LATIN.search(text)
    if not m:
        continue
    count = len(NON_LATIN.findall(text))
    i = m.start()
    snippet = text[max(0, i - 15):i + 15].replace("\n", " ").strip()
    where = "the filename" if label == "filename" else "`{}`".format(label)
    sys.stderr.write(
        "english-guard: non-English text detected in {}.\n".format(where)
        + ("   File: {}\n".format(path) if path else "")
        + "   Found near: ...{}...  ({} non-Latin letter(s) total).\n".format(snippet, count)
        + "   Policy: the yar repo is English-only -- all source, docs, comments, and filenames must be in English.\n"
        + "   Fix: rewrite this content (and any non-English filename) in English, then write it again.\n"
        + "   Note: editing a genuinely non-English file OUTSIDE this repo is fine -- this guard only covers yar.\n"
        + "   Rare deliberate bypass: ENGLISH_GUARD=off\n"
        + "   -- blocked by english-guard (PreToolUse): keep yar English.\n"
    )
    sys.exit(2)

allow()
