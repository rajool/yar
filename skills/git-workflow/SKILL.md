---
name: git-workflow
description: 'A git branch-and-merge workflow for small teams coding with Claude Code — short-lived feature branches off main, conventional commits, a pull request the author squash-merges (no required approval), and one git worktree per parallel session so concurrent sessions never collide. Runs only when you invoke it; it does not auto-branch, auto-push, or auto-merge on its own. Use when you ask to start new work, create a branch, commit changes, sync or rebase on main, open or merge a pull request, resolve a merge conflict, run parallel Claude sessions, or clean up branches and worktrees. Triggers include "create a branch", "start a new task", "open a PR", "merge this", "ship/land this", "sync with main", "resolve conflict", "set up a worktree". "Ship" is a single command for the whole chain — commit if needed, push, open the PR, and squash-merge it. It is NOT finished at `gh pr create`: shipping means the PR is merged and main has the change (the plugin''s ship-guard hooks enforce this).'
---

# git-workflow — git branch and merge workflow

Goal: let a small team write code with multiple concurrent Claude Code sessions **without getting tangled** — each task on a short-lived branch, one PR the author merges themselves, and `main` always clean. ("When" is in the description; "how" is here.)

**This skill is invoke-only.** It runs these steps when you ask for them (start work, branch, commit, sync, open/merge a PR, resolve a conflict, set up a worktree). It does **not** create branches, push, open, or squash-merge PRs on its own initiative.

## 0) Core principle + setup
- **`main` is sacred:** always green and the source of truth. Real work is **never directly on `main`** — always on a branch.
- **One worktree per session — the real isolation.** A branch alone is **not** enough once more than one session runs: every session opened in the same folder shares **one checkout and one git index**, and that shared index is what tangles commits — a file another session stages between your `git add` and `git commit` rides into *your* commit (a real incident: a clean 9-file change shipped as 18). A separate branch isolates *history*; a separate **worktree** isolates the *index and files*. So the default unit of work is "my own worktree," not just "my own branch" → step 1 + `reference/worktrees.md`.
- **Once per repo (recommended):** run `/yar:install-guards` to wire the git-level `pre-commit` guard (blocks committing binaries/secrets from any git client). The `git-guard`, `branch-guard`, and `ship-guard` Claude hooks are already active once the plugin is enabled — no install needed.
- **Branch naming:** `<type>/<dash-separated-summary>`; if you track tasks, `<type>/T-0NN-<summary>`. `type` values are the conventional-commits ones: `feat fix docs chore refactor`.

## 1) Starting work — branch off a fresh main
> Do this when you start a task or ask to "create a branch". (If the optional `branch-guard` hook is installed, editing files while on `main` is blocked as a passive safety net that nudges you to branch first — that guard never opens or merges a PR for you.)

**First, detect a shared checkout** (`git status`). You are sharing this folder with another session if you see *any* of: uncommitted changes or staged files you didn't make; the branch switched under you between commands; a file reported "modified by user or linter" that you never touched. If so — or if you simply can't be **certain** you're the only session here — **isolate into a worktree** (don't just branch):
```bash
git worktree add ../<repo>-<task> -b feat/<summary> origin/main   # your own checkout + branch + index
cd ../<repo>-<task>                                               # do all the work here
```
Only when you're certain you're the sole session in this folder is a plain branch enough:
```bash
git switch main && git pull --rebase        # start from the latest main
git switch -c feat/donation-receipts        # your own short-lived branch
```
**Next task in a worktree you already have (after its PR squash-merged):** start from `origin/main`, never from the old HEAD — a squash-merge rewrites your commits into one new commit on `main`, so the old ones still sit on the worktree branch and would ride along as duplicates (GitHub then reports conflicts on the next PR — this happened):
```bash
git fetch origin && git switch -C feat/<next-task> origin/main   # -C: reuse or move the branch onto fresh main
```
Worktree details (`.worktreeinclude` for `.env`/keys, rebase-not-merge, cleanup) → `reference/worktrees.md`.

