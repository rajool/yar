#!/usr/bin/env python3
"""yar aliases -- one word of your own, one complete workflow, every time.

A shorthand you say every day (a nickname for a routine, a word in your own
language, a team's slang for "the whole release dance") should run the *same full
procedure* every time -- not a version of it reconstructed from memory. This module
is the small shared core behind that: it finds the user's alias table, normalizes
it, and answers "does this prompt say X?" for Latin and Arabic-script (Persian,
Arabic) phrases alike.

Consumers: ``alias-guard.py`` (UserPromptSubmit -> tells Claude exactly which skill
to invoke and to finish it) and ``ship-guard.py`` (an alias marked ``"ship": true``
also arms the "ship means MERGED" contract, so a shorthand for shipping inherits the
same Stop-hook enforcement the word "ship" has).

Where the table lives -- every file that exists is read, in this order, and a later
file wins on the same word:

    $YAR_ALIASES                         explicit path(s), ":"-separated; "off" disables
    ~/.claude/yar-aliases.json           personal, applies in every project
    <project>/.claude/yar-aliases.json   this project only ($CLAUDE_PROJECT_DIR or cwd)

Format -- ``{"aliases": [...]}`` or a bare list. Each entry:

    {"words": ["nightly tidy", "wrap the day"],   # or "words": "one phrase"
     "run":   "yar:repo-sweep",                   # skill(s) to invoke; str or list
     "do":    "free-text instruction",            # optional, passed through verbatim
     "ship":  false,                              # true -> also arms ship-guard
     "note":  "what it covers / why"}             # optional, shown to Claude

The table is the user's own file and is deliberately not shipped with the plugin:
yar stays generic, the shorthand stays personal.

Every function here fails soft -- a missing, unreadable or malformed table yields an
empty list, never an exception, because a guard bug must not trap a session.
"""
import json
import os
import re

# Prompt zones: in a short prompt the phrase counts anywhere; in a long one it counts
# near the start or the end (where "... then <alias> it" lives), so a pasted document
# that merely mentions the word does not fire. Same windows ship-guard uses.
SHORT_PROMPT = 400
HEAD_WINDOW = 80
TAIL_WINDOW = 200

FILE_NAME = "yar-aliases.json"

# Letter classes used for word boundaries, as escapes so this file stays pure ASCII.
LATIN = "A-Za-z"
ARABIC = "\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff"

_ZERO_WIDTH = "\u200b\u200c\u200d\u200e\u200f\ufeff"      # ZWNJ/ZWJ/marks: not letters
_DIACRITICS = re.compile("[\u064b-\u0652\u0670\u0640]")   # harakat + tatweel
_FOLD = {"\u064a": "\u06cc", "\u0649": "\u06cc",          # Arabic yeh  -> Persian yeh
         "\u0643": "\u06a9",                              # Arabic kaf  -> Persian kaf
         "\u0629": "\u0647"}                              # teh marbuta -> heh


def normalize(text):
    """Fold the spelling differences that make the same Persian word look different:
    zero-width joiners, harakat, and Arabic vs Persian yeh/kaf. Latin text is
    untouched (case is handled by the match itself)."""
    if not isinstance(text, str):
        return ""
    out = _DIACRITICS.sub("", text)
    for src, dst in _FOLD.items():
        out = out.replace(src, dst)
    for ch in _ZERO_WIDTH:
        out = out.replace(ch, "")
    return out


def _edge_class(ch):
    """The letter class a neighbouring character must not belong to, or None when the
    edge is punctuation or a digit (then any neighbour is a real boundary)."""
    if re.match("[" + LATIN + "]", ch):
        return LATIN
    if re.match("[" + ARABIC + "]", ch):
        return ARABIC
    return None


