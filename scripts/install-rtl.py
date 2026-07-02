#!/usr/bin/env python3
"""install-rtl — install yar's Persian/RTL chat-rendering rule into the GLOBAL
``~/.claude/CLAUDE.md`` so every project on this machine renders Persian (or any
RTL-language) replies correctly. Run via:  /yar:install-rtl

Why: chat clients render plain-text messages as LTR paragraphs, so a reply that
mixes Persian with English words, digits, or punctuation scrambles (BiDi) — the
final period jumps to the head of the line, Latin tokens reorder, numeric
ranges flip. The rule installed here is the battle-tested fix: render the whole
reply as an RTL HTML widget card when a widget tool exists, keep every piece of
plain chat text English, and isolate neutral-edged tokens (paths, URLs).

Idempotent: the rule lives between marker comments; re-running replaces the
managed block in place (that is also how future upgrades of the rule arrive)
and never touches anything else in the file. Honors ``CLAUDE_CONFIG_DIR`` when
set, otherwise targets ``~/.claude/CLAUDE.md``.
"""
import os
import sys

BEGIN_MARK = "<!-- yar:install-rtl begin — managed block; re-run /yar:install-rtl to update; manual edits inside will be overwritten -->"
END_MARK = "<!-- yar:install-rtl end -->"

# The rule itself. Edit here to change what every `install-rtl` run installs.
RULE = """## Persian / RTL chat replies — render correctly (managed by yar)

Chat clients typically render plain-text messages as LTR paragraphs, so a reply
that mixes Persian (or any RTL script) with English words, digits, or
punctuation scrambles: the trailing period jumps to the head of the line, Latin
tokens reorder, numeric ranges flip. Two non-fixes, tested and rejected: Unicode
isolate characters (U+2066…U+2069 — chat clients strip or ignore them) and
transliterating English words into the RTL script (natural code-switching must
survive). What works:

1. **If an inline HTML-widget tool is available** (e.g. `mcp__visualize__show_widget`):
   render the **entire reply** as one RTL HTML card — never "card for the main
   content + a plain-text summary in chat" (the summary scrambles too). Card
   spec: `<div dir="rtl" lang="fa">` (match the reply's language),
   `text-align: right`, a Persian-capable font (e.g. Vazirmatn 400/500 via
   fonts.googleapis.com), colors only through the host theme's CSS variables,
   transparent background.
2. **Inside the card**, mix RTL and English naturally — the browser's BiDi
   algorithm lays it out correctly. One exception: a token that *starts or ends
   with a neutral character* (file paths like `~/.claude/...`, URLs, CLI
   commands) still breaks; wrap it in
   `<span dir="ltr" style="display:inline-block; unicode-bidi: isolate;">…</span>`
   — a bare `dir="ltr"` is not enough; `inline-block` is what makes it atomic.
3. **Outside the card: zero RTL plain text.** Even a 100%-pure-Persian sentence
   scrambles (its trailing period jumps — the client paragraph is LTR). Every
   piece of plain chat text — the intro line, status notes between tool calls,
   the closing sentence — either goes inside the card or is written in
   **English**. Never RTL plain text.
4. **If no widget tool is available** (plain CLI): either reply in English, or
   write structurally BiDi-safe RTL text: every line/bullet starts with an RTL
   word; Latin tokens sit between two RTL words with no punctuation attached
   (not `Convi/Horizon` — write «Convi و Horizon»); no hyphenated numeric
   ranges (write «۱۵ ژوئن», never «06-15»); parentheses only around fully-RTL
   content.

Scope: replies rendered **to** the user in chat. Text ghost-written **as** the
user (emails, messages meant to be forwarded) stays raw — no HTML, no direction
characters. Generated files (PDF, HTML decks) render RTL correctly on their own
and need none of this."""


def target_path():
    """The global CLAUDE.md this installer manages."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join("~", ".claude")
    return os.path.join(os.path.expanduser(cfg), "CLAUDE.md")


def managed_block():
    return "{}\n\n{}\n\n{}".format(BEGIN_MARK, RULE, END_MARK)


def apply(text):
    """Return (new_text, action) where action is installed | updated | unchanged.

    Replaces the content between the markers when they exist (malformed marker
    pairs — an end before a begin, or a missing end — are treated as absent so
    nothing outside a well-formed block is ever rewritten); appends the block
    otherwise. Everything outside the markers is preserved byte-for-byte.
    """
    begin = text.find(BEGIN_MARK)
    end = text.find(END_MARK)
    if begin != -1 and end != -1 and end > begin:
        current = text[begin : end + len(END_MARK)]
        if current == managed_block():
            return text, "unchanged"
        return text[:begin] + managed_block() + text[end + len(END_MARK):], "updated"
    prefix = "" if not text else text.rstrip("\n") + "\n\n"
    return prefix + managed_block() + "\n", "installed"


def install(path):
    """Apply the managed block to the file at ``path``. Returns the action taken."""
    text = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    new_text, action = apply(text)
    if action != "unchanged":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
    return action


def main():
    path = target_path()
    try:
        action = install(path)
    except OSError as e:
        sys.stderr.write("✗ could not write {}: {}\n".format(path, e))
        sys.exit(1)
    verb = {
        "installed": "installed into",
        "updated": "updated in",
        "unchanged": "already up to date in",
    }[action]
    print("✅ yar Persian/RTL rendering rule {} {}".format(verb, path))
    print("   Scope: global — applies to every project on this machine.")
    print("   Idempotent: re-run any time; only the managed marker block changes.")
    print("   Undo: delete the block between the yar:install-rtl markers.")


if __name__ == "__main__":
    main()