## 2) While working — small, frequent commits
Stage **only this session's own files**, by explicit path, and confirm the staged set *before* you commit — never sweep in a concurrent session's changes.
```bash
git status --short                           # 1. see the whole working tree first
git add path/to/file another/file            # 2. stage only this task's files, explicit paths
git diff --cached --name-only                # 3. verify every staged file is one YOU changed this session
git commit -m "feat(finance): add donation receipt template" -- path/to/file another/file   # 4. commit ONLY these paths
```
- **Commit by pathspec (race-proof) when you share a checkout:** end the commit with `-- <your paths>`. `git commit -m "…" -- p1 p2` commits exactly those paths from the working tree and **ignores whatever else sits in the shared index** — so a concurrent session that stages its files between your `add` and your `commit` cannot ride into your commit. (Steps 2–3 still matter for new/untracked files, which `add` must stage first; the `-- <paths>` on commit is the mechanical guarantee. In your own worktree there's no shared index, so it's just a harmless habit.)
- **Ownership check before every commit:** you know which files you edited this session — commit only those. If `git status` / `git diff --cached` shows a file you did **not** touch, it likely belongs to another session sharing this checkout: leave it exactly as is — don't stage, commit, `stash`, or `restore` it. If such a file is already **staged** (a concurrent session staged it), unstage it with `git restore --staged <path>` — its changes stay intact in the working tree — then commit your own files and continue. (Already committed one by mistake — even already pushed? → `reference/recipes.md`.)
- Conventional message: `type(scope): short imperative description`.
- Keep the branch **up to date**: every so often run `git fetch origin && git rebase origin/main`. Why rebase, not merge: history stays linear and Claude reasons better over a linear `git log`. Resolve conflicts right here inside the branch, not on `main`.
- `git add -A`/`git add .`/`commit -a` won't work (the `git-guard` hook catches it) — deliberate, so you don't pick up other sessions' work. The ownership check above is the active version of that same rule: the hook blocks bulk staging; you confirm the explicit set is yours.

## 3) Merge — push, PR, and self-merge
> Only when you ask to open/merge a PR or "ship it".

### "Ship" is one unbroken chain — it ends at MERGED, not at "PR opened"

**`gh pr create` is the middle of the job, never the end.** Shipping is done when the PR is **merged** and `main` has the change. Run all four, in order, in one go:

```bash
git push -u origin HEAD                      # 1. push the branch up
gh pr create --fill                          # 2. or with a custom title/body
gh pr merge --squash --delete-branch         # 3. merge it yourself — no approval needed
                                             #    (inside a worktree: gh pr merge --squash, WITHOUT --delete-branch)
gh pr view --json state --jq .state          # 4. must print MERGED — only then report "shipped"
```
Inside a worktree, two more steps **after** step 4 prints `MERGED`, each as its own command:
```bash
git push origin --delete <branch>            # 5. delete the remote branch — only now (git-guard refuses it while the PR is OPEN or when it is chained to the merge)
git fetch origin && git reset --hard origin/main   # 6. park the worktree on fresh main — the squash left it on dead commits; the tree is identical, nothing is lost
```

- **The word "shipped" is reserved for `state == MERGED`.** "PR opened", "ready to merge", "mergeable and clean", "left for you to merge" are *not* shipped — they are the failure this rule exists to prevent. If the last command you ran was `gh pr create`, you are not finished: run step 3, then step 4.
- **"Ship" pre-authorizes the merge.** Never come back asking "shall I merge it?". The one reason to stop before step 3 is that the change genuinely needs another person's eyes — then **say so, with the reason**, and release the guard (below). Silence after `gh pr create` is always a bug.
- **Mechanically enforced — `ship-guard`.** Once your prompt says "ship", three plugin hooks hold this contract: the prompt hook injects the chain above; a `PostToolUse` nudge fires right after `gh pr create`; and a `Stop` hook refuses to end the turn — up to three times — while a PR from this session is unmerged, commits are unpushed or have no PR, or nothing was committed at all. It verifies with `gh pr view` and `git`, fails open (offline, no `gh`, not a repo), and releases itself the moment the PR is `MERGED`. The escape hatch is explicit and auditable: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ship-guard.py" release --marker <path> --reason "<why>"` (the block message prints the exact command) — and the reason must be repeated to the user, because a released ship is an unfinished ship.
- **No required approval:** everyone squash-merges their **own** PR. Others' review is welcome but never a blocker.
- **Why squash:** each PR becomes one clean commit on `main`; history stays readable.
- Before merging, make sure the branch is up to date with `main` (step 2) so the merge is conflict-free.
- **Merging from inside a worktree?** `--delete-branch` errors there (it tries to check out `main`, which is checked out in the main folder) and can leave the remote branch behind. Use `gh pr merge --squash`, verify `MERGED`, and only then `git push origin --delete <branch>` — **as a separate command, never `gh pr merge … && git push origin --delete …`**: if the merge fails (conflict, pending checks) the delete still runs, and GitHub closes the open PR unmerged the moment its head branch disappears. `git-guard` blocks that chain, and blocks a standalone delete while the PR is still `OPEN`. Then `git fetch origin && git reset --hard origin/main` so the worktree does not keep the dead pre-squash commits (`ship-guard` refuses to end the turn while it does — they show up as a phantom "Create PR" and would duplicate into the next PR).
- **Protected base branch?** If required checks block an immediate merge, use `gh pr merge --squash --auto` — it merges on its own once checks pass; do the cleanup after it lands.
- **The merge ends the worktree's job — offer cleanup now.** If this task ran in its own worktree, ask right after the merge lands: "merged — done with this task? I'll remove the worktree and the local branch." On yes → step 4. Skipping this moment is how stale worktrees pile up.

