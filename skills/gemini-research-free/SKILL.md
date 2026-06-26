---
name: gemini-research-free
description: FREE, multi-source web research on any topic via the Google **Gemini CLI** (free tier / Google login — no billed key), producing a cited Markdown report. Gemini-powered — distinct from Anthropic's built-in `/deep-research` (which fans out Claude's own WebSearch). Its PAID counterpart is `boote:gemini-research-paid` (Gemini API, sharper/deeper, billed). Use whenever the user says "go research X", "deep research on …", "free gemini research", Persian "تحقیق رایگان با جمینای", or asks for a researched answer/briefing on a market, vendor, regulation, technology, best practice, country/region facts, pricing, etc. Saves the report as a .md file (by default under reports/). Output is research data — for domain-specific interpretation (legal, medical, financial) treat it as raw facts to be verified by a qualified expert, not authoritative advice.
---

# gemini-research-free — free deep research with Gemini CLI

Goal: when asked to "go research X", run a deep, multi-source investigation with the **Gemini CLI** and deliver a cited Markdown report. The research engine is **Gemini** (agentic web browsing), not Claude's WebSearch — Gemini cross-checks many sources in one pass and returns a denser, source-tagged result.

> **Free, Gemini, and one of three.** This is the **free** door (Gemini CLI, no billed key) — *not* Anthropic's built-in `/deep-research` (which fans out Claude's own WebSearch). The **paid** Gemini door is `boote:gemini-research-paid` (Gemini API, sharper/deeper). `ceo-deep-research` (if installed) is the smart router that picks between the two.

## 0) Clarify the scope (only if ambiguous)
If the question is ambiguous (no budget/region/time range/criteria), ask **2–3 short clarifying questions**, then continue. If it's clear, go straight ahead.

## 1) Run the research (gemini-researcher agent)
Dispatch the `gemini-researcher` agent with the **full, clarified question** (Agent tool). The raw research output is long, so running it in a subagent keeps the main context clean — the agent returns a structured report (TL;DR, findings, uncertainties, sources, confidence).

For a quick/small research you can call the wrapper directly with a long timeout instead:
```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/gemini-research-free/scripts/gemini-research.sh" "<full question>" /tmp/gemini-research-out.md   # Bash timeout ≈ 600000ms
```
Then read `/tmp/gemini-research-out.md`. The script's progress/errors go to **stderr** (which model it used, fallbacks, success/fail) — read those to know what happened.

### Models, quota, and failing fast (read this — 2026)
- The free tier gives **`gemini-2.5-pro` a quota of `limit: 0`** — calling pro fails instantly (`Quota exceeded … limit: 0` → `unexpected critical error`). **Never default to pro on the free tier.**
- The wrapper therefore **ladders `gemini-2.5-flash` → `gemini-2.5-flash-lite`**, **time-boxes** each attempt (`GEMINI_TIMEOUT`, default 420s), and **fails fast** with an actionable message instead of hanging. `flash`/`flash-lite` have **daily caps that reset ~midnight Pacific**; web grounding can also 429.
- Overrides: `GEMINI_MODEL=gemini-2.5-flash-lite` pins the lightest model; `GEMINI_TIMEOUT=<sec>` adjusts the per-attempt cap.
- **If it still fails** (all free models capped): use the paid skill `boote:gemini-research-paid` (billed Gemini API key) or fall back to Claude's own `/deep-research`. Don't keep retrying a quota-blocked model — that's the trap that wastes time.

## 2) Save the report
Save it to `reports/YYYY-MM-DD_<slug>.md` (or wherever the project keeps research notes). Use an absolute date. Structure: a **Summary** (TL;DR), the body with source markers, and a **Sources** section with full URLs. At the top, note the topic and `Source: Gemini deep research — <date>`.

## 3) Summary in chat
Give a short summary right here: TL;DR + 3–5 key points + a pointer to the sources. If the project keeps a reports index, add a row.

## 4) Guardrails
- **Citation:** every important claim needs a source; flag unsourced claims and suspicious URLs. Gemini must not fabricate sources — if a URL looks invented, verify that one with WebFetch.
- **Not authoritative advice:** for legal / medical / financial / regulatory topics, Gemini's output is *raw facts to gather*, not a professional opinion. Route the interpretation and final recommendation to a qualified human/expert; don't present a researched answer as a sign-off.
- **Text, not binary:** the report is a `.md` file. Don't write secrets or personal data into a report that lands in git.

## Authentication (one-time)
The Gemini CLI works either with `GEMINI_API_KEY` in the project's `.env` (or the environment), or with a free Google login (run `gemini` once and log in; it persists in `~/.gemini`). If the script throws an auth error, set up one of these two and retry.
