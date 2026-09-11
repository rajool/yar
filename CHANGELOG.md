# Changelog

All notable changes to **yar** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Plugin releases are driven by the `version` field in
[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json): users receive an update
only when it is bumped.

## [Unreleased]

## [4.5.2] - 2026-09-11

### Changed

- **Generic throughout, ahead of the repository going public.** Examples and
  documentation no longer name any person, company, place, machine or private
  tool: illustrative names are fictional, the development checkout is a
  placeholder path, and the copyright and author fields carry the maintainer's
  handle. The git history was squashed to a single root commit, as at 2.8.0;
  the version history lives in this file.
- **`context-guard` reads more than files.** The no-context guard now also
  flags a home-relative path into a specific project (`~/Projects/<repo>`; a
  bare root such as `~/Projects` is fine) and, as a `PreToolUse(Bash)` hook,
  the text of `git commit -m` and `gh pr create|edit` commands, so a private
  term cannot ride into a commit message or a pull-request body. The
  `no-context` workflow scans the pull request's title and body too, and the
  same `--scan` mode serves a `commit-msg` git hook for commits made outside
  Claude. `noreply` senders (bots, GitHub's privacy address) are recognised as
  non-personal.

## [4.5.1] - 2026-09-10

### Fixed

- **Four skills and one agent were loading with no metadata at all.**
  `chrome-devtools`, `daily-log`, `git-workflow`, `meeting-processor` and the
  `file-inspector` agent each had a `description:` written as an unquoted YAML
  scalar containing `": "` -- inside a plain scalar YAML reads that as a nested
  mapping and rejects the whole block. The loader's response to unparseable
  frontmatter is not to complain but to drop **every** field, so those five
  shipped with no name, no description and no triggers: they never fired on
  their own, and nothing on disk looked wrong. All five descriptions are now
  single-quoted, byte-for-byte the same text.
- **The validator that was supposed to catch this said PASS.**
  `skill-builder`'s `validate.py` called PyYAML inside a bare
  `except Exception`, so a *parse error* fell through to the lenient
  `key: value` fallback meant only for a machine with no PyYAML installed --
  the fallback read the broken frontmatter happily and reported no issues. A
  YAML error is now a hard validation error naming the line and column, the
  fallback is reached only on `ImportError`, and CI installs PyYAML so the
  strict path always runs. Covered by `tests/test_skill_validator.py`.

### Added

- **A release gate in CI, and tagging that is no longer a thing to remember.**
  `claude plugin tag --dry-run` now runs on every pull request: it is the only
  check that reads the repo the way Claude Code does, failing on frontmatter
  the loader cannot parse and on a `plugin.json` version that disagrees with
  the marketplace entry. A new `release.yml` cuts and pushes the
  `yar--v<version>` tag (and a GitHub release from this file) whenever a merge
  to `main` lands a version that has no tag yet -- yar had drifted nine
  versions past its newest tag before this existed.

## [4.5.0] - 2026-09-09

### Added

- **Aliases: your own word for a whole workflow, applied by a hook instead of
  by memory.** A routine you run daily ends up with a nickname, and a nickname
  left to memory degrades -- sometimes the skill runs, sometimes an improvised
  half of it does, and the difference only surfaces afterwards. The new
  `alias-guard` (`UserPromptSubmit`) reads an alias table you own and, when a
  prompt uses one of your words, hands Claude the mapping: which skill to
  invoke, what the alias covers, and that it is to be run in full rather than
  approximated. An entry is `{"words": [...], "run": "yar:repo-sweep", "do":
  "...", "ship": false, "note": "..."}`; the table is read from
  `~/.claude/yar-aliases.json` (personal, every project) and
  `<project>/.claude/yar-aliases.json` (that project only), later wins, with
  `$YAR_ALIASES` overriding the search and `YAR_ALIASES=off` /
  `ALIAS_GUARD=off` disabling it. **yar ships no aliases** -- the mechanism is
  generic, the words stay personal, and the hook is silent until you write a
  table (`alias-guard.sh example > ~/.claude/yar-aliases.json`, then
  `alias-guard.sh list` to see what is active and where it came from).
  Matching is whole-phrase only and script-aware, so a trigger never fires
  inside a longer word in Latin *or* Arabic script, and Persian triggers
  tolerate ZWNJ, harakat, and Arabic-vs-Persian yeh/kaf spelling; in a long
  prompt the word still only counts near the start or the end, so a pasted
  document that merely mentions it does nothing. Covered by
  `tests/test_alias_guard.py`.
- **A ship alias is bound by the ship contract.** An alias marked
  `"ship": true` is adopted by `ship-guard` as a trigger word, so a personal
  word for shipping arms the same "not finished until the PR is `MERGED`" Stop
  contract the word "ship" arms -- routing and enforcement come from one line
  in one file, not from two settings that can drift apart.

### Fixed

- **`ship-guard`: a non-Latin trigger word is now bounded correctly.**
  `SHIP_GUARD_WORDS` accepted any language, but the boundary test was
  `[A-Za-z]` lookarounds, to which every Persian letter looks like a word
  boundary -- so a Persian trigger also matched inside a longer Persian word.
  Boundaries are now script-aware (`scripts/yar_aliases.py`), Latin and
  Arabic-script alike.

## [4.4.0] - 2026-09-09

### Added

- **`repo-sweep`: the scan sees which checkouts a live process is standing
  in, and the sweep never removes one.** `sweep-scan.sh` takes one
  `lsof +c 0 -a -d cwd -Fpcn` snapshot per run — read-only: every process the
  caller may inspect, with its working directory — and gives `WT`, `ORPHAN`
  and `PARKED` rows an `INUSE` column: `yes` when some process has its cwd at
  or below the path (compared case-insensitively, boundary-safe: `/foo` never
  matches `/foobar`), `no` when none does, `?` when there is no snapshot —
  `lsof` missing or failed — because unknown is not "no". Each in-use path is
  followed by one `INUSE REPO PATH PID COMMAND CWD` row per process, and
  `SUMMARY` gains `in-use=N` (or `?`). The skill and playbook add the rule: a
  worktree with `INUSE=yes` is never removed, an orphan dir never trashed, a
  parked primary never switched, whatever the merged-ness proof says — they
  are listed under "Skipped (in use by a live process; pid and command)";
  `INUSE=?` is needs-you, with a manual `lsof` one-liner. Covered by
  `tests/test_sweep_scan.py` (a fake `lsof` on PATH).
  Why: a sweep classified a clean, detached, contained worktree as removable
  while another Claude Code session — its shell and MCP servers — had its
  working directory inside it; removing it would have broken that session on
  every command. The only guard was "skip the checkout the session is
  standing in", which covers the sweeping session alone.

## [4.3.0] - 2026-09-09

### Added

- **`repo-sweep`: merged pull requests are proof — the scan now sees
  multi-commit squash merges.** `git cherry` recognizes a squash-merged branch
  only when it had one commit: the squash commit on the default branch carries
  the combined diff, so with two or more commits every patch-id misses and the
  branch read `UNIQUE(N)` although nothing on it was unmerged. `sweep-scan.sh`
  now makes one `gh pr list --state merged --base <default> --limit 500` call
  per GitHub repo and classifies a branch `PRMERGED(#N)` when a merged PR into
  the default branch vouches for it: its merge commit is an ancestor of the
  local `origin/<default>`, and no non-merge commit reachable from the tip is
  missing from both the default branch and the PR head — the tip is the PR
  head, is behind it, or only merges from the default branch follow it (a
  rebased or continued branch stays `UNIQUE`). Local branches, remote branches,
  worktree HEADs (a detached HEAD matches a PR by commit) and parked primaries
  all use it. Read-only and best-effort: no `gh`, no token for the host, a
  non-GitHub remote, or a failed call leaves that repo classified from git
  alone; `--no-pr` opts out. `PRMERGED` joins `MERGED`/`EQUIV` as proof for the
  skill's safe bucket (local `-D`, clean worktrees removable, parked primaries
  switched back); remote-branch deletion keeps its per-item confirmation.
  `SUMMARY` gains `pr-merged-local`, `pr-merged-remote` and `pr-proof` (`off`,
  or repos-answered/GitHub-repos). Covered by `tests/test_sweep_scan.py`.
  Why: in one user's end-of-day sweep 39 local branches read `UNIQUE`; a manual
  cross-check against merged PRs found 35 were the head of a merged PR, 2 more
  carried only merges from main after it, and 2 held real work — 37
  non-decisions under "needs you", plus 23 remote branches in the same state.

