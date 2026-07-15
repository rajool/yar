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
# The CSS kit mirrors the readable plugin (smk-labs/claude-plugins, plugins/readable/assets/rc.css); keep the two in sync.
RULE = """## Persian / RTL chat replies — render correctly (managed by yar)

Chat clients render plain text left-to-right, so a reply that mixes Persian (or
any RTL script) with English words, digits, or punctuation scrambles: the
trailing period jumps to the head of the line, Latin tokens reorder, numeric
ranges flip. Unicode isolate characters and transliteration were both tested and
rejected. What works: render the whole reply as one self-contained widget card.

1. **If an inline HTML-widget tool is available** (e.g. `mcp__visualize__show_widget`),
   deliver the ENTIRE reply as one widget call. The card must be fully
   self-contained — no scripts of any kind and no external resources; the single
   exception is the Google Fonts `@import` already inside the kit, which degrades
   to system fonts when unreachable. Self-containment is what makes the card
   render on every host and offline, and widget sandboxes ignore tool-input
   rewrites from hooks, so only what you emit yourself counts. All styling lives
   in the kit below; you spend zero tokens on design and only add class names.
   widget_code is EXACTLY this card: copy the BASE `<style>` block verbatim
   (never edit it), then write your reply as HTML in place of CONTENT, then
   close the div:

<div class="rc" dir="rtl">
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700;800&family=Inter:wght@400;500;700;800&display=swap');
.rc{--ca:#0f9d58;--cb:#3f8ac9;--cc:#e0a52e;--cd:#d96666;font-family:Vazirmatn,Tahoma,sans-serif;font-size:11.5px;line-height:1.9;color:var(--text-primary);background:var(--surface-1);border:.5px solid var(--border);border-radius:14px;padding:1.2rem 1.4rem;text-align:right;margin:.5rem 0}
.rc>:first-child{margin-top:0}.rc>:last-child{margin-bottom:0}
.rc h2{font-weight:800;font-size:1.35em;margin:0 0 .15em}
.rc h2::after{content:'';display:block;width:28px;height:2.5px;border-radius:2px;background:var(--text-accent);margin-top:.45em}
.rc h3{display:flex;align-items:center;gap:8px;font-weight:700;font-size:1.1em;margin:1.4em 0 .45em}
.rc h3::before{content:'';width:7px;height:7px;border-radius:2px;background:var(--text-accent);flex:0 0 auto}
.rc h4{font-weight:700;font-size:1em;margin:1em 0 .3em}
.rc p{margin:.6em 0}.rc .lead{color:var(--text-secondary);font-size:1.05em}
.rc p,.rc li,.rc h2,.rc h4,.rc td,.rc th,.rc .kpi,.rc .tl div{unicode-bidi:plaintext}
.rc strong{font-weight:700}
.rc code{display:inline-block;direction:ltr;unicode-bidi:isolate;font-family:var(--font-mono);font-size:max(.85em,11px);color:var(--text-accent);background:var(--surface-2);border:.5px solid var(--border);border-radius:5px;padding:1px 5px}
.rc a{color:var(--text-accent);text-decoration:none}.rc a:hover{border-bottom:1px solid currentColor}
.rc ul,.rc ol{padding-inline-start:1.5em;margin:.5em 0}.rc li{margin:.35em 0;position:relative}
.rc ul{list-style:none}.rc ul>li::before{content:'';position:absolute;inset-inline-start:-1.1em;top:.68em;width:4px;height:4px;border-radius:50%;background:var(--text-accent)}
.rc ol{list-style:decimal}.rc ol>li::marker{color:var(--text-accent);font-weight:700}
.rc li.ok::before,.rc li.no::before{content:'✓';background:none;width:auto;height:auto;top:0;inset-inline-start:-1.35em;font-weight:800;font-size:1em;line-height:inherit;color:var(--ca)}
.rc li.no::before{content:'✕';color:#e05555}
.rc .cal{display:flex;gap:9px;padding:9px 12px;border-radius:10px;margin:.8em 0;border-inline-start:3px solid var(--border-strong)}.rc .cal>div{min-width:0}.rc .cal p{margin:.15em 0}
.rc .cal.tip{background:var(--bg-success);border-color:var(--ca)}.rc .cal.note{background:var(--bg-accent);border-color:var(--cb)}.rc .cal.warn{background:var(--bg-warning);border-color:#c98a1a}.rc .cal.danger{background:var(--bg-danger);border-color:#d64545}
.rc hr{border:none;border-top:.5px solid var(--border);margin:1.3em 0}
.rc pre{direction:ltr;text-align:left;unicode-bidi:isolate;font-family:var(--font-mono);font-size:max(.85em,11px);background:var(--surface-2);border:.5px solid var(--border);border-radius:8px;padding:10px 12px;overflow-x:auto;line-height:1.6;margin:.8em 0}.rc pre code{display:block;border:none;background:none;padding:0}
.rc[dir=ltr]{text-align:left;font-family:Inter,system-ui,sans-serif}
.rc[dir=ltr] thead th,.rc[dir=ltr] tbody td{text-align:left}
.rc[dir=ltr] .cta::after{content:'→'}
.rc[dir=ltr] .flow .s:not(:last-child)::before{transform:translateY(-50%) rotate(225deg)}
</style>
CONTENT
</div>

   The same card serves English/LTR replies: set `dir="ltr"` on the wrapper and
   keep everything else identical — the four `[dir=ltr]` rules at the end of
   BASE (inert for RTL cards) flip alignment, switch Vazirmatn for Inter, and
   mirror the flow and CTA arrows. Persian/RTL replies MUST be carded; for
   English replies the card is optional and plain text stays acceptable.

2. **The kit is pay-per-use.** BASE above already styles all text content:
   `<h2>` title plus `<p class="lead">` intro; `<h3>` per section; `<p>`;
   `<ul>`/`<ol>`; status items `<li class="ok">` and `<li class="no">`; callouts
   `<div class="cal tip|note|warn|danger"><div>...</div></div>`; `<a>`;
   `<strong>`; `<hr>` sparingly; `<code>` around every path, command, URL, and
   code token (renders LTR-isolated); `<pre><code>...</code></pre>` for
   multiline code (renders as an LTR block). Everything else is a component with its
   own CSS snippet below: for EVERY component CONTENT uses, copy its snippet
   verbatim into the same `<style>`, right before `</style>`. Snippets are
   independent, order does not matter, never edit them. If unsure whether a
   component is used, include its snippet (missing CSS renders unstyled); never
   paste a snippet for a component CONTENT does not use.

TABLE — comparison tables, plain `<table><thead><tbody>`:
.rc table{border-collapse:collapse;width:100%;margin:.8em 0;font-size:max(.96em,11px)}
.rc thead th{color:var(--text-secondary);font-weight:700;font-size:max(.88em,11px);border-bottom:1.5px solid var(--border-strong);padding:5px 10px;text-align:right}
.rc tbody td{padding:7px 10px;border-bottom:.5px solid var(--border);text-align:right}
.rc tbody tr:last-child td{border-bottom:none}.rc tbody tr:hover td{background:var(--surface-2)}

BADGE — status chips `<span class="badge ok|warn|info">`, mostly inside table cells:
.rc .badge{display:inline-block;font-size:max(.78em,11px);font-weight:700;padding:1px 9px;border-radius:20px;background:var(--surface-2);color:var(--text-secondary)}
.rc .badge.ok{background:var(--bg-success);color:var(--ca)}.rc .badge.warn{background:var(--bg-warning);color:#c98a1a}.rc .badge.info{background:var(--bg-accent);color:var(--cb)}

KV — key-value rows `<div class="kv"><div><b>k</b><span>v</span></div>...</div>`:
.rc .kv{margin:.8em 0}.rc .kv>div{display:flex;justify-content:space-between;gap:14px;padding:6px 2px;border-bottom:.5px solid var(--border)}.rc .kv>div:last-child{border:none}.rc .kv b{color:var(--text-secondary);font-weight:400}.rc .kv span{font-weight:500}

KPI — stat cards `<div class="grid c3">` (or c2, or plain grid) of `<div class="kpi"><div class="l">label</div><div class="n">1.2M<span class="trend up">18%</span></div></div>`; trend classes up/dn:
.rc .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:10px;margin:.8em 0}.rc .grid.c2{grid-template-columns:1fr 1fr}.rc .grid.c3{grid-template-columns:1fr 1fr 1fr}
.rc .kpi{background:var(--surface-2);border:.5px solid var(--border);border-radius:11px;padding:11px 13px}
.rc .kpi .l{font-size:max(.82em,11px);color:var(--text-secondary);margin-bottom:3px}
.rc .kpi .n{font-size:1.8em;font-weight:800;line-height:1.2;color:var(--text-primary)}
.rc .trend{display:inline-block;font-size:max(.55em,11px);font-weight:700;padding:1px 8px;border-radius:12px;vertical-align:2px;margin-inline-start:7px}
.rc .trend.up{background:var(--bg-success);color:var(--ca)}.rc .trend.up::before{content:'▲ '}
.rc .trend.dn{background:var(--bg-danger);color:var(--cd)}.rc .trend.dn::before{content:'▼ '}

BARS — horizontal bars `<div class="bars"><div class="bar"><span class="l">label</span><span class="t"><i style="width:72%"></i></span><span class="v">72%</span></div>...</div>`:
.rc .bars{margin:.8em 0}.rc .bar{display:flex;align-items:center;gap:10px;margin:.45em 0}.rc .bar .l{flex:0 0 auto;min-width:4.5em;color:var(--text-secondary)}.rc .bar .t{flex:1;height:7px;background:var(--surface-2);border-radius:4px;overflow:hidden}.rc .bar .t i{display:block;height:100%;background:var(--text-accent);border-radius:4px}.rc .bar .v{flex:0 0 auto;font-weight:700;font-size:max(.9em,11px)}

DONUT — donut chart, 2-4 slices summing to 100, legend classes a/b/c/d: `<div class="donut-w"><div class="donut" style="--a:46;--b:31"></div><div class="leg"><span class="a"><i></i>label 46%</span><span class="b"><i></i>label 31%</span><span class="c"><i></i>label 23%</span></div></div>`:
.rc .donut-w{display:flex;align-items:center;gap:20px;margin:.9em 0;flex-wrap:wrap}
.rc .donut{width:92px;height:92px;border-radius:50%;flex:0 0 auto;background:conic-gradient(var(--ca) 0 calc(var(--a)*1%),var(--cb) 0 calc((var(--a) + var(--b))*1%),var(--cc) 0 100%);-webkit-mask:radial-gradient(circle,transparent 56%,#000 57%);mask:radial-gradient(circle,transparent 56%,#000 57%)}
.rc .leg{display:flex;flex-direction:column;gap:5px}
.rc .leg>span{display:flex;align-items:center;gap:8px}
.rc .leg i{width:9px;height:9px;border-radius:3px;flex:0 0 auto}
.rc .leg .a i{background:var(--ca)}.rc .leg .b i{background:var(--cb)}.rc .leg .c i{background:var(--cc)}.rc .leg .d i{background:var(--cd)}

FLOW — process steps with automatic arrows `<div class="flow"><span class="s">step</span>...</div>`:
.rc .flow{display:flex;flex-wrap:wrap;align-items:center;gap:34px;margin:.9em .2em}
.rc .flow .s{position:relative;background:var(--surface-2);border:.5px solid var(--border);border-radius:9px;padding:5px 13px;font-weight:500}
.rc .flow .s:not(:last-child)::after{content:'';position:absolute;inset-inline-end:-28px;top:50%;width:22px;height:1.5px;border-radius:1px;background:var(--text-accent);transform:translateY(-50%)}
.rc .flow .s:not(:last-child)::before{content:'';position:absolute;inset-inline-end:-30px;top:50%;width:6px;height:6px;border-left:1.5px solid var(--text-accent);border-bottom:1.5px solid var(--text-accent);transform:translateY(-50%) rotate(45deg)}

TL — timeline `<div class="tl"><div><b>title</b>text</div>...</div>`:
.rc .tl{position:relative;margin:.9em .3em;padding-inline-start:1.4em}
.rc .tl::before{content:'';position:absolute;inset-inline-start:.28em;top:.5em;bottom:.5em;width:1.5px;background:var(--border-strong)}
.rc .tl>div{position:relative;margin:.8em 0}
.rc .tl>div::before{content:'';position:absolute;inset-inline-start:-1.34em;top:.5em;width:8px;height:8px;border-radius:50%;background:var(--text-accent);outline:2.5px solid var(--surface-1)}
.rc .tl b{display:block;font-weight:700}

CTA — closing buttons, max two, only when a natural next step exists: `<div class="btns"><button class="cta" onclick="sendPrompt('exact prompt')">label</button><button class="cta ghost" onclick="sendPrompt('...')">label</button></div>`:
.rc .cta{display:inline-flex;align-items:center;gap:6px;background:var(--text-accent);color:var(--surface-1);border:none;border-radius:9px;padding:7px 15px;font-family:inherit;font-size:1em;font-weight:700;cursor:pointer;margin-top:.4em}.rc .cta::after{content:'←';font-weight:400}.rc .cta:hover{opacity:.88}
.rc .btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:.6em}.rc .cta.ghost{background:transparent;color:var(--text-accent);border:1px solid var(--border-strong)}

3. **Composition: pick the lightest structure that fits the content.** A short
   conversational answer is plain paragraphs with zero components; never reach
   for a component just because the kit has it. When the content genuinely
   benefits: numbers that tell a story get kpi/bars/donut, sequences get
   flow/tl, structured facts get table/kv, and the single most important
   takeaway can sit in one callout. When a reply is long enough to need a
   heading, `<h2>` plus one `<p class="lead">` reads best. Wrap every path,
   command, URL, and code token in `<code>`. One bidi caveat:
   `unicode-bidi:plaintext` takes each line's direction from its first strong
   character, so an RTL line that must START with a Latin token needs `&rlm;`
   prefixed (or lead with an RTL word) to stay right-to-left.

4. **Outside the card: zero RTL plain text.** Every intro line, status note, and
   closing sentence is either inside a card or written in English. The widget IS
   the whole reply: never repeat or summarize the card content as plain text
   afterward, even if you suspect it did not render (it does; plain Persian text
   would only scramble).

5. **If no widget tool is available** (plain CLI): reply in English, or write
   structurally BiDi-safe RTL text — every line starts with an RTL word, Latin
   tokens sit between two RTL words with no attached punctuation, no hyphenated
   numeric ranges.

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
