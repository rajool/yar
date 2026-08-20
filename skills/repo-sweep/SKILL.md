---
name: repo-sweep
description: End-of-day sweep across every local git repo, worktree, and installed Claude Code plugin at once. Reconciles each repo with its remote (pushes committed work, fast-forward pulls, surfaces divergence and dirty trees, never discarding them), prunes stale state — local branches whose content already landed on the default branch (squash-merge aware), merged or contained worktrees, orphaned worktree directories from repo renames, primaries parked on a merged branch, zero-unique remote branches — and updates every installed plugin to its latest published version, flagging manifest/install version drift. Read-only scan, then a classified plan (safe / needs-you / skipped); mutations only on confirmation. Use on "sweep the repos", "wrap up the day", "end of day", "good night", "clean up branches and worktrees", "any stale branches?", "update all plugins", or Persian "شب بخیر", "جمع‌وجور کن", "برنچ‌ها و ورک‌تری‌های الکی رو پاک کن", "پلاگین‌ها رو آپدیت کن".
---

# repo-sweep — end-of-day sweep: repos, branches, worktrees, plugins

Goal: one move at the end of the day (or whenever asked) that leaves **every** local
git repo reconciled with its remote, **every** stale branch/worktree accounted for, and
**every** installed Claude Code plugin on its latest published version — across all
repos at once, so nothing quietly drifts, rots, or gets left behind. ("When" lives in
the description; "how" is here.)

This skill mutates many repos, so it always runs in phases: **scan (read-only) → plan
(classified) → confirm → act → re-scan → report**. A bare "good night" therefore never
destroys anything before you have seen what it intends to do. It never runs on a
schedule or on its own initiative — only when invoked. Per-repo mechanics (branching,
conventional commits, rebase, conflict recovery) belong to **`yar:git-workflow`**; this
skill orchestrates across repos and hands a stuck repo to git-workflow rather than
reinventing it.

