# daily-sync playbook — per-state decisions, edge cases, exact commands

Read this when a checkout's state is not obvious from the scan, or before running a
command you are not certain preserves work. The governing rule for the whole skill:
**reconcile by moving commits, never by overwriting work.** Everything committed gets
pushed; everything on the remote gets pulled; anything that cannot reconcile cleanly is
**surfaced**, not destroyed. There is no `reset --hard`, no `checkout -- <file>` over a
dirty tree, no `stash drop`, no `worktree remove --force`, no deleting an unpushed branch.

`<path>` below is the checkout's path from the scan; commands use `git -C <path>` so you
never have to `cd` (and never lose the worktree you are standing in).

## The decision matrix

Read the scan columns `DIRTY AHEAD BEHIND UPSTREAM STASHES` per checkout. Resolve in this
order — **upstream first, then divergence, then dirtiness, then stashes** — because the
safe action depends on whether an upstream even exists.

| UPSTREAM | DIRTY | AHEAD | BEHIND | Meaning | Morning | Evening |
|---|:--:|:--:|:--:|---|---|---|
| `ok` | 0 | 0 | 0 | in sync | nothing | nothing |
| `ok` | 0 | 0 | >0 | behind only | `pull --ff-only` | `pull --ff-only` |
| `ok` | 0 | >0 | 0 | ahead only | leave (push tonight) | `push` |
| `ok` | 0 | >0 | >0 | diverged | `pull --rebase` | `fetch` → `rebase @{u}` → `push --force-with-lease` |
| `ok` | >0 | * | 0 | local edits, not behind | report; offer stash-pull only if behind | commit (confirm) → `push` |
| `ok` | >0 | * | >0 | local edits **and** behind | **do not pull onto dirty**; report | commit (confirm) → `rebase @{u}` → `push --force-with-lease` |
| `none` | * | – | – | branch has no upstream (never pushed) | skip; report | **ask** before `push -u origin HEAD`; if it is a worktree, treat as work-in-progress and skip the sweep |
| `gone` | 0 | * | * | upstream deleted on remote (merged) | report | **sweep** the worktree (see below) |
| `gone` | >0 | * | * | merged upstream **but** dirty | report | **do not remove**; surface the dirty files first |
| any | * | – | – | `BRANCH = DETACHED` | skip; report | surface; do not guess a branch |

`*` = any value; `–` = not meaningful (no upstream to measure against).

## Commands by state

**Behind, clean** — fast-forward only, so history is never rewritten:
```bash
git -C <path> pull --ff-only
```
If `--ff-only` refuses, the branch actually diverged (the scan raced a new local commit) —
fall through to the diverged case.

**Ahead, clean** — publish your commits:
```bash
git -C <path> push                      # upstream exists
git -C <path> push -u origin HEAD       # UPSTREAM=none, and only after the user says publish it
```

**Diverged (ahead + behind)** — replay local commits on top of the remote, then push:
```bash
git -C <path> fetch
git -C <path> rebase @{u}                # @{u} = this branch's upstream
git -C <path> push --force-with-lease    # safe: refuses if the remote moved under you
```
Morning shortcut for the same situation is `git -C <path> pull --rebase`. `--force-with-lease`
(not `--force`) is mandatory — it aborts if someone else pushed in the meantime, so you never
clobber a teammate. On a conflict, see "Conflicts" below.

**Dirty** — uncommitted work a push cannot carry. Do not pull or rebase onto it. In the
evening, commit it first (the morning leaves it unless the user opts into stash-pull):
```bash
git -C <path> status --porcelain         # list the exact changed/untracked paths
# branch first if on main (per git-workflow), then stage ONLY those paths explicitly:
git -C <path> add -- <path1> <path2> ...  # never  add -A / add . / add -u  (git-guard blocks it)
git -C <path> commit -m "type(scope): summary" -- <path1> <path2> ...
git -C <path> push                        # or push -u origin HEAD for a fresh branch
```
Propose a sensible conventional-commit message from the diff; confirm before committing.
If the repo is also behind, rebase after committing, then `push --force-with-lease`.

**Dirty + behind, morning, user opts in** — the only sanctioned stash dance, fully reversible:
```bash
git -C <path> stash push -u -m "daily-sync auto-stash"
git -C <path> pull --ff-only
git -C <path> stash pop                   # may conflict → resolve in place, never drop
```
Default to **not** doing this; leaving dirty files for the evening commit is safer.

