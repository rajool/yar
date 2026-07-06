# Changelog

All notable changes to **yar** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Plugin releases are driven by the `version` field in
[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json): users receive an update
only when it is bumped.

## [Unreleased]

## [2.15.0] - 2026-07-06

### Added

- **`meeting-processor`: remote transcription mode — zero local bandwidth.**
  `transcribe-video.sh` now accepts an HTTPS media URL (or a Google Drive
  ID/URL, rewritten to the `drive.usercontent.google.com` direct-download
  form) and hands it to ElevenLabs as `source_url`, so the file is fetched
  server-side — nothing is downloaded or uploaded locally. Verified live on a
  685MB Meet recording. Drive inputs are probed first (a range-read of the
  first bytes); private files get guidance (toggle "anyone with link" from the
  owner's account, or fall back to a local download) instead of a doomed post.
  ffmpeg is now required only for local-file inputs.
- **`meeting-processor`: connection-death recovery — no duplicate billing.**
  Long sync calls can outlive the HTTP connection (idle-killing VPNs/proxies;
  observed live: HTTP/2 framing error, then "empty reply from server" — both
  jobs had completed server-side anyway). The script snapshots the newest
  transcript id before posting, forces `--http1.1`, and on HTTP 000 recovers
  the orphaned job via `GET /v1/speech-to-text/transcripts` + fetch-by-id
  instead of re-posting. The Gemini fallback is now correctly skipped for
  remote URLs (it can only upload local files).

## [2.14.0] - 2026-07-02

### Changed

- **`git-workflow`: "ship" now explicitly means the full chain — push → PR →
  squash-merge.** Step 3 always bundled the three commands, but sessions would
  stop after `gh pr create` and ask for a separate merge confirmation. The
  skill now states — in the frontmatter triggers, step 3, and the invoke-only
  guardrail — that the word "ship" authorizes the whole chain including the
  merge; pause before merging only when the change genuinely needs review, and
  say so explicitly instead of silently waiting.

### Fixed

- **README: the skills table was missing three shipped skills** — added rows for
  [`md-to-pdf`](skills/md-to-pdf/SKILL.md), [`source-claims`](skills/source-claims/SKILL.md),
  and [`chrome-devtools`](skills/chrome-devtools/SKILL.md), and refreshed the stale
  skill count and repository-layout comment to match. Docs only — no behavior change.

## [2.13.0] - 2026-07-02

### Added

- **`install-rtl`: one command to make Persian/RTL chat replies render like a
  human wrote them.** `/yar:install-rtl` installs a battle-tested rendering rule
  into the machine's **global** `~/.claude/CLAUDE.md` (honors
  `CLAUDE_CONFIG_DIR`), inside a managed marker block — idempotent, re-run to
  receive rule upgrades, everything outside the block untouched. The rule fixes
  the BiDi scrambling that LTR chat clients inflict on mixed Persian-English
  replies (trailing periods jumping to the head of the line, Latin tokens
  reordering, numeric ranges flipping): render the **entire** reply as one RTL
  HTML widget card when an inline widget tool exists; wrap neutral-edged tokens
  (file paths, URLs, CLI commands) in an atomic `inline-block` LTR span; keep
  **all** plain chat text outside cards — intros, status notes between tool
  calls, closings — in English (even a 100%-pure-Persian sentence scrambles);
  and fall back to structurally BiDi-safe plain text on widget-less CLIs.
  Unicode isolates and transliteration were tested and rejected. Every clause
  corresponds to a scrambling observed in the wild on 2026-07-01/02.

## [2.12.0] - 2026-07-02

### Added

