---
name: repo-sweep
description: End-of-day sweep across every local git repo, worktree, and installed Claude Code plugin at once. Reconciles each repo with its remote (pushes committed work, fast-forward pulls, surfaces divergence and dirty trees, never discarding them), prunes stale state — local branches whose content already landed on the default branch (squash-merge aware, merged pull requests as proof), merged or contained worktrees, orphaned worktree directories from repo renames, primaries parked on a merged branch, zero-unique remote branches — and updates every installed plugin to its latest published version, flagging manifest/install version drift. Read-only scan, then a classified plan (safe / needs-you / skipped); mutations only on confirmation. Use on "sweep the repos", "wrap up the day", "end of day", "good night", "clean up branches and worktrees", "any stale branches?", "update all plugins", or Persian "شب بخیر", "جمع‌وجور کن", "برنچ‌ها و ورک‌تری‌های الکی رو پاک کن", "پلاگین‌ها رو آپدیت کن".
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
sync state (`repo`/`worktree`), worktree facts (`WT`, whose `CONTAINED` column is the
proof that the HEAD's content is on the default branch: `yes` / `EQUIV` /
`PRMERGED(#N)` / `TREESAME` / `no`, and whose `INUSE` column says whether a live process
is standing in it: `yes` / `no` / `?`), local branch classification (`BRANCH`: `MERGED` =
ancestor of the default branch, `EQUIV` = every commit patch-equivalent to one already
there — how a single-commit squash-merge looks, `PRMERGED(#N)` = pull request #N into the
default branch is merged and vouches for every commit on the branch — how a multi-commit
squash-merge looks, which `git cherry` cannot see, `TREESAME` = the tip's tree is
identical to the default branch's tree — the same work landed there in a different
commit shape (pushed directly as one combined commit, no PR), which neither patch-ids
nor the PR record can see; judged only where the three proofs before it failed,
`UNIQUE(N)` = N commits found nowhere else that no merged PR vouches for and whose tree
differs from the default branch's), remote branch classification (`RBRANCH`, same
vocabulary), orphaned worktree directories (`ORPHAN`), primaries parked off the default
branch (`PARKED`), and plugin manifest drift (`PLUGDEV`). If `SUMMARY` shows
`fetch-failures>0`, say so and treat those repos as read-only — stale refs must not
drive deletions. Never invent state.

The merged-PR proof needs `gh` with a token for the repo's host: the scan makes one
`gh pr list --state merged` call per GitHub repo and degrades to git-only
classification without it — `SUMMARY` reads `pr-proof=off`, or `pr-proof=Q/G` (Q of G
GitHub repos answered). When it is off or a repo did not answer, say so in the plan:
`UNIQUE` rows there may hide squash-merged branches, and the playbook has the manual
check. `--no-pr` turns the lookup off deliberately.

The in-use signal is one `lsof -a -d cwd` snapshot per run. `INUSE=yes` on a `WT`,
`ORPHAN`, or `PARKED` row means some process — another Claude Code session's shell and
MCP servers, an editor, a terminal — has its working directory at or below that path,
and one `INUSE REPO PATH PID COMMAND CWD` row follows for each such process. `INUSE=no`
means the snapshot holds none; `INUSE=?` means there was no snapshot (`lsof` missing or
failed; `SUMMARY` reads `in-use=?`) — unknown, never "no". Removing or trashing a
directory pulls it out from under every process standing in it (a Claude Code session
there fails on every command from then on), so the plan below never touches an in-use
path.

## 1) Build the plan — classify every finding

