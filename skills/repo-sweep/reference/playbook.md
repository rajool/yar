# repo-sweep playbook — decision matrices, edge cases, exact commands

Read this before acting on any state that is not obvious from the scan, or before a
command you are not certain preserves work. The governing rule: **reconcile by moving
commits and prune only what is provably elsewhere — never overwrite or guess.**
Everything committed gets pushed; everything remote gets pulled; a branch or worktree
is deleted only on proof its content already lives on the default branch; anything
that cannot be proven is **surfaced, not destroyed**.

`<path>`/`<repo>` below come from the scan rows; commands use `git -C` so you never
have to `cd` (and never lose the checkout you are standing in).

## Sync states (the `repo`/`worktree` rows)

Resolve in this order — upstream first, then divergence, then dirtiness, then stashes:

| UPSTREAM | DIRTY | AHEAD | BEHIND | Meaning | Action |
|---|:--:|:--:|:--:|---|---|
| `ok` | 0 | 0 | 0 | in sync | nothing |
| `ok` | 0 | 0 | >0 | behind only | `git -C <path> pull --ff-only` |
| `ok` | 0 | >0 | 0 | ahead only | `git -C <path> push` |
| `ok` | 0 | >0 | >0 | diverged | `fetch` → `rebase @{u}` → `push --force-with-lease` |
| `ok` | >0 | * | 0 | local edits | offer a conventional commit (confirm) → `push` |
| `ok` | >0 | * | >0 | edits **and** behind | commit (confirm) → `rebase @{u}` → `push --force-with-lease` |
| `none` | * | – | – | never pushed | **ask** before `push -u origin HEAD`; on a worktree, treat as work-in-progress and skip the sweep |
| `gone` | 0 | * | * | upstream deleted (merged) | prune candidate — see worktrees/branches below |
| `gone` | >0 | * | * | merged upstream **but** dirty | do not remove; surface the dirty files first |
| any | * | – | – | `BRANCH = DETACHED` | surface; do not guess a branch |

`*` any value · `–` not meaningful.

**Dirty trees** — uncommitted work a push cannot carry. Do not pull or rebase onto it.
List the exact paths, propose a conventional-commit message from the diff, and only on
confirmation (branch first if it sits on `main`, per git-workflow):

```bash
git -C <path> status --porcelain
git -C <path> add -- <path1> <path2> ...   # never add -A / add . / add -u (git-guard blocks it)
git -C <path> commit -m "type(scope): summary" -- <path1> <path2> ...
git -C <path> push
```

**Diverged** — replay local commits on top, then push. `--force-with-lease` (never
`--force`) aborts if the remote moved meanwhile:

```bash
git -C <path> fetch && git -C <path> rebase @{u} && git -C <path> push --force-with-lease
```

**Conflicts** — repo-sweep does not auto-resolve across many repos. Stop on that repo,
`git -C <path> rebase --abort` to leave it clean (or resolve now via git-workflow's
conflict recipe), report it under "needs you", and continue the sweep on the others.

**Stashes** — local-only state a push cannot save. `git -C <path> stash list`, report
so they are not forgotten, never `drop`/`clear`/`pop` unprompted.

## Local branches (the `BRANCH` rows)