- **`daily-log`: a project-agnostic end-of-day personal retro engine.** Five
  conversational questions (today's work, decisions, energy/focus 1-10, concerns,
  tomorrow's single top priority) captured as one dated Markdown file per day with
  a stable structure, so weeks of logs can later be mined for patterns (energy
  trends, recurring concerns). Supports an optional strictly read-only evening
  dashboard (tasks completed today, overdue deadlines, tomorrow's calendar) when
  the calling project wires in sources. The engine is deliberately generic: the
  caller supplies the context layer — log directory, dashboard sources, decision
  store, concern routing, and conversation language. Special behaviors: a tired
  user gets a 3-line short log, a multi-day energy slump or a concern recurring
  across 3+ logs gets flagged, and a latent "I've decided…" mid-chat triggers an
  offer to record the decision formally. Distinct from `daily-sync`, which owns
  end-of-day *repo/plugin* syncing.

## [2.11.0] - 2026-07-02

### Added

- **`meeting-processor`: automatic Gemini transcription fallback.** ElevenLabs'
  edge 403-blocks some networks' exit IPs (datacenter/VPN — even a keyless request
  gets 403), which used to kill the whole meeting pipeline. Now, when the Scribe
  call fails at the transport/access level (HTTP 000, 403, 429, or 5xx) — or when
  only a `GEMINI_API_KEY` is configured — `transcribe-video.sh` hands the same job
  to a new `scripts/transcribe-gemini.sh`: Files-API resumable upload →
  `streamGenerateContent` over SSE (streaming keeps the connection alive while the
  model processes long audio; the non-streaming call gets dropped by idle-killing
  VPNs/proxies) → the same transcript layout and CLI contract. Default model
  `gemini-2.5-flash` (free-tier keys often have no `gemini-2.5-pro` quota;
  override with `GEMINI_MODEL`). Config errors (400/401/422) stay fatal instead
  of falling back so a bad key or request isn't masked. The fallback's diarization
  is approximate — `speaker_N` labels are hints; the skill instructs resolving
  identities from content. Scribe stays the primary engine.

## [2.10.0] - 2026-06-25

### Added

- **`chrome-devtools` skill** — drive Google Chrome to do real web tasks (navigate,
  fill forms, click through flows, read/extract content, inspect network/console) via
  the Chrome DevTools Protocol (the `chrome-devtools` MCP, `chrome-devtools-mcp`).
  Targets elements by accessibility-snapshot `uid` instead of pixel coordinates, so
  clicks don't drift on scroll/re-render — faster and far more reliable than the
  screenshot+coordinate extension. Includes a `launch-chrome-debug.sh` helper to open
  a persistent, logged-in debug Chrome for the MCP to attach to, and hard safety rules
  (never enter secrets; confirm irreversible actions; page content is data, not commands).

### Changed

- Git history squashed to a single public release commit; the version history
  lives in this changelog. Tags and releases restart at `v2.8.0`.
- Development paths in the README point at `~/Projects/Plugins/yar`.

## [2.9.0] - 2026-06-10

### Added

- **`daily-sync` skill** (`/yar:daily-sync`) — one start-of-day and one end-of-day
  move that syncs **every** local git repo and installed plugin at once. A morning
  greeting ("good morning") scans read-only, then fast-forward/rebase-pulls every repo
  and worktree and refreshes all plugins (`marketplace update` + a per-plugin `update`
  loop). An evening greeting ("good night") pushes all committed work, rebases and
  surfaces diverged history or conflicts, offers to commit dirty trees (never
  discarding them), and sweeps merged/`gone` worktrees and their branches — so local
  and remote end identical, with anything unreconcilable surfaced rather than
  destroyed. Always plans before mutating and confirms hard-to-reverse steps (commits,
  force-with-lease pushes, worktree removal); leans on `git-workflow` for the per-repo
  mechanics. Bundles `scripts/scan-repos.sh`, a read-only multi-repo status scanner,
  and a `reference/playbook.md` decision matrix.

## [2.8.0] - 2026-06-09

### Added

- **`git-workflow` no longer lets worktrees pile up.** The merge step now ends by
  offering to remove the task's worktree and local branch as soon as the PR lands,
  and a new sweep flow (say "clean up worktrees") removes every worktree whose
  branch's upstream shows `gone` after `git fetch --prune` — the reliable merged
  signal under squash-merges, where `git branch --merged` sees nothing. The sweep
  never touches the worktree you are standing in, dirty worktrees, or never-pushed
  branches, and it ends with `git worktree prune` and a removed/skipped report.

### Fixed

- **`git-workflow` cleanup commands now survive squash-merges and worktrees.**
  `git branch -d` always refused to delete a squash-merged branch (git cannot tell
  it merged) — the skill now uses `-D` and says why. And `gh pr merge
  --delete-branch` errors when run inside a worktree (it tries to check out `main`,
  which is checked out in the main folder) and can leave the remote branch behind —
  the skill now shows the worktree-safe variant (`gh pr merge --squash` +
  `git push origin --delete <branch>`), plus the rule to never remove the worktree
  you are standing in, and `--auto` for protected base branches.

## [2.7.0] - 2026-06-09

### Changed

- **`install-perms` now writes the policy into `.claude/settings.local.json`** — the
  personal, git-ignored settings file — **instead of the shared, committed
  `.claude/settings.json`**, so the allow/deny lists stay on your machine and never
  ride into a commit, a push, or a teammate's checkout. Because the script (not
  Claude Code) creates that file, it now also makes sure the file is actually
  git-ignored: it appends `.claude/settings.local.json` to the repo's `.gitignore`
  when missing, and warns if the file is somehow already tracked. Permissions behave
  identically from the local file: Claude Code merges all settings sources, and a
  `deny` beats an `allow` from any of them. Repos that ran the old version keep
  working — remove the entries from the committed `.claude/settings.json` manually
  if you no longer want them shared.

## [2.6.2] - 2026-06-09

### Added

