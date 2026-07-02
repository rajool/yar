---
name: install-rtl
description: Install yar's Persian/RTL chat-rendering rule into the machine's global ~/.claude/CLAUDE.md (idempotent managed marker block) so every project renders mixed Persian-English replies correctly — the whole reply as an RTL HTML widget card when a widget tool exists, English-only plain chat text, atomic LTR isolation for paths/URLs, and a BiDi-safe fallback for plain CLI. Run once per machine; re-run to update. Invoked manually as /yar:install-rtl; it does not auto-run.
disable-model-invocation: true
---

# install-rtl — teach this machine to render Persian/RTL replies correctly

Install the plugin's Persian/RTL chat-rendering rule into the **global** `~/.claude/CLAUDE.md` (user memory — applies to every project on this machine), then report the result.

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/install-rtl.py"
```

If `$CLAUDE_PLUGIN_ROOT` is empty in the shell, find the plugin under `~/.claude/plugins/` (look for `yar/scripts/install-rtl.py`) and run that instead.

After it succeeds, confirm to the user that:

- The rule now lives in `~/.claude/CLAUDE.md` between `yar:install-rtl` marker comments — **global** (every project on this machine) and **idempotent**: re-running replaces only the managed block, which is also how future improvements to the rule arrive; everything else in the file is untouched. It honors `CLAUDE_CONFIG_DIR` when that is set.
- What the rule does, in one breath: when replying in Persian (or any RTL language) in a chat client, the **whole reply** renders as one RTL HTML widget card (when a widget tool such as `mcp__visualize__show_widget` exists); tokens with neutral edges — file paths, URLs, CLI commands — are wrapped in an atomic LTR span; **all plain chat text outside cards** (intros, status notes between tool calls, closings) **is English**; and without any widget tool it falls back to structurally BiDi-safe plain text or plain English.
- Why it exists: chat clients lay plain text out as LTR paragraphs, so mixed RTL-LTR replies scramble — trailing periods jump to the head of the line, Latin tokens reorder, numeric ranges flip. Each clause of the rule corresponds to a scrambling actually observed in the wild; Unicode isolate characters and transliteration were both tested and do not work.
- To undo, delete the managed block (markers included) from `~/.claude/CLAUDE.md`.

Then read the rest of `~/.claude/CLAUDE.md`: if it already contains a hand-written RTL/Persian rendering rule **outside** the managed block, point that out and offer to remove the old copy, so the managed block becomes the single source of truth.