def has_phrase(text, phrase):
    """True when ``phrase`` appears in ``text`` as a whole word / whole phrase.

    Boundaries are script-aware: an English trigger is not matched inside another
    English word ("ship" not in "relationship"), and a Persian trigger is not matched
    inside another Persian word -- the plain ``\\b`` and ``[A-Za-z]`` lookarounds get
    the second case wrong, because every Persian letter looks like a boundary to them.
    Case-insensitive; inner whitespace is flexible.
    """
    if not isinstance(text, str) or not isinstance(phrase, str):
        return False
    p = normalize(phrase).strip()
    if not p:
        return False
    words = p.split()
    if not words:
        return False
    head, tail = _edge_class(p[0]), _edge_class(p[-1])
    pre = "(?<![" + head + "])" if head else ""
    post = "(?![" + tail + "])" if tail else ""
    body = r"\s+".join(re.escape(w) for w in words)
    return re.search(pre + body + post, normalize(text), re.I) is not None


def in_prompt(text, phrase):
    """``has_phrase`` restricted to the zones where a phrase reads as an instruction."""
    if not isinstance(text, str):
        return False
    t = text.strip()
    if not t:
        return False
    zones = [t] if len(t) <= SHORT_PROMPT else [t[:HEAD_WINDOW], t[-TAIL_WINDOW:]]
    return any(has_phrase(z, phrase) for z in zones)


# ---- the table ------------------------------------------------------------------

def disabled():
    return (os.environ.get("YAR_ALIASES") or "").strip().lower() == "off"


def alias_files(cwd=None):
    """Existing alias files, in load order (later wins)."""
    env = (os.environ.get("YAR_ALIASES") or "").strip()
    if disabled():
        return []
    if env:
        paths = [os.path.expanduser(p) for p in env.split(os.pathsep) if p.strip()]
    else:
        project = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
        paths = [os.path.join(os.path.expanduser("~"), ".claude", FILE_NAME),
                 os.path.join(project, ".claude", FILE_NAME)]
    out = []
    for p in paths:
        real = os.path.realpath(p)
        if real not in out and os.path.isfile(real):
            out.append(real)
    return out


def _as_list(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.strip()]
    return []


def _entry(raw, source):
    """One validated entry, or None. Unknown keys are ignored, not an error."""
    if not isinstance(raw, dict):
        return None
    words = _as_list(raw.get("words") or raw.get("word") or raw.get("when"))
    run = _as_list(raw.get("run") or raw.get("skill") or raw.get("skills"))
    do = raw.get("do") or raw.get("then") or ""
    if not words or not (run or isinstance(do, str) and do.strip()):
        return None       # a trigger with nothing to trigger is not an alias
    return {"words": [w.strip() for w in words],
            "run": run,
            "do": do.strip() if isinstance(do, str) else "",
            "ship": bool(raw.get("ship")),
            "note": (raw.get("note") or "").strip() if isinstance(raw.get("note"), str) else "",
            "source": source}


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []            # unreadable or malformed -> this file simply has no aliases
    if isinstance(data, dict):
        data = data.get("aliases")
    if not isinstance(data, list):
        return []
    out = []
    for raw in data:
        e = _entry(raw, path)
        if e:
            out.append(e)
    return out


def load_aliases(cwd=None):
    entries = []
    for path in alias_files(cwd):
        entries.extend(read_file(path))
    return entries


def _index(entries):
    """word (normalized) -> (word as written, entry); a later file wins on a word."""
    idx = {}
    for e in entries:
        for w in e["words"]:
            idx[normalize(w).strip().lower()] = (w, e)
    return idx


def match_aliases(text, cwd=None, entries=None):
    """[(entry, matched word), ...] for every alias this prompt invokes, once each."""
    if entries is None:
        entries = load_aliases(cwd)
    out, seen = [], []
    for word, entry in _index(entries).values():
        if in_prompt(text, word) and id(entry) not in seen:
            seen.append(id(entry))
            out.append((entry, word))
    return out


def ship_phrases(cwd=None, entries=None):
    """Trigger words of aliases that stand for shipping -- ship-guard adopts these."""
    if entries is None:
        entries = load_aliases(cwd)
    out = []
    for e in entries:
        if e.get("ship"):
            for w in e["words"]:
                if w not in out:
                    out.append(w)
    return out
