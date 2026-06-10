# The Agent Skills authoring standard (full reference)

> Cited reference for `skill-builder`. When you want to nail down the frontmatter, structure, or writing style of a skill precisely, read this file.
> Sources: agentskills.io/specification (the open standard of 18 December 2025), the platform.claude.com docs (Agent Skills overview / best-practices / skills-guide), and the official `skill-creator` skill.

## Contents
1. [SKILL.md frontmatter (fields and numbers)](#1-frontmatter)
2. [Folder structure](#2-folder-structure)
3. [Progressive disclosure (three levels + token budget)](#3-progressive-disclosure)
4. [Writing the description](#4-writing-the-description)
5. [Writing the body (patterns and anti-patterns)](#5-writing-the-body)
6. [Reference and file rules](#6-reference-rules)
7. [Skill vs. slash-command and subagent/agent](#7-skill-vs-the-rest)
8. [Portability across levels](#8-portability)
9. [Validation, packaging, distribution](#9-packaging)
10. [Sources](#10-sources)

---

## 1) Frontmatter
Each skill has a `SKILL.md` that begins with a block of YAML frontmatter between two `---` lines.

**Required fields:**

| Field | Rule |
|---|---|
| `name` | kebab-case: only `a-z`, `0-9`, and hyphen; **≤ 64 characters**; no leading/trailing hyphen; no consecutive `--`; must be **exactly the same as the skill's folder name**. |
| `description` | **≤ 1024 characters**, non-empty; third person; includes "**what** the skill does **and** when to use it"; no XML tags / `<` and `>` characters. It is the only signal for the trigger decision. |

(Source: agentskills.io/specification; platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)

**Optional fields:**

| Field | Rule / use |
|---|---|
| `license` | Short (license name or a reference to LICENSE.txt). |
| `compatibility` | ≤ 500 characters; environment requirements (e.g. "Requires Python 3.14+, git"). |
| `metadata` | An arbitrary key-value mapping; pick unique keys so they don't collide. |
| `allowed-tools` | A space-separated list of pre-approved tools (experimental). |

(Source: agentskills.io/specification)

> Most skills write only `name` and `description`. **Agents** have a `tools:` field, not skills — don't mix the two up (section 7).

Example:
```yaml
---
name: pdf-processing
description: Extract text and tables from PDF files, fill forms, and merge documents. Use when the user works with PDFs or mentions forms or document extraction.
license: Apache-2.0
---
```

---

## 2) Folder structure
```
skill-name/
├── SKILL.md            # required: frontmatter + Markdown instructions
├── reference/          # optional: documentation read on demand
├── scripts/            # optional: executable code for deterministic/repetitive work
└── assets/             # optional: templates/assets used in the output
```
The names `reference/`, `scripts/`, `assets/` are conventional; they're not mandatory but they're recommended. (Source: agentskills.io/specification; skill-creator → "Anatomy of a Skill")

---

## 3) Progressive disclosure
A three-level loading system for saving context — the most important architectural idea of a skill:

1. **Metadata** (`name` + `description`): always in context (~100 tokens per skill). The basis of the trigger decision.
2. **The SKILL.md body**: loaded only when the skill activates. Aim for **under ~500 lines** (roughly < 5,000 tokens).
3. **Bundled resources** (`reference/`, `scripts/`, `assets/`): consume **zero tokens until they're read**. Scripts run without loading their code — only the output enters context.

The result: you can ship hundreds of pages of reference alongside the skill with no context penalty; the model reads only the file it actually needs. (Source: platform.claude.com/.../agent-skills/overview; best-practices)

> This very file you're reading is itself an example of level 3: separated from the light SKILL.md body and read only when needed.

---

## 4) Writing the description
The description is the only thing seen when a skill is selected; its quality = the rate of correct triggering.

- **Third person.** "Processes Excel files…" ✅ — not "I can help…" or "You can use this…" ❌. Because the description text is injected directly into the system prompt.
- **Both "what" and "when".** "Extract tables from PDFs. **Use when the user mentions PDFs, forms, or document extraction.**" ✅ — not "Helps with documents" ❌.
- **Put in specific trigger keywords**: file type, user action, context.
- **Be a bit "pushy".** Claude tends to activate a skill **less than it should** (undertrigger). To compensate, say explicitly when it should activate — even "whenever the user talks about X, even if they didn't say the word Y". (Source: best-practices; skill-creator → the description section)

> Write the trigger phrases in the languages your users actually use, and keep example triggers concrete.

A mechanism note: Claude only reaches for a skill for tasks it can't easily handle on its own; simple single-step requests (like "read this PDF") may not activate the skill even with a perfect description match. So eval queries should be **substantive and multi-step**. (Source: skill-creator → "How skill triggering works")

---

## 5) Writing the body
**Base assumption:** the model is already smart; only write what it doesn't know. Test each section: "does it really need this explanation?"

- **Write imperatively:** "do this task", not "this skill does X".
- **Explain the "why", not MUST/NEVER in capitals.** A dry rule without a reason loses the edges; when you give the reason the model generalizes to a new situation. Seeing "ALWAYS/NEVER" in capitals = a yellow flag; rewrite it and give the reason.
- **Set the degree of freedom by how fragile the task is:**
  - High freedom (textual): "analyze the code, find the bugs…" → multiple correct paths.
  - Medium freedom: "use this template and change it if needed."
  - Low freedom (a specific script): "run exactly this command, don't change it." → for fragile tasks (database migration).
- **The output format** — if it matters, state it explicitly (a fixed template).
- **An example** helps: the Input/Output pattern.
- **The Gotchas section** (real mistakes) is the most valuable part; fill it over time from real experience, not assumptions.
- Keep the body **under ~500 lines**; if you get close, add a layer of hierarchy and with a clear pointer say where to read the rest.

(Source: best-practices → Content guidelines / Set appropriate degrees of freedom; skill-creator → Writing Style / Writing Patterns)

---

## 6) Reference rules
- **Keep references one level from SKILL.md.** ✅ `SKILL.md → FORMS.md` — ❌ `SKILL.md → advanced.md → details.md` (the model may read the nested file incompletely).
- **Relative path with a forward slash:** ✅ `reference/guide.md`, `scripts/extract.py` — ❌ a Windows backslash.
- **A reference file larger than ~100 lines** should start with a Table of Contents so the model sees the whole scope even with an incomplete read. (skill-creator says a ~300-line threshold; conservatively use 100.)
- Point to the reference from SKILL.md with a "when to read this file" hint, not just a bare link.

(Source: best-practices → Avoid deeply nested references; skill-creator → Progressive Disclosure)

---

## 7) Skill vs. the rest
- **Skill** = packaged, reusable procedural knowledge (SKILL.md + bundled files). The main standard for agent authoring.
- **Slash-command** = a Claude Code shortcut; it can call a skill but is not itself a skill.
- **Subagent/agent** = an agent spawned with code; commonly defined in `.claude/agents/<name>.md` (or a plugin's `agents/<name>.md`) with a `tools:` field. A skill can dispatch an agent for heavy work (like `gemini-research-free` → `gemini-researcher`).

Rule of thumb: simple, linear work → a single-file self-contained skill. Heavy/long work that would clutter the context → a skill + a paired agent that returns clean output.

---

## 8) Portability
The SKILL.md format is **the same** at every level, but skills **don't sync between levels** — each one is uploaded/installed separately:

| Level | Discovery/installation | Scope |
|---|---|---|
| Claude Code | Filesystem: `~/.claude/skills/` (personal), `.claude/skills/` (project), or bundled in a plugin | personal/project |
| claude.ai | Upload a zip from Settings | that user only |
| Claude API | Upload with the Skills API (`/v1/skills`) | the whole workspace |

(Source: platform.claude.com/.../agent-skills/overview → Where skills work)

---

## 9) Packaging
- **Validation:** before distribution, the skill must pass validation — valid frontmatter, character limits, naming, structure. This skill ships `scripts/validate.py`. (The general standard also has the `skills-ref validate` tool.)
- **Packaging:** the skill folder is turned into a zip archive with a `.skill` extension; `SKILL.md` must be at the top level. This skill ships `scripts/package_skill.py`.
- **API upload:** the whole size **under 30MB**; the output is a skill id with versions. Beta header: `skills-2025-10-02`.
- **Distribution/standard:** the open standard at agentskills.io and the example repository at github.com/anthropics/skills.

(Source: platform.claude.com/.../build-with-claude/skills-guide; anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

> **Don't commit the `.skill` file to git** (it's a binary). Only produce it for upload/distribution.

---

## 10) Sources
- agentskills.io/specification — the open Agent Skills standard (18 December 2025).
- platform.claude.com/docs/en/agents-and-tools/agent-skills/overview — concept, progressive disclosure, Where skills work.
- platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices — writing the description and body, degrees of freedom, nested references.
- platform.claude.com/docs/en/build-with-claude/skills-guide — upload/versioning/30MB/beta header.
- anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills — the official introduction (18 December 2025).
- The official `skill-creator` skill (Anthropic) — `SKILL.md`, `scripts/quick_validate.py`, `scripts/package_skill.py`, `references/schemas.md`.