## 4) Cleanup
Worked on a plain branch (in the main checkout):
```bash
git switch main && git pull --rebase         # refresh local main
git branch -D feat/donation-receipts         # -D, not -d: after a squash-merge git cannot tell the branch is merged (the remote branch is already gone)
```
Worked in a worktree? Leave it first — **never remove the directory you are standing in** (your shell's cwd dies with it):
```bash
cd <main-checkout> && git pull --rebase
git worktree remove <path-to-worktree>       # refuses if the worktree is dirty — investigate, don't --force
git branch -D <branch>
```
Keeping the worktree for the next task instead? Park it on fresh `main` first — `git fetch origin && git reset --hard origin/main` — and start the next branch from there (§1). A worktree left on its squash-merged commits looks like unmerged work and seeds duplicate commits.
**Sweep — on "clean up worktrees":** when stale worktrees piled up anyway, run `git fetch --prune origin`, then `git worktree list` + `git branch -vv`: every worktree whose branch's upstream says `gone` was merged and deleted on the remote → remove it as above (a squash-merge is why `git branch --merged` finds nothing). Skip — and report — dirty worktrees, never-pushed branches (no upstream = work in progress), and the worktree you are standing in. Finish with `git worktree prune`. Full recipe → `reference/worktrees.md`.

## 5) Untangling (summary — details and safe commands in `reference/recipes.md`)
- **You accidentally committed on `main` (not pushed yet):** move the commits to a branch and pull `main` back.
- **PR has a conflict / branch is behind:** `git rebase origin/main` → resolve conflicts → `git push --force-with-lease`.
- **rebase/merge broke:** find the good point with `git reflog` and `git reset --hard <hash>`.

## Guardrails
- `main` is sacred — real work on a branch + PR; never directly on `main`.
- **One worktree per session** whenever you can't be certain you're the only session in this folder — a shared checkout means a shared index, and that is what cross-contaminates commits. A branch isolates history; a worktree isolates the index/files.
- The bundled hooks stay in place: no `git add -A`/`commit -a` and no remote-branch deletion while its PR is `OPEN` or chained to the merge (git-guard), no edits on `main` (branch-guard), no binaries/secrets (pre-commit), no ending a turn mid-ship or on dead pre-squash commits (ship-guard). Binary → external storage (not git), secret → `.env` (gitignored). Rare overrides: `GIT_GUARD=off`, `BRANCH_GUARD=off`, `SHIP_GUARD=off`, or `git commit --no-verify`.
- Stage only this session's own files with explicit paths, **commit by pathspec** (`git commit -m "…" -- <paths>`), and **verify ownership before each commit** (`git diff --cached --name-only`): commit only files you changed this session; leave any other session's changes — staged or unstaged — exactly as they are. In an isolated worktree the collision risk is zero (these pass trivially); they matter most when sessions **share one checkout**.
- **Invoke-only:** this skill does not branch, push, open, or merge a PR on its own — it runs the steps when you ask. When the ask is "ship", the whole of step 3 — squash-merge included — is what was invoked; don't re-confirm the merge separately. The `ship-guard` hooks enforce exactly that: they never start a ship, they only refuse to end one early.

## References
- `reference/worktrees.md` — parallel Claude sessions with git worktree (setup, `.worktreeinclude`, rebase not merge, post-merge cleanup + the merged-worktree sweep, the practical 2–4 session ceiling). **Read it when working in parallel.**
- `reference/recipes.md` — ready-to-use commands for resolving conflicts and recovery. **Read it when things get tangled.**