### Changed

- **`repo-sweep`: one vocabulary for every prune decision.** `RBRANCH` rows
  are now `RBRANCH REPO NAME STATE LASTCOMMIT` with the `BRANCH` states
  (`MERGED` / `EQUIV` / `PRMERGED(#N)` / `UNIQUE(N)`) instead of a bare unique
  count, and `WT CONTAINED` reads `yes` / `EQUIV` / `PRMERGED(#N)` / `no`
  instead of yes/no — a detached worktree on a squash-merged commit is no
  longer a "needs you" item. A rev the scan cannot resolve is `UNIQUE(?)`,
  never a proof. Remote-branch deletion is listed and confirmed per item in
  the skill text, outside the one-confirmation safe batch, as the guardrail
  already required.

## [4.2.0] - 2026-09-06

### Fixed

- **`typeset`: paper is Letter (8.5 x 11 in), not A4.** Two hardcoded A4
  dimensions made every PDF the skill produced an A4 page: `page.size`
  defaulted to `A4`, and the cover's height was `297 - margins`, A4's height
  in millimetres. On a North American printer an A4 layout is the paper that
  is not in the tray, and the shorter Letter page cost the last lines of a
  full one. The default is now `letter`, and the cover derives its height from
  the resolved paper (`theme.PAPER_MM` / `theme.page_mm`), so its foot no
  longer breaks onto a near-blank second page. Verified on the produced PDF's
  `/MediaBox` (612 x 792 pt), not on the CSS, which read correctly throughout
  while the output was wrong.
  Why: raised repeatedly against printed ops sheets, each time corrected
  per-document instead of at source.

