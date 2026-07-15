<div align="center">

# Yar

**A toolkit of reusable [Claude Code](https://code.claude.com) skills — packaged as one plugin you can drop into any project.**

_Yar_ (Persian for "companion / helper") bundles an invoke-only git workflow, deep web research, a meeting recorder + transcriber, a file organizer, a skill-authoring kit, and a set of safety guards — each as a Claude Code skill that acts **only when you ask**.

[![CI](https://github.com/rajool/yar/actions/workflows/ci.yml/badge.svg)](https://github.com/rajool/yar/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/rajool/yar?sort=semver)](https://github.com/rajool/yar/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-d97757)](https://code.claude.com/docs/en/plugins)
[![Changelog](https://img.shields.io/badge/changelog-keep%20a%20changelog-orange)](CHANGELOG.md)

</div>

---

## Why yar

- **One install, many tools.** A single plugin carries fourteen skills and two agents across every project you work in.
- **Invoke-only by design.** Nothing branches, commits, records, deletes, or sends on its own — skills run when you ask, guards only block mistakes.
- **Safety built in.** Hooks block bulk `git add`, edits on `main`, committed binaries/secrets, and destructive commands like `rm -rf` — and they [fail open](CONTRIBUTING.md), so they never get in the way of legitimate work.
- **Self-hosting.** It is both a **plugin** and its own **marketplace** in one repo, so installing is two lines.

## Table of contents

- [Install](#install)
- [What's inside](#whats-inside)
- [The `git-workflow` skill](#the-git-workflow-skill)
- [Guardrails & permissions](#guardrails--permissions)
- [Repository layout](#repository-layout)
- [Development](#development)
- [Trust & security](#trust--security)
- [Contributing](#contributing)
- [License](#license)

## Install

> `/plugin` commands run **inside** Claude Code — type them at the prompt.

```text
# 1) Register the marketplace (once per machine)
/plugin marketplace add rajool/yar          # or: /plugin marketplace add ~/Projects/Plugins/yar

# 2) Install the plugin
/plugin install yar@yar
```

<details>
<summary><strong>No <code>/plugin</code> command?</strong> (Cowork, web, the Agent SDK) — enable yar declaratively</summary>

Some environments don't expose the `/plugin` slash command. Add the block below to `.claude/settings.json` at **user level** (`~/.claude/settings.json`, applies everywhere) or **project level** (committed, so teammates get it on trust). The runtime reconciles `enabledPlugins` at startup and fetches the marketplace automatically — no `/plugin install` needed:

```json
{
  "extraKnownMarketplaces": {
    "yar": { "source": { "source": "github", "repo": "rajool/yar" } }
  },
  "enabledPlugins": {
    "yar@yar": true
  }
}
```

</details>

## What's inside

### Skills

| Skill | Invoke | What it does |
|---|---|---|
| [`git-workflow`](skills/git-workflow/SKILL.md) | `/yar:git-workflow` | Invoke-only git flow: short-lived branch → conventional commits → rebase → PR → squash-merge, plus one git worktree per parallel session. Ships guard hooks (no bulk add, no edits on `main`, no binaries/secrets). |
| [`daily-sync`](skills/daily-sync/SKILL.md) | `/yar:daily-sync` | Start-of-day / end-of-day sync across **every** local repo and installed plugin at once. Morning: scan + `pull` every repo/worktree + refresh all plugins. Night: push all committed work, rebase/surface conflicts, offer to commit dirty trees (never discards), and sweep merged/`gone` worktrees — so local and remote end identical. Read-only scan + plan first; confirms hard-to-reverse steps. Builds on [`git-workflow`](skills/git-workflow/SKILL.md); triggers on "good morning" / "good night". |
| [`daily-log`](skills/daily-log/SKILL.md) | `/yar:daily-log` | Project-agnostic engine for a **personal end-of-day retro log**: five questions (today's work, decisions, energy/focus 1-10, concerns, tomorrow's top priority) → one dated Markdown file per day, structured for later pattern analysis (energy trends, recurring concerns). Optional read-only evening dashboard when the caller wires in task/calendar sources. The caller supplies the context layer (log dir, sources, decision store, routing, language). Personal retro only — repo syncing stays with [`daily-sync`](skills/daily-sync/SKILL.md). |
| [`gemini-research-free`](skills/gemini-research-free/SKILL.md) | `/yar:gemini-research-free` | **Free** deep, multi-source web research via the Google **Gemini CLI** → a cited Markdown report. Gemini-powered, _not_ Anthropic's built-in `/deep-research`; the **paid** Gemini engine is `boote:gemini-research-paid`. Dispatches the [`gemini-researcher`](agents/gemini-researcher.md) agent. Needs `GEMINI_API_KEY` or a Google login. |
| [`skill-builder`](skills/skill-builder/SKILL.md) | `/yar:skill-builder` | Author / edit / validate / package Claude Agent Skills to the current standard. Bundles a template plus `validate.py` and `package_skill.py`. |
| [`organize-files`](skills/organize-files/SKILL.md) | `/yar:organize-files` | Project-agnostic engine for tidying any folder: meaningful naming (`YYYY-MM-DD-name.ext`), duplicate detection, best-version selection, safe deletion (trash, never `rm`), and per-folder README upkeep. Reads file contents via [`file-inspector`](agents/file-inspector.md). |
| [`meeting-recorder`](skills/meeting-recorder/SKILL.md) | `/yar:meeting-recorder` | **macOS only.** Record a call as a small audio-only `.m4a` via a self-built CoreAudio process-tap recorder — no third-party app. Captures both the other participants and your mic, then hands off to `meeting-processor`. |
| [`meeting-processor`](skills/meeting-processor/SKILL.md) | `/yar:meeting-processor` | Turn a recording or transcript into a clean summary with decisions and action items (owner / deadline / priority), then optionally route them into the project's own tools (tasks, calendar, decisions record, docs, follow-up email). Tracks a per-meeting **processing ledger** so "review the meetings" shows what's done vs. still pending. Transcribes with **ElevenLabs Scribe v2**. Needs `ELEVENLABS_API_KEY` only when transcribing. |
| [`md-to-pdf`](skills/md-to-pdf/SKILL.md) | `/yar:md-to-pdf` | Convert a Markdown file into a print-ready, **RTL-aware** A4 PDF (Vazirmatn font + headless Chrome) — built for Persian/Farsi and other right-to-left documents, works for LTR too. Renders headings, tables, lists, code, blockquotes, and an optional YAML frontmatter block; fonts are fetched once on first use and cached (no binaries in the repo). |
| [`source-claims`](skills/source-claims/SKILL.md) | `/yar:source-claims` | Verify and source the factual / market / statistical claims in a draft so each carries a hyperlink to the **original independent source** — never a vendor's own marketing page — backed by a concrete number. Searches the web for the real URL (never guesses or fabricates links) and flags any claim it cannot back, so the author can cut it or mark it an estimate. |
| [`chrome-devtools`](skills/chrome-devtools/SKILL.md) | `/yar:chrome-devtools` | Drive Google Chrome to do a real task on the web — navigate, fill forms, click through flows, extract page content, check network/console — via the **Chrome DevTools Protocol** (`chrome-devtools` MCP). Targets elements by DOM/accessibility snapshot instead of pixels, so it's faster and more reliable than screenshot+coordinate extensions. Never types passwords, 2FA, or card numbers — the user does those. |

Three manual install commands ship as skills too: [`install-guards`](skills/install-guards/SKILL.md) (`/yar:install-guards`) and [`install-perms`](skills/install-perms/SKILL.md) (`/yar:install-perms`) — see [Guardrails & permissions](#guardrails--permissions) — plus [`install-rtl`](skills/install-rtl/SKILL.md) (`/yar:install-rtl`), which teaches the machine's **global** `~/.claude/CLAUDE.md` to render Persian/RTL chat replies correctly: the whole reply as one self-contained RTL widget card (an always-on base style plus pay-per-use component snippets — KPI cards, bar and donut charts, callouts, timelines, tables) when a widget tool exists, atomic LTR isolation for paths/URLs, English-only plain chat text (intros, status notes, closings), and a structurally BiDi-safe fallback for plain CLI. Once per machine, idempotent (a managed marker block), re-run to receive rule upgrades.

### Agents

| Agent | Invoke | What it does |
|---|---|---|
| [`file-inspector`](agents/file-inspector.md) | `yar:file-inspector` | Deeply reads a single file (PDF, image, doc, text) — **full content**, not just metadata — and returns a structured report (type, subject, dates, signatures, entities, summary, suggested name/destination). Great for organizing folders or detecting duplicates; also the reading engine behind `organize-files`. |
| [`gemini-researcher`](agents/gemini-researcher.md) | _(used by `gemini-research-free`)_ | Runs the Gemini CLI in a subagent and returns a structured, source-cited report, keeping the main context clean. |

## The `git-workflow` skill

**Invoke-only.** It never branches, pushes, opens, or merges a PR on its own — it runs the workflow **when you ask**. Just talk to it:

- "start a task / create a branch for X"
- "commit this", "sync with main", "rebase on main"
- "open a PR", "merge this", "ship it"
- "set up a worktree so I can work on two things at once"
- "I committed on main by accident — fix it"

When you ask it to commit, it stages and commits **only this session's own files** — verified against the working tree first — and leaves any concurrent session's changes untouched. That is the active complement to the passive `git-guard` below.

## Guardrails & permissions

yar carries a safety policy into **every** project that enables it: fewer prompts on safe tools, a hard stop on dangerous ones. Guards are **passive** (they block mistakes, never drive the workflow) and **fail open** (an error never blocks legitimate work).

| Guard | Type | Auto-active? | What it blocks |
|---|---|:--:|---|
| `git-guard` | PreToolUse(Bash) hook | ✅ | `git add -A` / `.` / `-u` / `-f` and `git commit -a`. |
| `branch-guard` | PreToolUse(Edit\|Write) hook | ✅ | Editing files while on `main` — nudges you to branch first. |
| `perms-guard` | PreToolUse(Bash) hook | ✅ | Force-recursive deletes — `rm -rf` (incl. `sudo` and combined flags) and `docker rm -f`. |
| `pre-commit` | git hook | run `/yar:install-guards` | Committing binaries/secrets from **any** git client (terminal, GUI, Claude). |

The first three are Claude Code hooks (automatic once the plugin is enabled). `pre-commit` is a _git_ hook, so it needs a one-time per-repo install:

```text
/yar:install-guards      # once per repo — wire the binaries/secrets pre-commit guard
/yar:install-perms       # once per repo — merge the allow/deny permission policy into .claude/settings.json
```

<details>
<summary>Permissions policy detail & rare overrides</summary>

A Claude Code **plugin can't ship `permissions` directly**, so the policy comes in two layers: the deny side rides along as an always-on **hook** (`perms-guard`, no setup), and the allow side is an opt-in **merge** into your repo settings (`install-perms`, visible in `/permissions`, never overwrites what's there). A settings `deny` always beats an `allow`, and `perms-guard` blocks destructive patterns regardless — so `Bash(*)` in the allow-list never opens the door to `rm -rf`.

| Override (rare) | Effect |
|---|---|
| `GIT_GUARD=off` | Disable the bulk/force-staging block for one command. |
| `BRANCH_GUARD=off` | Allow editing on `main` for this session. |
| `PERMS_GUARD=off` | Disable the destructive-command block for one command. |
| `git commit --no-verify` | Skip the pre-commit binary/secret check for one commit. |

The branch guards assume the default branch is `main`. If yours is `master`/`trunk`, adjust `scripts/branch-guard.py`.

</details>

## Repository layout

```text
yar/
├── .claude-plugin/
│   ├── plugin.json        # the "yar" plugin manifest
│   └── marketplace.json   # one-repo marketplace (source: "./")
├── skills/                # one folder per skill (SKILL.md + reference/scripts/assets)
│   ├── git-workflow/      #   git-workflow · daily-sync · daily-log · gemini-research-free ·
│   ├── …                  #   skill-builder · organize-files · meeting-recorder · meeting-processor ·
│   │                      #   md-to-pdf · source-claims · chrome-devtools ·
│   └── install-perms/     #   install-guards · install-perms · install-rtl (manual, disable-model-invocation)
├── agents/                # file-inspector · gemini-researcher
├── hooks/hooks.json       # git-guard + perms-guard + branch-guard wiring
├── scripts/               # guard scripts + installers (pre-commit, perms)
├── tests/                 # unit/integration tests for the guard scripts
└── .github/workflows/     # CI (lint, test, validate) + the no-context merge gate
```

## Development

```bash
claude --plugin-dir ~/Projects/Plugins/yar          # load the plugin without installing

# Quality gates (also run in CI — see .github/workflows/ci.yml)
python3 -m unittest discover -s tests -v     # run the test suite (zero dependencies)
shellcheck $(git ls-files '*.sh') scripts/pre-commit
ruff check .                                 # lint Python (dev tool; runtime stays dependency-free)
for d in skills/*/; do python3 skills/skill-builder/scripts/validate.py "$d"; done
```

Adding a skill: create `skills/<name>/SKILL.md` (the `skill-builder` skill scaffolds and validates this), wire any command/hook, bump `version` in `.claude-plugin/plugin.json`, add a `CHANGELOG.md` entry, and it becomes `/yar:<name>`. Installed projects pick it up on `/plugin marketplace update`.

## Trust & security

Once enabled, yar runs hooks that execute small shell/Python scripts before certain tool calls, installs a git `pre-commit` hook into your repo, and (on macOS) builds a local audio recorder. Review the code before enabling, as you would any plugin. The guards are a **safety net, not a sandbox** — they reduce mistakes, they are not a boundary against someone who already has shell access. See [SECURITY.md](SECURITY.md) to report a vulnerability.

## Contributing

Contributions are welcome. The repo is **public, generic, and English-only**, enforced automatically by write-time hooks and a CI merge gate. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, how to run the checks, and the two repo-wide rules — and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.

## License

[MIT](LICENSE) © Ali Rajool