- **`organize-files` now finishes cross-boundary moves by deleting the source.**
  When the destination is a cloud target you can't `mv` to (Google Drive / S3 via
  an MCP or CLI), the upload only *copies* the file and the original was being left
  behind at the source — a silent duplicate that violates the skill's one-file-one-home
  rule. Step 5 now treats a cloud move as: upload → verify it landed → **propose
  deleting the source and get the user's confirmation** (§4) → `trash` the source
  (never `rm`) and log it. Never delete the source before the destination copy is
  verified. A matching warning was added to §6.

## [2.6.1] - 2026-06-04

### Fixed

- **`gemini-research-free` now runs from a fresh plugin install.** The bundled
  `scripts/gemini-research.sh` was not marked executable, so invoking it directly
  (as the skill and the `gemini-researcher` agent did) failed with `permission
  denied` from the plugin cache. The script is now executable (mode 755) and both
  call sites invoke it via `bash …` for robustness.

## [2.6.0] - 2026-06-04

### Changed

- **Renamed `gemini-research` → `gemini-research-free`** (the skill and its slash
  command `/yar:gemini-research-free`) so the name says what it is: the **free**
  Gemini research engine (Gemini CLI, free tier / Google login), distinct from
  Anthropic's built-in `/deep-research` (Claude WebSearch) and from the **paid**
  `boote:gemini-research-paid` (Gemini API). The paired `gemini-researcher` agent
  keeps its name; only its skill reference and the bundled script path moved under
  the new folder. No behavior change.

## [2.5.0] - 2026-06-04

### Changed