### Added

- **`typeset --page-size letter|a4`.** A4 stays one flag away for a document
  printed outside North America; a theme can still set `page.size` (now also
  `legal`, `a5`, or an explicit `"215.9mm 279.4mm"`) for a whole project. The
  flag is case-insensitive and merges over the theme's page block, so the
  margins survive it. `--describe` now prints a `paper` line with the resolved
  size and margins.

## [4.1.0] - 2026-09-06

### Added

- **`ship-guard`: "ship" now mechanically means merged.** Three new plugin hooks
  make the git-workflow contract hold without relying on prose. When a prompt
  says "ship", a `UserPromptSubmit` hook arms a per-session marker and injects
  the full chain (commit → push → `gh pr create` → `gh pr merge --squash` →
  verify `MERGED`); a `PostToolUse(Bash)` hook records every PR URL that
  `gh pr create` prints and nudges, right there, that the job is not done; and
  a `Stop` hook refuses to end the turn — up to three times — while a recorded
  PR is not `MERGED`, the branch has commits with no PR or after the merged PR,
  commits are unpushed, or nothing was committed at all. It checks reality with
  `gh pr view` and `git`, releases itself once the PR is merged, fails open
  (no `gh`, offline, not a repo → allow, marker kept), and has one explicit,
  auditable escape hatch — `scripts/ship-guard.py release --marker <path>
  --reason "<why>"` — whose reason must be repeated to the user. State lives
  under `$XDG_STATE_HOME/yar/ship-guard` (default `~/.local/state/…`); bypass
  with `SHIP_GUARD=off`; extra trigger words via `SHIP_GUARD_WORDS`.
  Why: across 96 "ship" requests in one user's session transcripts, dozens
  ended at `gh pr create` with "Shipped: PR #N" and the PR still open — with
  the written rule already in the skill (tightened on 2026-07-02 and
  2026-08-23). A rule the model reads is advice; a Stop hook is a contract.

### Changed

- **`git-workflow`: the "ship" section is state-only and names the guard.**
  The word "shipped" is reserved for `state == MERGED`; the skill documents the
  ship-guard hooks and the release escape hatch; the incident history moved to
  this changelog.
- **`repo-sweep`: the plugin loop updates every install scope, not just
  `user`.** `claude plugin update` touches one scope per call (user by
  default), and every project or worktree that enables a plugin in its own
  `.claude/settings*.json` carries a separate install record pinned to the
  version current when it was enabled. The skill and playbook now loop over the
  `scope`/`projectPath` rows of `claude plugin list --json` and run
  `--scope project|local` from each project directory, so a release actually
  reaches every project (the 2026-08-23 ship fix never left the user scope).

