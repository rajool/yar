---
name: daily-log
description: Project-agnostic engine for capturing a person's end-of-day retro log — what got done, decisions made, energy/focus (1-10), concerns, and tomorrow's single top priority — one dated Markdown file per day, structured for later pattern analysis (energy trends, recurring concerns). Conversational, not a form; adapts to a tired user with a 3-line short log. Optionally opens with a read-only evening dashboard (tasks completed today, overdue deadlines, tomorrow's calendar) when the caller wires in sources. The caller supplies the context layer: log directory, dashboard sources, decision store, concern routing, and conversation language. Personal retro only — end-of-day *repo/plugin* syncing is `yar:daily-sync`, not this. Triggers: "log my day", "daily log", "end-of-day log", "evening retro", "journal my day", "how was my day wrap-up".
---

# daily-log — an end-of-day personal retro engine

The reusable **engine** for a nightly personal retrospective: five questions, one dated file per day, stable structure so weeks of logs can later be mined for patterns (energy trends, recurring concerns, drifting priorities). It is deliberately **project-agnostic** — it knows *how* to run and record the retro, not *whose* life or company it describes.

> **The caller supplies the context layer.** A wrapping skill (or you, inline) provides: the **log directory**, any **phase-1 dashboard sources** (task system, calendars, domain flags), the **decision store** (where a formally recorded decision goes), **concern routing** (e.g. a health concern → the caller's health tracker; a match against a caller-defined risk watch-list → flag it), and the **conversation language**. With no caller layer, sensible defaults apply: logs in `journal/daily-logs/` at the project root, no dashboard, decisions and concerns stay in the log, converse in the user's language.

Not to be confused with `yar:daily-sync`: that skill owns "good night" as a *repo/plugin* sync. This one is the *person's* retro. A caller may chain them (sync repos, then log the day), but the engine itself never touches git.

---

## 1. Phase 1 — evening dashboard (optional, read-only)

Run **only if** the caller layer defines sources, **before** asking anything. Gather in parallel and report as a compact summary:

- **Tasks**: what was completed *today* (acknowledge it — it frames the retro positively); overdue items and deadlines within ~7 days (**flag with the date in bold**); open counts per list (numbers only — never dump full lists unprompted).
- **Tomorrow's calendar**: every calendar the caller names, with times; if empty, say so explicitly — an empty tomorrow is information.
- **Caller-defined extras**: upcoming bills, medication/appointment reminders, important dates — only when the caller layer wires them in and only when meaningful tonight.

Phase 1 is **strictly read-only**. The single allowed mutation: marking a task complete when the user explicitly states it is done. Everything else — creating tasks, moving files, editing calendars — waits for the user to ask.

## 2. Phase 2 — the retro conversation

This is **conversational, not a form**. If the user is engaged, ask one question at a time; if their replies are short or they seem tired, batch all five into one message and accept brief answers.

1. **Today** — "What did you work on today? What got finished, what's half-done?" Extract 3-5 items; note whether today's priorities held or shifted.
2. **Decisions** — "Did you make any meaningful decision today? Even a small one." If yes, offer to record it formally in the caller's decision store.
3. **Energy & focus** — "Energy and focus today, 1-10? What moved them?" Capture both numbers plus factors.
4. **Concerns** — "Anything on your mind that won't let go?" If a concern matches the caller's risk watch-list, flag the match explicitly; route domain concerns (health, finance, …) wherever the caller layer says.
5. **Tomorrow** — "What's the single top priority for tomorrow?" One sentence. If the caller has a task system and no matching task exists, offer to create it.

Show a short summary of the assembled log and **confirm before saving**.

## 3. Output — one file per day

Save to `<log-dir>/YYYY-MM-DD.md`. Structural keywords stay in English; content is written in the conversation language.

```markdown
---
date: YYYY-MM-DD
energy: X/10
focus: Y/10
mood: {{one word, optional}}
---

# Daily log — {{date, localized}}

## Today
- {{item}}

## Decisions
{{"No significant decisions." OR a list, linking to the decision store if recorded}}

## Energy & focus
- Energy: X/10 · Focus: Y/10
- Notes: {{factors}}

## Concerns
{{list — explicitly tag matches with the caller's risk watch-list}}

## Tomorrow — top priority
{{one sentence}}

## Tags
{{#topic tags for later pattern queries}}
```

Rules:

- **One file per day; never rewrite past logs.** History is the dataset — corrections go in today's file.
- A `README.md` inside the log directory is metadata, not a log: skip it when globbing/analyzing. An empty directory means no logs yet, not an error.
- Keep the section structure stable across days — pattern analysis depends on it.

## 4. Special behaviors

1. **Tired or terse user** → take a short log without pressure; three lines beat nothing.
2. **Energy < 5 for several consecutive days** → note it at the end of the log and gently offer a check-in conversation (route per the caller layer, e.g. a coach-style skill or a health tracker).
3. **Recurring concern** (same theme in 3+ recent logs) → flag it and suggest acting on it: a task, a dedicated workspace, or a focused conversation.
4. **Latent decision** — if mid-chat the user says "I've decided…" or "I concluded…", offer to record it formally.

## 5. Style

- Warm, empathetic, **zero judgment** — a bad day gets recorded, not lectured about, unless advice is asked for.
- Match the user's language and formality; keep the file's structural keywords English.
- Numbers and dates in the chat summary follow the caller's formatting rules, if any.