**Stashes present** — a stash is local-only state a push cannot save. List it so it is not
forgotten; never `drop` or `clear`:
```bash
git -C <path> stash list
```

## Conflicts — hand off, don't force
A conflict during `pull --rebase`, `rebase @{u}`, or `stash pop` means two histories touched
the same lines. daily-sync does **not** auto-resolve across many repos. Stop on that one repo,
leave it in a clean state, and surface it:
```bash
git -C <path> rebase --abort      # back to before the rebase, nothing lost
# or, to resolve now, hand this repo to yar:git-workflow's conflict recipe
```
Report the repo under "needs you" and continue the sweep on the others. Resolving conflicts is
git-workflow's job (`reference/recipes.md` there) — don't reimplement it here.

## The merged-worktree sweep
This is git-workflow's sweep run across every repo at once. After `scan-repos.sh --fetch` (which
runs `git fetch --all --prune`), a worktree whose branch `UPSTREAM` shows `gone` had its remote
branch deleted — under squash-merges that is the **only** reliable "this merged" signal, because
`git branch --merged` sees nothing (the squash commit has different parents). Remove it from its
**main checkout** (never from inside the worktree — your cwd would vanish):
```bash
git -C <main-checkout> worktree remove <path>   # refuses if dirty — investigate, don't --force
git -C <main-checkout> branch -D <branch>         # -D not -d: git can't tell a squash-merge merged
git -C <main-checkout> worktree prune             # drop stale administrative entries
```
**Never sweep** a worktree that is (a) dirty, (b) on a branch with `UPSTREAM=none` (never pushed —
work in progress, no proof it merged), or (c) the one you are standing in. Report each skip with
its reason. The scan lists worktrees under their parent repo, so `<main-checkout>` is the `repo`
row that owns the `worktree` rows.

## Plugins
Plugins come in two layers, and the routines treat them differently:

- **Source repos** (a plugin you develop, living under a scan root) are ordinary git repos — the
  scan finds them and the morning pull / evening push/sweep cover them like any other repo.
- **The installed cache** (`~/.claude/plugins/cache/...`) is downstream of a marketplace. Nothing
  to push there; it is refreshed, not reconciled. Morning only:
  ```bash
  claude plugin marketplace update           # refresh every configured marketplace source
  claude plugin list --json                   # array of {id, version, enabled, installPath, ...}
  # for each id:  claude plugin update <id>    # there is no built-in "update all"
  ```
  `claude plugin update` applies on the **next Claude Code restart** — always say so in the report.
  If a marketplace is a local path that is also a scan-root repo, the morning pull already updated
  its source; `marketplace update` then re-reads it and `plugin update` installs the new version.

## Scan roots and depth
`scan-repos.sh` resolves roots in this order, first non-empty wins:
1. `ROOT` arguments passed on the command line.
2. `$DAILY_REPO_ROOTS` — a colon-separated list, `~` allowed (e.g. `~/Projects:~/Clients/acme`).
3. Defaults: `~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer` (only those that exist).

Depth under each root is `$DAILY_SCAN_DEPTH` (default 4). The scan prunes `node_modules`, `.venv`,
`venv`, `vendor`, `Pods`, `.terraform`, `.tox`, `.Trash`, and `Library` for speed. A primary repo
is a directory containing a `.git` **directory**; linked worktrees (which have a `.git` **file**)
are enumerated through their parent's `git worktree list`, so each checkout appears exactly once.
On the first run, confirm the discovered root list with the user; if repos are missing, widen
`DAILY_REPO_ROOTS` or raise the depth.

## Offline / partial failure
If `scan-repos.sh --fetch` reports `fetch-failures>0`, one or more remotes were unreachable
(offline, VPN, auth). The ahead/behind/gone numbers for those repos reflect the **last** fetch and
may be stale. Do not push or sweep based on stale `gone`/behind data — tell the user which repos
failed to fetch, finish the routine for the repos that did fetch, and offer to re-run the rest once
the network is back. Never invent or assume remote state.

## Relationship to git-workflow
daily-sync is the **breadth** (every repo, once a day); `yar:git-workflow` is the **depth** (one
repo, done right). daily-sync calls on git-workflow's rules and recipes — explicit-pathspec commits,
rebase-not-merge, `--force-with-lease`, the conflict recipes, the worktree sweep and its skip rules —
rather than duplicating them. When a single repo needs real attention (a gnarly conflict, a tangled
rebase, an accidental commit on `main`), switch to git-workflow for that repo, then come back and
finish the sweep.