## [4.0.1] - 2026-09-04

### Changed

- **`locales` carries a register, not just an identity.** A per-language block
  in the theme may now set `mood`, `fonts`, `weights`, `table`, `page`,
  `base_size_pt`, `line_height`, `ink` and `accent` alongside the identity
  fields, so a project that writes formal Persian and light, modern English
  keeps both house styles in one theme file and lets each document's `lang:`
  pick.

### Fixed

- The deck sample tripped the repo's Markdown lint (an `h6` eyebrow above an
  `h2` slide title is the deck syntax); the sample now says so and is exempt.

## [4.0.0] - 2026-09-04

### Changed

- **`md-to-pdf` is now `typeset` — a document design system, not a converter.**
  The skill had outgrown its name: it designs the document (identity, type,
  weights, tables, statements, decks) and PDF is merely the output. The folder,
  the CLI (`scripts/typeset.py`; `md_to_pdf.py` stays as a compatibility entry
  point) and the font cache (`~/.cache/yar/typeset/fonts/`, an existing
  `md-to-pdf` cache is adopted) follow the new name. Invoke it as
  `/yar:typeset`. **Breaking:** project instructions that call
  `yar:md-to-pdf` should say `yar:typeset`.

- **Weights, not bold.** Each mood now names a full weight set — display,
  heading, body, emphasis, label — and `<strong>` sets at the *emphasis*
  weight, one step above the body, instead of 700. Table heads, eyebrows and
  meta labels take the label weight. A theme overrides any role under
  `weights` (`{"body": 300, "heading": 500, "emphasis": 500}`), which is how a
  project asks for a lighter page. The `modern` mood now pairs Inter (text and
  display) with IBM Plex Mono; Geist remains in the catalogue.

- **A table register.** Every Markdown table is classified after conversion
  (`scripts/tables.py`): numeric columns are right-aligned in tabular lining
  figures with the header, tables that are mostly figures drop the rules
  between ordinary rows while text tables keep a hairline, a bold label row in
  a numeric table is set as a total (rule above, emphasis weight; the last one
  double-ruled), short tables stay whole on a page and a total row never
  starts a page. Table type is a step smaller than the prose (`table.size_em`,
  default 0.86). Author classes are preserved.

- **Financial statements.** `scripts/statements.py` renders sections, groups,
  indented items, group sub-totals, key lines and a double-ruled final line
  from plain rows, with statement conventions for figures (whole, grouped,
  negatives in parentheses, nil as a dash, blank elimination cells) and
  footnote markers; `scripts/quickbooks_export.py` reads a QuickBooks Online
  report export (profit and loss, balance sheet, by entity) into a checked
  tree for it. Reference: `reference/tables-and-statements.md`.

- **Decks.** `kind: deck` sets the same design on 16:9 pages, one slide per
  page, split at horizontal rules, with a title slide from the frontmatter, an
  `h6` eyebrow, column and tile helpers (`cols-2/3/4`, `.tile`, `.stat`) and a
  generated slide foot. Geometry under the theme's `deck` field. Reference:
  `reference/decks.md`.

- **Per-language identity.** A theme's `locales` block carries the tagline,
  contact line and classification in more than one language; the document's
  own `lang:` frontmatter picks the set, so one theme file serves a project
  that writes in two languages.

- Paragraphs keep three lines together at a page break (was two); footnote
  markers (`<sup>`) are set small at the body weight.

### Fixed

- Numeric table cells that already carried a class were given a *second*
  `class="num"` attribute, which the parser drops — so an author's (or a
  script's) table classes vanished and their numbers fell back to
  left-aligned proportional figures. Classes are now merged.

## [3.2.0] - 2026-09-01

### Changed

