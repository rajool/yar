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
| `EQUIV` | every commit patch-equivalent upstream (`git cherry` shows no `+`) — the single-commit squash-merge signature | delete: `git -C <repo> branch -D <name>` (`-d` refuses: git cannot see a squash as merged; the scan's EQUIV **is** the proof) |
| `PRMERGED(#N)` | pull request #N into the default branch is merged, its merge commit is on `origin/<default>`, and every non-merge commit on the branch is inside the PR's head (the tip **is** the head, is behind it, or only merges from the default branch follow it) — the multi-commit squash-merge `git cherry` cannot see; see *Merged-PR proof* below | delete: `git -C <repo> branch -D <name>` (same reasoning as `EQUIV`; quote the PR number in the plan) |
| `TREESAME` | the tip's tree is byte-identical to `origin/<default>`'s (`git diff --quiet origin/<default> <name>` is silent) — the same work landed on the default branch in a different commit shape: pushed there directly as one combined commit, with no PR, so patch-ids miss it and no PR record vouches for it; judged only after the three proofs above failed — see *Tree-identical proof* below | delete: `git -C <repo> branch -D <name>` (as for `EQUIV`). **Never open a PR for it**: the branch holds nothing the default branch lacks, so GitHub would squash-merge an empty commit |
| `UNIQUE(N)` | N commits whose content is nowhere on the default branch, that no merged PR vouches for, and whose tip's tree differs from the default branch's | **never auto-delete.** Show them (`git -C <repo> cherry -v origin/<default> <name>` or `log --oneline origin/<default>..<name>`) and let the user decide: merge it, keep it, or explicitly discard. If the PR proof was off or unanswered for this repo, run the manual check under *Merged-PR proof* first; and before shipping it as a PR, rule out tree equality last — the one-liners under *Tree-identical proof*: a silent `git diff --quiet origin/<default> <name>` means delete, not ship |
| `DEFAULT(behind=N)` | the default branch itself | never delete; if behind and not checked out: `git -C <repo> fetch origin <default>:<default>` (fast-forwards without a checkout) |

Skip — whatever the state — any branch that is **checked out** somewhere
(`CHECKEDOUT=yes`; remove/switch the checkout first) or has an **open PR**. Deleting a
local branch touches nothing remote and stays recoverable via `git reflog` for ~90
days, which is why `MERGED`/`EQUIV`/`PRMERGED`/`TREESAME` deletions may batch under one
confirmation.

## Worktrees (the `WT` rows)

Remove from the **primary checkout**, never from inside the worktree (your cwd would
vanish). A worktree is removable when it is **clean** (`DIRTY=0`), **not in use**
(`INUSE=no`), and any of:

- `CONTAINED=yes` — its HEAD (branch or detached) is an ancestor of the default branch;
- `CONTAINED=EQUIV` or `CONTAINED=PRMERGED(#N)` — the scan proved the HEAD's content is
  there by patch-equivalence or by a merged pull request (a detached HEAD matches a PR
  by commit, so it needs no branch);
- `CONTAINED=TREESAME` — the HEAD's tree is identical to the default branch's: its whole
  content landed there in a different commit shape;
- its branch is `MERGED`/`EQUIV`/`PRMERGED`/`TREESAME` in the `BRANCH` rows;
- its branch's upstream is `gone` (deleted on the remote after a merge).

```bash
git -C <repo> worktree remove <path>    # refuses if dirty — investigate, never --force
git -C <repo> branch -d <branch>        # then its branch, -D if EQUIV, PRMERGED or TREESAME
git -C <repo> worktree prune            # drop stale admin entries (also for PRUNABLE=yes)
```

**In use** (`INUSE=yes`) — some process has its working directory inside the worktree:
typically another Claude Code session (its shell and its MCP servers all stand there),
an editor, or a terminal. Removing the directory pulls the floor out from under that
process — a Claude Code session standing in it fails on every command from then on — so
an in-use worktree is **never removed, whatever `CONTAINED` says**. List it under
**Skipped (in use by a live process; pid and command)**, taken from the `INUSE` rows
the scan prints right after it (`INUSE REPO PATH PID COMMAND CWD`); it becomes a
candidate again once that process is gone. `INUSE=?` means the scan had no `lsof`
snapshot (not installed, or it failed): the worktree is **needs you**, not safe — look
by hand before removing:

```bash
lsof -a -d cwd 2>/dev/null | grep -i -- "<path>"   # COMMAND PID ... NAME: who stands in it
```

Never sweep a worktree that is dirty (surface the files), on a never-pushed branch
with unproven content (work in progress), in use by a live process (`INUSE=yes`), or
the one the session is standing in.

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

- **`INUSE=yes`** (a live process stands in the dead directory — often the very session
  whose repo was renamed under it): `git worktree repair` is still fine, it only rewrites
  the link files; **never move the directory** — list it under Skipped with the pid and
  command from its `INUSE` rows, and trash it, if at all, once that process is gone.
  `INUSE=?` (no snapshot) means the `lsof` one-liner above before any trash step.

## Parked primaries (the `PARKED` rows)

A primary checkout left standing on a non-default branch. If that branch is
`MERGED`/`EQUIV`/`PRMERGED`/`TREESAME` and the tree is clean: `git -C <repo> switch <default>` then
`git -C <repo> pull --ff-only`, after which the old branch joins the prune list. If
the branch is `UNIQUE` or has an open PR, leave it parked — just fast-forward the
local default branch alongside: `git -C <repo> fetch origin <default>:<default>`. The
same when `INUSE=yes`: another live process (a Claude Code session, an editor) is
working in that primary, and switching branches under it would change its files
mid-task — leave it parked, list it under Skipped with the pid and command from its
`INUSE` rows, and only fast-forward the default branch alongside. `INUSE=?` is needs-you.

## Remote branches (the `RBRANCH` rows)

`STATE` uses the local vocabulary: `MERGED` (ancestor), `EQUIV` (patch-equivalent — a
single-commit squash), `PRMERGED(#N)` (a merged pull request vouches for it — the
multi-commit squash) and `TREESAME` (the tip's tree is the default branch's — the work
landed in a different commit shape, with no PR) all mean the default branch already
contains everything. Deleting
is **outward-facing** — irreversible for anyone else who fetched the branch — so list
each candidate in the plan with its state (and PR number), check open PRs
(`gh pr list --state open --json headRefName,number` — a PR head is never deleted;
GitHub would close the PR), and delete only after a **per-item** confirmation, never
inside the safe batch:

```bash
git push origin --delete <branch>
```

A `TREESAME` remote branch is a deletion candidate on the same terms — and never a pull
request: merging one squashes an empty commit onto the default branch.

`UNIQUE(N)` remote branches are decisions, not chores: show their age and unique
commits and let the user choose — and before shipping one as a PR, run the tree check
under *Tree-identical proof*: it is the last thing to rule out. Never delete the
default branch or `origin/HEAD`.

## Merged-PR proof (how `PRMERGED` is computed)

`git cherry` recognizes a squash-merged branch only when it had **one** commit: the
squash commit on the default branch carries the combined diff, so with two or more
commits every patch-id misses and the branch reads `UNIQUE(N)` although nothing on it
is unmerged. The scan closes that gap with the pull request record:

- **One `gh` call per repo**: `gh pr list --state merged --base <default> --limit 500`
  for every repo whose origin is a GitHub-style remote (`host/owner/name`) on a host
  `gh` holds a token for. Read-only — nothing is written to GitHub.
- **A branch, remote branch, worktree HEAD, or parked primary is `PRMERGED(#N)`** when a
  merged PR #N into the default branch — matched by head ref name, or by head commit for
  a renamed branch or a detached HEAD — satisfies both tests: its **merge commit is an
  ancestor of the local `origin/<default>`**, and **no non-merge commit reachable from
  the tip is missing from both `origin/<default>` and the PR head** — the tip is the PR
  head, is behind it, or only merges from the default branch follow it. A rebased,
  amended, or continued branch fails the second test and stays `UNIQUE`.
- **Best-effort, never inventive**: no `gh`, no token (`gh auth token -h <host>` is the
  probe — `gh auth status` fails as soon as any stale secondary account exists), a
  non-GitHub remote, or a failed call leaves that repo classified from git alone,
  exactly as before. `SUMMARY` says which: `pr-proof=off`, or `pr-proof=Q/G` (Q of G
  GitHub repos answered). Stale refs only make the proof more conservative: a PR merged
  after the last fetch has a merge commit the local `origin/<default>` does not hold yet.
- **Limits**: only the 500 most recently merged PRs are seen, and PRs into another base
  branch never count — such branches stay `UNIQUE`. So before calling a `UNIQUE` branch
  unmerged work in a repo where the proof was off or unanswered, check by hand:

```bash
gh pr list --state merged --head <name> --json number,headRefOid,mergeCommit          # the PR, if any
git -C <repo> merge-base --is-ancestor <mergeCommit> origin/<default> && echo landed  # test 1
git -C <repo> rev-list --count --no-merges origin/<default>..<name> ^<headRefOid>     # test 2: 0 = nothing beyond the PR
```

- `--no-pr` turns the lookup off for a run (no `gh` calls at all).

## Tree-identical proof (how `TREESAME` is computed)

Patch-ids see a squash only when the branch had one commit, and the PR record sees a
squash only when there was a pull request. Work that reached the default branch
**directly, as one combined commit** — the same files, the same content, a different
commit shape — defeats both: `git cherry` shows every commit as `+`, no PR vouches for
it, and the branch reads `UNIQUE(N)` although nothing on it is unmerged. Shipping such a
branch as a PR lands an **empty commit** on the default branch (GitHub squash-merges the
zero diff). The scan closes this gap by comparing trees:

- **The check**: `git rev-parse <tip>^{tree}` equals `git rev-parse origin/<default>^{tree}`
  — exactly what `git diff --quiet origin/<default> <tip>` tests. Identical tree ids mean
  identical content, whatever the commits look like, so the branch holds nothing the
  default branch lacks.
- **Order**: judged only after `MERGED`, `EQUIV` and `PRMERGED` have all failed, so a
  stronger proof always wins the label; and a tip holding anything the default branch
  lacks has a different tree, so it can never pass — `TREESAME` never fires on a branch
  that is ahead in content.
- **Limit**: only the **current tip** of `origin/<default>` is compared. Once the default
  branch moves on, a branch whose content landed earlier reads `UNIQUE(N)` again — the
  scan is exact, not historical. So before shipping a `UNIQUE` branch as a PR, the tree
  check is the last thing to rule out, by hand:

```bash
git -C <repo> diff --quiet origin/<default> <name> && echo tree-same   # silent = nothing unique: delete, never PR
git -C <repo> log --format=%T origin/<default> | grep -qx "$(git -C <repo> rev-parse '<name>^{tree}')" && echo landed-earlier   # its exact tree was the default branch's at some earlier commit
```

Either line printing means the branch's whole content has already been on the default
branch: treat it as `TREESAME` — delete it (`branch -D`, or `push origin --delete` after
a per-item confirmation) and do not open a pull request for it.

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
claude plugin list --json           # BEFORE snapshot: [{id, version, scope, projectPath?, ...}]
# for each id:
claude plugin update <id>           # user scope — the default, and the ONLY scope this touches
# for each row with scope project|local — every project and worktree keeps its own
# install record, pinned to the version current when the plugin was enabled there:
(cd "<projectPath>" && claude plugin update <id> --scope <scope>)
claude plugin list --json           # AFTER snapshot — the diff is the report
```

Rows whose `projectPath` no longer exists are stale install records (a renamed or
removed project or worktree): skip them and list them under **needs you** rather than
guessing a path.

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
case-insensitively (macOS filesystems). The in-use probe is one
`lsof +c 0 -a -d cwd -Fpcn` call per run — read-only, every process the user may
inspect with its working directory — matched against each `WT`/`ORPHAN`/`PARKED` path
by prefix (case-insensitively, and `/foo` never matches `/foobar`). Without `lsof`
(macOS ships it; on Linux it is a package) every `INUSE` reads `?` and `SUMMARY`
`in-use=?`: nothing is assumed free — check by hand with the one-liner above.

If the scan reports `fetch-failures>0`, those repos' merged/gone/behind signals are
stale: report which failed, finish the sweep on the repos that did fetch, and never
push, prune, or delete from stale refs. Offline, the merged-PR lookup fails the same
way (`pr-proof=0/G`): classification falls back to git alone, and `UNIQUE` rows in
those repos are not unmerged work until the manual check above says so. Never invent
or assume remote state.

## Relationship to git-workflow

repo-sweep is the **breadth** (every repo, end of day); `yar:git-workflow` is the
**depth** (one repo, done right). The sweep leans on git-workflow's rules —
explicit-pathspec commits, rebase-not-merge, `--force-with-lease`, conflict recipes —
rather than duplicating them. When one repo needs real attention (a gnarly conflict, an
accidental commit on `main`), switch to git-workflow for that repo, then come back and
finish the sweep.