| STATE | Proof | Action |
|---|---|---|
| `MERGED` | ancestor of `origin/<default>` | delete: `git -C <repo> branch -d <name>` |
| `EQUIV` | every commit patch-equivalent upstream (`git cherry` shows no `+`) — the squash-merge signature | delete: `git -C <repo> branch -D <name>` (`-d` refuses: git cannot see a squash as merged; the scan's EQUIV **is** the proof) |
| `UNIQUE(N)` | N commits whose content is nowhere on the default branch | **never auto-delete.** Show them (`git -C <repo> cherry -v origin/<default> <name>` or `log --oneline origin/<default>..<name>`) and let the user decide: merge it, keep it, or explicitly discard |
| `DEFAULT(behind=N)` | the default branch itself | never delete; if behind and not checked out: `git -C <repo> fetch origin <default>:<default>` (fast-forwards without a checkout) |

Skip — whatever the state — any branch that is **checked out** somewhere
(`CHECKEDOUT=yes`; remove/switch the checkout first) or has an **open PR**. Deleting a
local branch touches nothing remote and stays recoverable via `git reflog` for ~90
days, which is why `MERGED`/`EQUIV` deletions may batch under one confirmation.

## Worktrees (the `WT` rows)

Remove from the **primary checkout**, never from inside the worktree (your cwd would
vanish). A worktree is removable when it is **clean** (`DIRTY=0`) and any of:

- `CONTAINED=yes` — its HEAD (branch or detached) is an ancestor of the default branch;
- its branch is `MERGED`/`EQUIV` in the `BRANCH` rows;
- its branch's upstream is `gone` (deleted on the remote after a merge).

```bash
git -C <repo> worktree remove <path>    # refuses if dirty — investigate, never --force
git -C <repo> branch -d <branch>        # then its branch, -D if EQUIV
git -C <repo> worktree prune            # drop stale admin entries (also for PRUNABLE=yes)
```

Never sweep a worktree that is dirty (surface the files), on a never-pushed branch
with unproven content (work in progress), or the one the session is standing in.

## Orphaned worktree directories (the `ORPHAN` rows)

Directories under `<repo>/.claude/worktrees/` that git no longer lists. The classic
cause: the parent repo was **renamed**, so the dir's `.git` file points at
`<old-path>/.git/worktrees/<id>` and every git command inside fails.

- **`REPAIRABLE=yes`** (the admin dir still exists under some repo's `.git`): run
  `git -C <repo> worktree repair <path>`, re-scan, and the entry becomes a normal `WT`
  row — classify it as above (this recovers its dirty state honestly).
- **`REPAIRABLE=no`** (the admin dir is gone): a dead plain directory. Git cannot say
  whether it holds unsaved work, so **look first** (files newer than the last commit,
  anything outside the tracked tree), show the user its size/file count, and only on
  explicit confirmation move it to the Trash — recoverable, unlike `rm -rf`:

```bash
mv <orphan-dir> ~/.Trash/"$(basename <orphan-dir>)-$(date +%Y%m%d%H%M%S)"
```

## Parked primaries (the `PARKED` rows)

A primary checkout left standing on a non-default branch. If that branch is
`MERGED`/`EQUIV` and the tree is clean: `git -C <repo> switch <default>` then
`git -C <repo> pull --ff-only`, after which the old branch joins the prune list. If
the branch is `UNIQUE` or has an open PR, leave it parked — just fast-forward the
local default branch alongside: `git -C <repo> fetch origin <default>:<default>`.

## Remote branches (the `RBRANCH` rows)

`UNIQUE=0` means the default branch already contains everything (by content, so
squash-merged branches qualify). Deleting is **outward-facing**: list each candidate in
the plan, check open PRs (`gh pr list --state open --json headRefName,number` — a PR
head is never deleted; GitHub would close the PR), and only after confirmation:

```bash
git push origin --delete <branch>
```

`UNIQUE>0` remote branches are decisions, not chores: show their age and unique
commits and let the user choose. Never delete the default branch or `origin/HEAD`.

## Plugins

Two layers, treated differently:

- **Dev clones** (plugin source repos under a scan root) are ordinary repos — the sync
  and prune phases above already cover them. The scan adds `PLUGDEV` rows: plugin.json
  version vs the matching marketplace.json entry. A mismatch means a release skipped a
  manifest — surface it; fixing manifests is a git-workflow change (branch → commit →
  PR), never a silent side effect of the sweep.
- **The installed cache** is downstream of a marketplace: refreshed, not reconciled.

```bash
claude plugin marketplace update    # refresh every configured marketplace source
claude plugin list --json           # BEFORE snapshot: [{id, version, ...}]
# for each id:
claude plugin update <id>           # no built-in "update all" — loop over the ids
claude plugin list --json           # AFTER snapshot — the diff is the report
```

Cross-check the layers after updating: for a plugin whose dev clone the scan saw,
compare the installed version with the clone's plugin.json — **installed < clone**
means unreleased work (merge + release needed, or the marketplace serves a stale
version); **installed > clone** means the clone is behind (the sync phase's pull fixes
it). Updates take effect on the next **Claude Code restart** — always say so.

## Scan roots, depth, offline

Roots resolve in order: `ROOT` arguments → `$DAILY_REPO_ROOTS` (colon-separated, `~`
allowed) → defaults (`~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer`).
Depth: `$DAILY_SCAN_DEPTH` (default 4). The scan prunes `node_modules`, `.venv`,
`venv`, `vendor`, `Pods`, `.terraform`, `.tox`, `.Trash`, `Library`. A primary repo is
a directory containing a `.git` **directory**; linked worktrees (a `.git` **file**) are
enumerated via their parent, each checkout exactly once. Paths are compared
case-insensitively (macOS filesystems).

If the scan reports `fetch-failures>0`, those repos' merged/gone/behind signals are
stale: report which failed, finish the sweep on the repos that did fetch, and never
push, prune, or delete from stale refs. Never invent or assume remote state.

## Relationship to git-workflow

repo-sweep is the **breadth** (every repo, end of day); `yar:git-workflow` is the
**depth** (one repo, done right). The sweep leans on git-workflow's rules —
explicit-pathspec commits, rebase-not-merge, `--force-with-lease`, conflict recipes —
rather than duplicating them. When one repo needs real attention (a gnarly conflict, an
accidental commit on `main`), switch to git-workflow for that repo, then come back and
finish the sweep.