- **`md-to-pdf` v2 — a per-project house style instead of one template
  everywhere.** The renderer now reads a **theme file** from the *host* project
  (`.claude/pdf-theme.json`) carrying that project's identity (name, tagline,
  contact line, logo), its ink and single accent, a type pairing chosen by a
  one-word **mood** (`modern` `formal` `editorial` `technical` `warm`
  `classic`), page geometry and locale — so the same skill produces a different,
  internally consistent identity in every project, derived from that project's
  own README, manifest, design tokens and logo rather than invented. `--describe`
  prints the resolved theme before rendering; with no theme file a monochrome
  default applies.

  The design itself was rebuilt on print-typography practice: **black ink, no
  decorative colour**, hierarchy carried by **font weight and whitespace**, and
  an accent that is *derived* for print (darkened along its own hue until it
  clears 4.5:1 on white) and used on at most four elements. A real **cover page**
  or, for `kind: letter`/`memo`, a **letterhead** is built from the document's
  frontmatter — which is no longer dumped on the page as a monospace block — plus
  a running head and a folio via `@page` margin boxes, both suppressed on the
  cover. Asymmetric canon margins, a held measure, three visible heading levels,
  `booktabs`-style tables (horizontal hairlines only, no vertical rules, no
  stripes, tabular figures), and fragmentation control (no stranded headings, no
  split tables, repeating table heads).

  **Persian and RTL typography is now first-class rather than a font swap.**
  The Persian family is primary and owns digits, punctuation and the zero-width
  non-joiner, while the Latin family is layered on with a letters-only
  `unicode-range` and a `size-adjust` computed from the two measured x-heights,
  so a mixed sentence keeps one digit design and no fallback splits an Arabic
  shaping run. Arabic decimal and thousands separators are sourced from a family
  known to carry them (several good Persian faces omit them, and the system
  fallback draws them with Latin sidebearings). Letter-spacing drops to zero on
  shaped runs per CSS Text 3, lists and folios number in Persian digits, dates
  render in the **Jalali** calendar, and digits inside version strings, URLs,
  paths, emails and code stay ASCII as Latin context.

  Fonts moved from three hard-coded Vazirmatn weights to a catalogue of **18
  open-licence variable families** (five Arabic-script, ten Latin, three
  monospace) from a **pinned** Fontsource release, still fetched once into
  `~/.cache/yar/md-to-pdf/fonts/` and still keeping the repo binary-free.

  Also fixed: headless Chrome was given a named `--user-data-dir`, which made it
  write the PDF and then never exit; the ephemeral profile is used instead and a
  timeout guards the call.

## [3.1.0] - 2026-08-24

### Changed