## 0) Scan — read-only, always first

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/repo-sweep/scripts/sweep-scan.sh" --fetch
```

`--fetch` updates remote-tracking refs only (never files); without current refs the
merged/gone/behind signals below cannot be trusted. **Scan roots** (first source that
yields anything wins): `ROOT` arguments → `$DAILY_REPO_ROOTS` (colon-separated, `~`
allowed) → the defaults `~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer`;
depth is `$DAILY_SCAN_DEPTH` (default 4). Confirm the root list with the user on the
first run.

The output is typed rows (the script's `--help` documents every column): per-checkout
sync state (`repo`/`worktree`), worktree facts (`WT`), local branch classification
(`BRANCH`: `MERGED` = ancestor of the default branch, `EQUIV` = every commit
patch-equivalent to one already there — how a squash-merged branch looks, `UNIQUE(N)` =
N commits found nowhere else), remote branch staleness (`RBRANCH`), orphaned worktree
directories (`ORPHAN`), primaries parked off the default branch (`PARKED`), and plugin
manifest drift (`PLUGDEV`). If `SUMMARY` shows `fetch-failures>0`, say so and treat
those repos as read-only — stale refs must not drive deletions. Never invent state.

## 1) Build the plan — classify every finding

Sort every row into three buckets and show the user the plan as a short table before
touching anything. Where the repo is on GitHub and `gh` is available, check open PRs
first (`gh pr list --state open --json headRefName,number` per repo, best-effort) — a
branch with an open PR is never stale, whatever the numbers say.

- **Safe** (batch; one confirmation covers them): push ahead-clean checkouts;
  fast-forward behind-clean ones; delete local `MERGED`/`EQUIV` branches that are not
  checked out anywhere and have no open PR; remove clean worktrees whose HEAD is
  contained in the default branch (or whose branch is `MERGED`/`EQUIV`/upstream-`gone`);
  switch a parked primary back to the default branch when its current branch is
  `MERGED`/`EQUIV` and the tree is clean; delete remote branches with `UNIQUE=0` and no
  open PR; update installed plugins.
- **Needs you** (list, don't touch): dirty trees (name the files), `UNIQUE` branches
  (show the commits via `git cherry`), stashes, detached primaries, diverged histories,
  orphaned worktree dirs (git cannot prove they hold no unsaved work — a human look
  first), and dev clones whose version is ahead of the installed plugin (unreleased
  work: merge + release needed).
- **Skipped** (say why): the checkout the session is standing in, branches with open
  PRs, never-pushed branches (`UPSTREAM=none` on a worktree = work in progress).

## 2) Reconcile sync state

Work each `repo`/`worktree` row by its state — ahead/behind/diverged/dirty/stash —
using the exact commands and the full decision matrix in `reference/playbook.md`.
Essentials: `push` what is ahead; `pull --ff-only` what is behind; rebase-then-
`push --force-with-lease` what diverged (stop and hand conflicts to git-workflow);
offer a conventional commit for dirty trees (stage explicit paths only — never
`git add -A`/`.`, the git-guard blocks it); list stashes; never discard anything.

## 3) Prune stale branches and worktrees

Order matters: worktrees first (a branch checked out in a worktree cannot be deleted),
then local branches, then remote branches, then `git worktree prune`. Exact commands,
the `-d`/`-D` rule, the orphan-dir repair-or-trash protocol (`git worktree repair` when
the admin dir survives; move to `~/.Trash` — never `rm -rf` — when it is dead), and the
parked-primary recipe are in `reference/playbook.md`. Remote-branch deletion is
outward-facing: list each one explicitly in the plan and delete only after the
confirmation, with `git push origin --delete <branch>`.

## 4) Bring every plugin up to date

Installed plugins are refreshed, not reconciled — there is nothing to push:

```bash
claude plugin marketplace update    # refresh every configured marketplace source
claude plugin list --json           # snapshot BEFORE: array of {id, version, ...}
# for each id:  claude plugin update <id>   # no built-in "update all" — loop
claude plugin list --json           # snapshot AFTER: diff = what actually moved
```

Report every plugin whose version moved, and remind the user a **Claude Code restart**
is needed for updates to take effect. Then close the loop with the dev clones the scan
found: a `PLUGDEV` row whose plugin.json version differs from the marketplace entry, or
a dev clone ahead of the installed version, means a release step was missed — surface
it under **needs you** with the fix (align the manifests / merge and release, via
git-workflow), rather than editing manifests as a side effect of the sweep.

## 5) Re-scan and report

Run the scan again (no `--fetch` needed if nothing remote changed besides your own
pushes). Every `ok` checkout should read `ahead=0 behind=0`, pruned branches and
worktrees should be gone, and the plugin snapshots should match their sources. End with
a compact summary: **Done** (per repo: pushed / pulled / branches deleted / worktrees
removed / plugins updated), **Needs you** (each item with its path and the one command
or decision it waits on), **Skipped** (with reasons). The honest "nothing left behind"
check is the re-scan, not a claim.

## Guardrails

- **Scan + plan before any mutation**; one confirmation for the safe batch, explicit
  per-item confirmation for anything irreversible or outward-facing (remote branch
  deletion, trashing an orphan dir). Never on a schedule, never unprompted.
- **Never discard work.** No `reset --hard`, no `checkout -- <file>` over dirty files,
  no `stash drop`, no `worktree remove --force`, no deleting a branch with unique
  commits, no `rm -rf` on orphan dirs (`~/.Trash` keeps them recoverable).
- Delete a branch only on proof its content is elsewhere: `MERGED`/`EQUIV` from the
  scan, or `UNIQUE=0` for remote branches — and never with an open PR.
- **Stage explicit paths only** (`git add -- <paths>`); the git-guard blocks bulk adds.
- Skip the checkout the session is standing in; report it instead.
- Stale refs (fetch failures) must never drive a deletion.
- Secrets and binaries never enter git; text / code / Markdown only.

## References

- `reference/playbook.md` — the full decision matrices (sync states, branch classes,
  worktree classes, orphan repair-or-trash, parked primaries, remote branches, the
  plugin loop), exact commands, offline handling, and how repo-sweep relates to
  git-workflow. **Read it before acting on any state that is not obvious.**
- `scripts/sweep-scan.sh` — the read-only auditor producing the typed rows above;
  `--help` documents roots, depth, and every column.
- Relies on **`yar:git-workflow`** for per-repo mechanics (commits, rebases, conflicts).