Sort every row into three buckets and show the user the plan as a short table before
touching anything. Where the repo is on GitHub and `gh` is available, check open PRs
first (`gh pr list --state open --json headRefName,number` per repo, best-effort) — a
branch with an open PR is never stale, whatever the numbers say. (Merged PRs are already
consumed by the scan as `PRMERGED`; open PRs are still this step's job.)

- **Safe** (batch; one confirmation covers them): push ahead-clean checkouts;
  fast-forward behind-clean ones; delete local `MERGED`/`EQUIV`/`PRMERGED`/`TREESAME`
  branches that are not checked out anywhere and have no open PR (quote the PR number
  next to a `PRMERGED` branch so the proof is visible); remove clean worktrees whose
  `CONTAINED` is `yes`/`EQUIV`/`PRMERGED`/`TREESAME` (or whose branch is
  `MERGED`/`EQUIV`/`PRMERGED`/`TREESAME`/upstream-`gone`) **and whose `INUSE` is
  `no`**; switch a parked primary back to the default branch when its current branch is
  `MERGED`/`EQUIV`/`PRMERGED`/`TREESAME`, the tree is clean, and `INUSE` is `no`; update
  installed plugins. Remote branches classified `MERGED`/`EQUIV`/`PRMERGED`/`TREESAME`
  with no open PR are deletion candidates too, but deletion is outward-facing: list each
  one and confirm it per item (step 3), never inside this batch. `TREESAME` sits in this
  bucket exactly like `EQUIV`, with one extra rule: **never open a PR for it** — the
  branch holds nothing the default branch lacks, so GitHub would squash-merge an empty
  commit.
- **Needs you** (list, don't touch): dirty trees (name the files), `UNIQUE` branches
  (show the commits via `git cherry`; if `pr-proof` was off or that repo did not
  answer, run the playbook's manual merged-PR check before calling the work unmerged;
  and before shipping one as a PR, the tree-equality check is the last thing to rule
  out — `git -C <repo> diff --quiet origin/<default> <tip>` staying silent means nothing
  on it is unique: delete it, never PR it; the playbook's *Tree-identical proof* has the
  historical variant), stashes, detached primaries, diverged histories,
  orphaned worktree dirs (git cannot prove they hold no unsaved work — a human look
  first), any `WT`/`ORPHAN`/`PARKED` row with `INUSE=?` (the scan could not probe
  processes; the playbook's `lsof` one-liner checks by hand), and dev clones whose
  version is ahead of the installed plugin (unreleased work: merge + release needed).
- **Skipped** (say why): the checkout the session is standing in, every path a live
  process is standing in (`INUSE=yes` — "in use by a live process", with the pid and
  command from its `INUSE` rows), branches with open PRs, never-pushed branches
  (`UPSTREAM=none` on a worktree = work in progress).

## 2) Reconcile sync state

Work each `repo`/`worktree` row by its state — ahead/behind/diverged/dirty/stash —
using the exact commands and the full decision matrix in `reference/playbook.md`.
Essentials: `push` what is ahead; `pull --ff-only` what is behind; rebase-then-
`push --force-with-lease` what diverged (stop and hand conflicts to git-workflow);
offer a conventional commit for dirty trees (stage explicit paths only — never
`git add -A`/`.`, the git-guard blocks it); list stashes; never discard anything.

## 3) Prune stale branches and worktrees

Order matters: worktrees first (a branch checked out in a worktree cannot be deleted),
then local branches, then remote branches, then `git worktree prune`. A worktree with
`INUSE=yes` is never removed, whatever its `CONTAINED` says — it stays listed under
Skipped with its pid and command until that process is gone. Exact commands,
the `-d`/`-D` rule (`-D` for `EQUIV`, `PRMERGED` and `TREESAME`: git itself cannot see a
squash or a re-shaped landing as merged — the scan's proof is what licenses it), the orphan-dir repair-or-trash protocol (`git worktree repair` when
the admin dir survives; move to `~/.Trash` — never `rm -rf` — when it is dead), and the
parked-primary recipe are in `reference/playbook.md`. Remote-branch deletion is
outward-facing: list each one explicitly in the plan and delete only after the
confirmation, with `git push origin --delete <branch>`.

## 4) Bring every plugin up to date

Installed plugins are refreshed, not reconciled — there is nothing to push:

```bash
claude plugin marketplace update    # refresh every configured marketplace source
claude plugin list --json           # snapshot BEFORE: [{id, version, scope, projectPath?, ...}]
# for each id:                       claude plugin update <id>                 # user scope (the default)
# for each row with scope project|local (each project and worktree has its OWN record):
#   (cd "<projectPath>" && claude plugin update <id> --scope <scope>)
claude plugin list --json           # snapshot AFTER: diff = what actually moved
```

`claude plugin update` touches **one scope per call**, and a plugin enabled in a
project's `.claude/settings.json` (or `settings.local.json`) has a separate install
record per project — and per worktree — pinned to the version current when it was
enabled. A user-scope update alone therefore leaves every project on the old version:
loop over every `scope`/`projectPath` row; skip rows whose `projectPath` no longer
exists and report them as stale records. Report every plugin whose version moved, and
remind the user a **Claude Code restart** is needed for updates to take effect. Then close the loop with the dev clones the scan
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
or decision it waits on), **Skipped** (with reasons — for an in-use path, the pid and
command standing in it). The honest "nothing left behind" check is the re-scan, not a
claim.

## Guardrails

- **Scan + plan before any mutation**; one confirmation for the safe batch, explicit
  per-item confirmation for anything irreversible or outward-facing (remote branch
  deletion, trashing an orphan dir). Never on a schedule, never unprompted.
- **Never discard work.** No `reset --hard`, no `checkout -- <file>` over dirty files,
  no `stash drop`, no `worktree remove --force`, no deleting a branch with unique
  commits, no `rm -rf` on orphan dirs (`~/.Trash` keeps them recoverable).
- Delete a branch only on proof its content is elsewhere: `MERGED`/`EQUIV`/`PRMERGED`/
  `TREESAME` from the scan, local and remote alike — and never with an open PR. `UNIQUE`
  is never deleted, and a merged PR the scan could not see is not a proof you may
  assume. A `TREESAME` branch is deleted, never shipped: a PR of it squashes to an empty
  commit.
- **Stage explicit paths only** (`git add -- <paths>`); the git-guard blocks bulk adds.
- Skip the checkout the session is standing in, and every path another live process is
  standing in (`INUSE=yes`): never remove, trash, or switch it, whatever its merged-ness
  proof says — report it with pid and command instead. `INUSE=?` is unknown, not `no`:
  needs you.
- Stale refs (fetch failures) must never drive a deletion.
- Secrets and binaries never enter git; text / code / Markdown only.

## References

- `reference/playbook.md` — the full decision matrices (sync states, branch classes,
  worktree classes, orphan repair-or-trash, parked primaries, remote branches, the
  plugin loop), exact commands, offline handling, and how repo-sweep relates to
  git-workflow. **Read it before acting on any state that is not obvious.**
- `scripts/sweep-scan.sh` — the read-only auditor producing the typed rows above;
  `--help` documents roots, depth, the merged-PR proof (`--no-pr` skips it), the
  tree-identical proof, the in-use probe, and every column.
- Relies on **`yar:git-workflow`** for per-repo mechanics (commits, rebases, conflicts).