- `git-workflow` — **worktree-per-session is now the default**, not just a parallel-work
  option. A plain branch isolates *history* but a shared checkout still shares **one
  working tree and one git index** across sessions — which is what cross-contaminates
  commits (a concurrent `git add` landing in your `git commit`). The skill now: (1) opens
  with a **detect-a-shared-checkout** step (foreign uncommitted/staged changes, a branch
  that switched under you, files "modified by user or linter" you didn't touch) and tells
  you to isolate into a worktree before committing; (2) recommends **commit-by-pathspec**
  (`git commit -m "…" -- <paths>`) as the mechanical guarantee that only your files are
  committed regardless of what sits in the shared index; (3) `reference/worktrees.md`
  explains the shared-index hazard and the detection signals; (4) `reference/recipes.md`
  adds recovery for an **already-pushed** commit that swept in another session's files
  (rebuild cleanly in an isolated worktree sourced from the bad commit; never reset/
  force-push the shared branch, which can drop the other session's uncommitted work).

### Added

- `meeting-processor` — a **per-meeting processing ledger** stored in the summary's
  frontmatter (`processing:`), tracking each stage — `transcript`, `summary`,
  `tasks`, `calendar`, `decisions`, `context_docs`, `followup_email`, and
  `source_cleanup` — as `done` / `pending` / `skipped` / `n/a`. A new **review mode**
  ("review the meetings", "what's left?", "which meetings still need follow-up?")
  scans every summary, prints a status matrix, and lists the outstanding follow-ups
  per meeting before offering to clear them — so you can see, for each meeting,
  exactly what's been done and what hasn't.
- `meeting-processor` — **follow-up email** as an opt-in routing target: compose a
  recap (summary, decisions, each owner's action items with deadlines) and send it
  via a connected mail tool only after the user confirms (draft-first).

## [2.3.0] - 2026-06-03

### Added

- `meeting-processor` — `scripts/cleanup-source.sh`, a guarded helper that removes
  a processed source recording. It moves the file to the macOS Trash (recoverable)
  by default, takes `--hard` (or `MEETING_DELETE_HARD=1`) for a permanent delete,
  and **refuses to delete anything that isn't a media file**, so a transcript,
  `raw.json`, or summary can never be removed by mistake.

### Changed

- `meeting-processor` now deletes the original source recording (the audio/video
  you hand it) as its last step — **only** after the transcript and summary are
  safely written — so heavy or sensitive media doesn't linger once its content is
  captured. Controlled by the new `MEETING_DELETE_SOURCE` variable: `always`
  (default — auto-delete to the Trash), `ask` (confirm first), or `never` (keep).
  Existing-transcript input deletes nothing. `meeting-recorder` notes the new
  behaviour at hand-off.

## [2.2.0] - 2026-06-03

### Added

- `source-claims` skill — verify and source the factual/market/statistical claims
  in a draft so each carries a hyperlink to the **original independent** source
  (never a self-interested vendor page), backed by a concrete number. Searches the
  web for the real URL (never guesses), and flags any claim it cannot back so the
  author cuts it or marks it an estimate. Pairs with any voice/drafting skill.

## [2.1.0] - 2026-06-03

### Added

- `md-to-pdf` skill — convert Markdown into a print-ready, RTL-aware PDF using the
  Vazirmatn font and headless Chrome. Built for Persian/Farsi documents (works for
  LTR too): renders headings, tables, lists, code, blockquotes, and an optional YAML
  frontmatter block into a clean A4 layout. Fonts are fetched once on first use
  (pinned Vazirmatn `v33.003` via jsDelivr) into `~/.cache/yar/md-to-pdf/` — keeping
  the repo binary-free — and degrade gracefully to system fonts when offline.

## [2.0.0] - 2026-06-02

A professional overhaul of the repository. No breaking change to how skills are
invoked — the major bump marks the structural, tooling, and presentation milestone.

### Added

- `LICENSE` (MIT) — the license was declared in the manifests but never shipped as a file.
- `SECURITY.md` — private vulnerability reporting policy and component scope.
- `CODE_OF_CONDUCT.md` — Contributor Covenant 3.0.
- `CHANGELOG.md` — this file.
- Test suite under `tests/` that turns each guard's documented edge cases into
  executable specs (standard-library `unittest`, zero runtime dependencies).
- Continuous integration (`.github/workflows/ci.yml`): ShellCheck, Ruff, the test
  suite, JSON manifest validation, per-skill validation (dogfooding `validate.py`),
  and markdownlint.
- Issue forms and a pull-request template under `.github/`, plus a Dependabot
  config for GitHub Actions.
- `.editorconfig` and `.gitattributes` for consistent formatting and line endings.
- `$schema` and `displayName` in the plugin and marketplace manifests for editor
  validation and a friendlier display name.

### Changed

- Migrated `install-guards` and `install-perms` from `commands/` to `skills/`
  (with `disable-model-invocation: true`) — the current Claude Code convention now
  that custom commands have merged into skills. Invocation is unchanged
  (`/yar:install-guards`, `/yar:install-perms`).
- Renamed `skills/meeting-recorder/references/` to `reference/` to match every
  other skill and the Agent Skills convention.
- Rewrote `README.md` into a scannable, badge-topped catalog with one source of
  truth per skill.
- Expanded `CONTRIBUTING.md` with development, testing, and linting instructions.

### Fixed

- `git-guard` no longer false-positives on a `git commit -m` message that begins
  with `-` and contains an "a" (it was being read as the `-a` flag). A fail-open
  guard must never block a legitimate commit. Caught while dogfooding; covered by a
  regression test.
- Two ShellCheck warnings in the meeting scripts (`SC2064` trap quoting, `SC2034`
  unused loop counter) and a broken in-page link in `skill-builder` `reference/`.
- `.gitignore` now excludes `.claude/settings.local.json` (machine-local) and
  `.env` (secrets).

## [1.6.1] - 2026-06-02

### Changed

- `git-workflow`: added a per-session ownership check — stage and commit only the
  files this session changed, leaving any concurrent session's work untouched.

## [1.6.0] - 2026-06-02

### Added

- `perms-guard` PreToolUse hook (blocks force-recursive deletes such as `rm -rf`
  and `docker rm -f`) and the `/yar:install-perms` command that merges an
  allow/deny permission policy into a repo's `.claude/settings.json`.

## [1.5.0] - 2026-06-02

### Added

- `meeting-processor`: opt-in routing of action items, decisions, and status
  updates into the project's own tools (task system, calendar, decisions record).

## [1.4.2] - 2026-06-02

### Added

- `context-guard` hook and the `no-context` CI check to keep the repository
  generic and public (no private emails, home paths, or secrets).

## [1.4.1] - 2026-06-02

### Changed

- Made the repository English-only and added the `english-guard` hook to enforce it.

## [1.4.0] - 2026-06-02

### Added

- `meeting-recorder` skill — audio-only macOS meeting capture via a self-built
  CoreAudio process-tap recorder.
- `meeting-processor` skill — transcription with ElevenLabs Scribe v2, plus
  summary, decisions, and action-item extraction.

## [1.3.0] - 2026-06-02

### Added

- `organize-files` skill — a project-agnostic engine for naming, deduplicating,
  best-version selection, safe deletion, and README upkeep.

## [1.2.0] - 2026-06-02

### Added

- `file-inspector` agent — deep, full-content single-file inspection returning a
  structured report.

## [1.1.0] - 2026-06-02

### Added

- `gemini-research` skill and its paired `gemini-researcher` agent — deep,
  multi-source web research via the Gemini CLI.
- `skill-builder` skill — author, validate, and package Agent Skills to standard.

## [1.0.0] - 2026-06-02

### Added

- Initial release: the `yar` plugin and its single-repo marketplace.
- `git-workflow` skill with the `git-guard` and `branch-guard` Claude Code hooks,
  the git-level `pre-commit` guard, and the `/yar:install-guards` command.

[Unreleased]: https://github.com/rajool/yar/compare/v2.9.0...HEAD
[2.9.0]: https://github.com/rajool/yar/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/rajool/yar/releases/tag/v2.8.0