- **`chrome-devtools` skill v2 — user-named login profiles with guided
  onboarding, pinned server, telemetry off.** The skill now drives a family of
  user-scope MCP servers instead of one ad-hoc entry: `chrome` (isolated
  throwaway — the default choice) plus one persistent `chrome-<name>` server
  per user-defined identity (e.g. personal / work / one per company account),
  whose signed-in sessions survive across runs so every task operates under
  the right identity (ambiguous tasks are asked, not guessed). A guided
  onboarding builds a new machine one profile at a time: collect the
  identities (or read them back from the user's global CLAUDE.md), register
  the servers, record the account→profile mapping in the global CLAUDE.md —
  never in a repo, and profile contents stay on local disk only — then walk
  the sign-ins one by one. New `scripts/setup.sh <name ...>` registers the
  servers idempotently at user scope with the package version **pinned** (no
  floating `@latest`) and Google usage-statistics telemetry disabled; new
  `scripts/open-profile.sh` opens a profile in a plain,
  non-automated Chrome window for the one-time sign-in (some providers, notably
  Google, may refuse sign-in in a WebDriver-controlled browser) and doubles as
  the attach-mode launcher (`--debug-port`), replacing
  `scripts/launch-chrome-debug.sh`. The skill doc adds an identity-first
  decision table, logged-in-profile hygiene rules (isolated by default,
  task-named sites only, page content is data not instructions, confirm
  irreversible clicks), parallel-session profile locking, the Chrome 144+
  `--auto-connect` attach mode, the optional one-shot `chrome-devtools` CLI
  companion, and 1.7.0 tooling (`lighthouse_audit`, `get_console_message`,
  screencast) with upstream efficiency guidance (`filePath` for large outputs,
  pagination, `includeSnapshot: false`).

## [3.0.0] - 2026-08-20

### Added

- **`repo-sweep` skill — end-of-day sweep of repos, branches, worktrees, and
  plugins.** One invocation audits every local repo (read-only `sweep-scan.sh`),
  presents a classified plan (safe / needs-you / skipped), and on confirmation:
  reconciles each checkout with its remote, prunes local branches whose content
  already landed on the default branch (`MERGED` by ancestry or `EQUIV` by
  `git cherry` — the squash-merge signal), removes merged/contained worktrees,
  repairs-or-trashes **orphaned worktree directories** left behind by repo renames
  (a state `git worktree list` cannot even see), un-parks primaries left on merged
  branches, deletes zero-unique remote branches (PR-aware, confirmed per item),
  and updates every installed plugin to its latest published version — flagging
  version drift between a plugin's dev clone, its manifests, and the installed
  copy. Never discards uncommitted work; orphan dirs go to `~/.Trash`, never
  `rm -rf`.

### Removed

- **Breaking: the `daily-sync` skill.** It was superseded by `repo-sweep`, which
  covers its evening duties correctly and more deeply (daily-sync's sweep only saw
  worktrees whose upstream was `gone`, missing squash-merged branches with no or
  live upstreams, detached worktrees, orphaned worktree dirs, parked primaries,
  stale remote branches, and plugin version drift). The morning greeting routine
  is retired with it; `repo-sweep` is safe to run at any time of day and covers
  the pull + plugin-refresh duties. `$DAILY_REPO_ROOTS` / `$DAILY_SCAN_DEPTH`
  keep working unchanged.

### Fixed

- **`marketplace.json` had drifted from `plugin.json`** (entry pinned at 2.12.0
  with a stale description while the plugin was at 2.16.0), so installs were
  served stale metadata. Both manifests now carry the same version and
  description — and `repo-sweep` detects exactly this class of drift from now on.

## [2.16.0] - 2026-07-08

### Changed

- **Direction-aware cards: one BASE now styles both directions.** The card
  wrapper's `dir` attribute follows the reply language: `dir="rtl"` behaves
  exactly as before, and `dir="ltr"` (English replies, optional) flips text
  alignment, switches Vazirmatn for Inter, and mirrors the flow and CTA
  arrows through four override rules that ship inertly inside BASE. Ported
  from readable 4.4 production use; no new snippets and no size change for
  RTL replies.

- **`install-rtl` rule v2: the whole reply ships as one self-contained styled
  card.** The rule now carries a fixed `<style>` component kit the model copies
  verbatim (Vazirmatn, per-block direction, LTR-isolated code, KPI grids,
  CSS-only donut and bar charts, flow arrows, timelines, icon callouts, badges,
  a `sendPrompt` CTA), so styling is deterministic and polish costs class names
  instead of free-form HTML. Two zero-token alternatives were tested and
  rejected on Claude Desktop: a PreToolUse hook rewriting the widget input
  (`updatedInput` is ignored for MCP tools) and a CDN-loaded renderer (the
  widget sandbox does not execute external scripts, so the card renders blank).
  Re-run `/yar:install-rtl` to receive the new rule.
- **The kit is pay-per-use: always-on base plus per-component snippets,
  roughly 70% cheaper for prose replies.** The style kit does not ship whole
  with every reply. A 2.5KB BASE covers all text content (headings,
  paragraphs, lists, ok/no items, callouts, LTR-isolated code), and each
  component (table, badge, kv, kpi, bars, donut, flow, timeline, cta)
  carries its own CSS snippet the model appends only when the reply
  actually uses it. The six SVG data-URI icons are gone: check/cross became
  text glyphs and callouts use tint plus an accent border, removing the
  1.5KB of most mangling-prone bytes from the verbatim copy. Per-reply
  style cost: 8.8KB (~2.4k tokens) for the monolithic kit, 2.5KB (~0.7k)
  for prose replies, 7.1KB (~2k) worst case with every component. Review
  invariants are regression-tested: `display:inline-block` code isolation,
  `max(...,11px)` size floors (now on the table body too),
  palette-not-template composition, the `&rlm;` escape hatch, and the
  precise network wording.
- **Multiline code blocks render correctly.** BASE gains a `<pre><code>`
  rule: LTR block, monospace, bordered, horizontally scrollable, floored at
  11px like every other derived size. Persian dev answers routinely carry
  code blocks; previously they fell back to unstyled, BiDi-fragile text.

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
- Development paths in the README use a placeholder checkout path.

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
  Gemini API engines (billed key). The paired `gemini-researcher` agent
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

[Unreleased]: https://github.com/rajool/yar/compare/yar--v4.5.2...HEAD
[4.5.2]: https://github.com/rajool/yar/releases/tag/yar--v4.5.2
