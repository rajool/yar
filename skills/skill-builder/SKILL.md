---
name: skill-builder
description: Author, edit, and improve Claude Agent Skills following the current Agent Skills standard (SKILL.md frontmatter limits, progressive disclosure, description-based triggering). Bundles the full draft, test, evaluate, iterate, validate, and package loop with a ready template and Python scripts. Use whenever someone wants to create a new skill, says "turn this into a skill", "make/create/build a skill", or asks to edit, fix, improve, validate, package, or optimize the triggering/description of an existing skill — even when they describe a repeatable workflow worth capturing without saying the word skill.
---

# skill-builder — building Claude skills

Goal: build/edit/improve Claude Agent Skills following the **current Agent Skills standard**. This skill is **self-contained**: the entire workflow lives here and in `reference/`, so you don't need an external tool for everyday work.

> Why a dedicated skill? It makes every skill you build come out **consistent**, to standard, and validatable — instead of reinventing structure and triggering each time.
>
> Optional heavy tooling: Anthropic's official `skill-creator` (an HTML benchmark viewer + an automatic description optimizer) is great when you need it; this skill doesn't re-implement those. Reach for it only when the manual method below isn't enough (section 5 and `reference/evaluation.md`).

This is a loop, not a straight line: **intent → draft → test → evaluate → improve → (validate/package)**. Figure out where in the loop the user is and help from there. If the user says "I don't want to run evals, just build it quickly," do that — be flexible.

---

## 0) Intent and scope
First figure out what the skill is supposed to do. If this very conversation already contains a workflow (e.g. the user said "turn this into a skill"), pull the details from the history (tools, order of steps, corrections the user made, input/output format) and only ask about the gaps. Clarify these 4:

1. What does the skill enable Claude to do?
2. When should it activate? (which phrases/contexts)
3. What is the output format?
4. Is a test case needed? Objective output (file conversion/extraction/code) → yes; subjective output (writing style) → usually no. Propose a default, but the user decides.

If you need external facts to build the skill well (e.g. details of an API or a best practice), research it here with a subagent so the user's load is reduced.

## 1) Draft
1. Create the folder. Common locations: a project skill at `.claude/skills/<name>/`, a personal skill at `~/.claude/skills/<name>/`, or a skill inside a plugin at `<plugin>/skills/<name>/`. `<name>` is the same as `name` in the frontmatter, kebab-case.
2. Start from the template: copy `assets/SKILL-template.md` to `SKILL.md` and fill it in.
3. Write the frontmatter **precisely**. The rules and hard numbers (the 64/1024 character limits, kebab-case, no `<>`) are in `reference/standards.md` section 1 — read it if in doubt.
4. Write a good `description`; it's the only trigger signal (section 5). Keep the body imperative, numbered, and **under ~500 lines**; explain the "why" instead of dry MUSTs. Writing-style details in `reference/standards.md` section 5.

> Progressive disclosure: move whatever isn't always needed to `reference/` so the context stays light. This very skill is an example — a light body + two reference files.

## 2) Test
Build 2–3 **real** prompts (something a real user would actually type, with details), show them to the user, and get confirmation. Save them in `evals/evals.json` (from `assets/evals-template.json`), for now without assertions. The full workflow is in `reference/evaluation.md` sections 2–3.

## 3) Evaluate
For each test, spawn two subagents in one go: one **with the skill** and one **baseline** (without the skill for a new skill; the old version for an improvement). Put the outputs in `<skill>-workspace/iteration-<N>/`, write the assertions and grade them, and compare with-skill against baseline. If a subagent isn't available, read the SKILL.md yourself and run it manually. Details: `reference/evaluation.md` sections 4–6.

## 4) Improve and iterate
Based on the results, make the skill better — and **generalize, don't overfit** (the goal is thousands of prompts, not these few samples). Keep the prompt light, explain the "why," and if you spot repetitive work, bundle it in `scripts/`. Improve → run again → get feedback → iterate, until the user is satisfied. Details: `reference/evaluation.md` section 7.

## 5) Description optimization
The description is the most important lever for correct activation. Manual method: build ~20 queries (half "should activate," half "should not" — especially near-misses), test the description against them, and refine. Write the trigger phrases in **the languages your users actually use**, and a bit **"pushy"** (Claude tends to undertrigger). To automate it, run the skill-creator optimizer (`reference/evaluation.md` section 8).

## 6) Validate and package
Before calling it "done," validate (this skill itself must PASS too — dogfood):
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/skill-builder/scripts/validate.py" <path-to-skill-dir>
```
If you want the skill for upload/distribution, package it (it validates itself first):
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/skill-builder/scripts/package_skill.py" <path-to-skill-dir>
```
The `<name>.skill` output is a binary (a zip) — for local use in Claude Code, the folder in `.claude/skills/` (or a plugin's `skills/`) is enough; packaging is only needed for claude.ai / the Skills API.

## 7) Project conventions (optional, but keep things consistent)
Fit the skill to whatever conventions the project already uses:
- **Path/style:** `.claude/skills/<name>/SKILL.md`, an imperative numbered body, a consistent language for the prose.
- **Paired agent (if it has heavy/long work):** create an `agents/<name>.md` (or `.claude/agents/<name>.md`) with a `tools:` field that returns clean output and doesn't clutter the context (pattern: `gemini-research-free` → `gemini-researcher`).
- **Update everywhere:** if the project keeps a skills index, a README, or a reports folder, update them in the same change. Leave no stale doc.

## 8) Guardrails
- **Principle of least surprise:** the skill must not contain malware/exploit code or do anything hidden beyond its declared intent. Don't build a deceptive/malicious skill.
- **No secrets and no binaries in git** (credentials, API keys, PDFs, audio). Only text/Markdown/code.
- For regulated/high-stakes domains (legal/medical/financial), a skill should gather facts but route the final interpretation to a qualified human/expert — don't let it present itself as a sign-off.

---

## References
- `reference/standards.md` — the full cited standard (frontmatter/numbers, structure, progressive disclosure, writing the description and body, portability, packaging). **When to read:** while writing the frontmatter or making a structural decision.
- `reference/evaluation.md` — the test/grade/benchmark/iterate method and description optimization. **When to read:** while testing and improving.
- `assets/SKILL-template.md` — a ready starting template for a new skill.
- `assets/evals-template.json` — the starting point for `evals/evals.json`.
- `scripts/validate.py` · `scripts/package_skill.py` — validation and packaging.
- Official heavy tooling (optional, if installed): the Anthropic `skill-creator` plugin (HTML eval viewer + automatic description optimizer).
