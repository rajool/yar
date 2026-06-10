# worktrees — parallel Claude Code sessions without collisions

> Read this file when you want to push **more than one task at the same time** with Claude Code (e.g. one session writes a feature, another fixes a bug). git worktree is the main anti-collision approach — Anthropic's own #1 recommendation for parallel work.

## Default to a worktree, and detect when you must
A second Claude session opened in the same folder lands in the **same checkout** by default — not a new one. So unless you're **certain** you're the only session here, make a worktree, not just a branch. Tell-tale signs you're already sharing a checkout (isolate *before* you commit if you see any):
- `git status` shows changes or staged files you didn't make;
- the branch switched under you between two commands;
- a file is reported "modified by user or linter" that you never touched.

## Why a worktree (and not just a branch)?
Each worktree is a **separate working directory with its own index**, tied to a separate branch but sharing the same `.git` object store. A plain branch in a shared checkout still shares **one working tree and one staging index** with every other session — so a concurrent `git add` can land in *your* `git commit`, and a branch-switch in one session changes the files under the other. A worktree gives each session its own working tree + index → collisions (files *and* commits) drop to zero. (Prerequisite: git 2.5+.)

## Creating a worktree
From inside the repo, create a **sibling** folder (next to the main folder) and check out the new branch there:
```bash
git worktree add ../myproject-receipts -b feat/donation-receipts main
#                 ^new folder           ^new branch               ^from main
```
Then open Claude Code in that folder and work:
```bash
cd ../myproject-receipts && claude
```
> Shortcut: if you run Claude Code with the worktree flag (`-w`), it creates the worktree itself and enters it.

## `.worktreeinclude` — getting `.env`/keys into the worktree
A worktree is a fresh checkout, so **untracked** files (like `.env`, which is in `.gitignore` and holds your secrets/API keys) are **not** in it. To have Claude copy these automatically when creating the worktree, put a `.worktreeinclude` file at the repo root:
```
.env
```
(Each line is a path relative to the root. This file itself is text and stays in git; `.env` itself does not.)

## Golden rule: rebase, not merge
To sync with `main` between worktrees/branches, always **rebase**, not merge:
```bash
git fetch origin && git rebase origin/main
```
Why: merge creates a "merge commit" that branches the history and makes reading `git log` confusing; rebase keeps each branch's history linear and based on `main`, and Claude reasons much better over a linear history.

## Multiple concurrent sessions? Practical ceiling 2–4
- 2 to 4 parallel sessions are manageable. 5 or more → hard to review + you hit the API rate limit.
- **Split scope by module, not by task:** do a single module/folder's work in one worktree and **sequentially**; do separate modules' work in parallel worktrees. This prevents same-file conflicts.
- Keep a shared notes file (like `~/.claude-notes.md`) so you don't lose the thread when switching between sessions.

## Cleanup (immediate habit after merge)
As soon as the PR merges, the worktree has done its job — remove it, or it joins the pile. **Right after a merge, offer this cleanup before moving on.** Two gotchas:

- **Never remove the worktree you are standing in** — the directory disappears under your shell and the cwd dies. `cd` to the main checkout first.
- **`gh pr merge --delete-branch` misbehaves inside a worktree**: after merging it tries to check out `main`, which is already checked out in the main folder, so it errors and can leave the remote branch behind. Prefer `gh pr merge --squash` followed by deleting the remote branch yourself.

```bash
cd <main-checkout>
git push origin --delete <branch>     # only if the remote branch is still there
git worktree remove <path>            # refuses if the worktree is dirty — investigate, don't --force
git branch -D <branch>                # -D: after a squash-merge git cannot tell the branch is merged
git worktree prune                    # clear out dead entries
```

## Sweeping merged worktrees ("clean up worktrees")
When worktrees piled up anyway, remove every one whose work already landed on `main`:

```bash
git fetch --prune origin    # 1. drop records of remote branches that no longer exist
git worktree list           # 2. all worktrees and their branches
git branch -vv              # 3. an upstream marked "gone" = deleted on the remote = its PR merged
```

For each worktree on a `gone` branch: `git worktree remove <path>`, then `git branch -D <branch>`. Finish with `git worktree prune`, and report what was removed and what was skipped and why. Never touch:

- **the worktree you are standing in** — `cd` out first, or leave it for a later sweep;
- **dirty worktrees** (`git -C <path> status --porcelain` prints anything) — that is work in progress;
- **branches with no upstream at all** (never pushed) — unfinished work, not merged work.

Why "upstream gone" and not `git branch --merged`: a squash-merge rewrites the branch's commits into one new commit on `main`, so git never sees the branch itself as merged. But the remote branch is deleted at merge time (`--delete-branch` or a manual `git push origin --delete`), and after `git fetch --prune` that absence shows up as `gone` — the one reliable merged signal under this workflow.
