---
name: daily-sync
description: Start-of-day and end-of-day sync across every local git repo and installed Claude Code plugin at once. A morning greeting scans read-only, fast-forward/rebase-pulls every repo and worktree, and refreshes all plugins. An evening greeting pushes all committed work, rebases and surfaces diverged history or conflicts, offers to commit dirty trees (never discarding them), sweeps merged/gone worktrees and their branches, and reconciles local with remote so nothing is left behind — code repos and plugin source repos alike. It shows the plan before mutating and confirms hard-to-reverse steps, so a bare greeting destroys nothing first. Leans on yar:git-workflow for per-repo mechanics. Use on "good morning", "good night", "start my day", "end of day", "wrap up", "sync everything", "pull all repos", "push everything", "update all plugins", "clean up worktrees", or Persian "صبح بخیر", "سلام صبح بخیر", "شب بخیر", "روتین صبح", "روتین شب", "همه ریپوها رو پول کن", "همه پلاگین‌ها رو آپدیت کن".
---

# daily-sync — start-of-day / end-of-day repo & plugin sync

Goal: one move at the start of the day and one at the end that keeps **every** local git repo and **every** installed Claude Code plugin in step with their remotes — pull + update in the morning, push + reconcile + tidy at night — across all your repos at once, so nothing quietly drifts or gets left behind. ("When" lives in the description; "how" is here.)

This skill mutates many repos, so it always **scans read-only first, shows the plan, and only then acts** — and it **confirms anything hard to reverse** (commits, force-with-lease pushes, worktree removal). A bare "good morning" therefore never destroys anything before you have seen what it intends to do. It does **not** run on a schedule or on its own initiative — only when you greet it or ask.

It is the cross-repo **orchestrator**. The per-repo mechanics — branching, committing by pathspec, rebasing, resolving conflicts, the merged-worktree sweep — belong to **`yar:git-workflow`**, which this skill follows rather than reinventing. When a single repo gets stuck (a conflict, a tangled rebase), hand that repo to git-workflow's recipes and move on.

## 0) Scan first — always (read-only)
Build the picture before touching anything. Run the bundled scanner; for the **evening** routine — or any time the ahead/behind/gone numbers must be exact — add `--fetch` (it updates remote-tracking refs only, never your files):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/daily-sync/scripts/scan-repos.sh" --fetch
```

**Scan roots** (first source that yields anything wins): `ROOT` arguments → `$DAILY_REPO_ROOTS` (colon-separated, `~` allowed) → the defaults `~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer`. Depth below each root is `$DAILY_SCAN_DEPTH` (default 4). If the user's repos live elsewhere, pass the root(s) or set `DAILY_REPO_ROOTS` — confirm the root list with them on the first run.

Each row is one **checkout** — a primary repo or one of its linked worktrees, each listed exactly once — with: `BRANCH`, `DIRTY` (changed + untracked paths), `AHEAD`/`BEHIND` vs upstream, `UPSTREAM` (`ok` | `gone` | `none`), and `STASHES`. The trailing `SUMMARY` line totals it. Read these columns to classify each checkout (step 3) and drive the routine. If `SUMMARY` shows `fetch-failures>0` you are likely offline or a remote is unreachable — say so and either stop or continue read-only; never invent state.

## 1) Morning routine — "good morning"
Goal: start the day from the latest of everything. The work here is mostly safe — a pull either fast-forwards or rebases your local commits on top, and a plugin update only adds newer versions — so proceed from the scan with a final summary and **no per-repo confirmation**, except where a pull cannot fast-forward cleanly.

1. **Scan** (step 0, with `--fetch`).
2. **Pull every `ok` checkout** (repo and worktree alike), by its state:
   - **clean, behind** → `git -C <path> pull --ff-only` (fast-forward only; it cannot rewrite anything).
   - **clean, diverged (ahead + behind)** → `git -C <path> pull --rebase` (replays your local commits on top). If it conflicts, **stop on that repo, leave it mid-rebase or abort cleanly, and surface it** — do not auto-resolve. Hand it to git-workflow.
   - **dirty, behind** → do **not** pull onto dirty files. Report it; offer a `stash → pull --ff-only → stash pop` only on confirmation, else leave it for the evening commit. Never discard.
   - **`none` / `gone` / `DETACHED`** → skip the pull, report it under "needs you".
3. **Refresh all plugins** — pull newer published versions into the installed plugin cache:
   ```bash
   claude plugin marketplace update          # refresh every marketplace source
   claude plugin list --json                  # enumerate installed plugins (a JSON array of {id,...})
   # then, for each id:  claude plugin update <id>
   ```
   `update` takes one plugin name (there is no built-in "update all"), so loop over the ids from `list --json`. Your own plugin **source repos** under your scan roots were already pulled in step 2; this step pulls the **published** versions into the cache. A plugin update needs a **Claude Code restart** to take effect — note it in the report.
4. **Report** (step 4).

## 2) Evening routine — "good night"
Goal: get every bit of **committed** local work safely to its remote, reconcile diverged history, tidy worktrees that have merged, and leave local and remote identical — **without ever discarding uncommitted work, stashes, or unpushed branches.** Because this pushes, rebases, and removes worktrees, **present the plan from the scan and confirm before mutating** (one "yes to all" is fine; or let the user pick per repo).

1. **Scan with `--fetch`** (step 0).
2. **Present the plan**: a short table — per checkout, the intended action (push / pull / rebase+push / commit-then-push / remove-worktree / surface-only). Proceed on confirmation.
3. **Work each checkout by its state** — the full matrix and exact commands are in `reference/playbook.md`; the essentials:
   - **ahead, clean** → `git -C <path> push`. If `UPSTREAM` is `none` and it is a branch worth publishing, `git -C <path> push -u origin HEAD` — **ask first**, never auto-publish a private branch.
   - **behind, clean** → `git -C <path> pull --ff-only` to match remote.
   - **diverged (ahead + behind)** → `git -C <path> fetch` then `git -C <path> rebase @{u}`, then `git -C <path> push --force-with-lease`. On conflict, **stop and hand the repo to git-workflow's conflict recipe** — do not force-push over it.
   - **dirty** → uncommitted work a push cannot carry. Surface the changed files and propose a conventional commit (branch first if on `main`, per git-workflow). On confirm, **stage explicit paths** (`git add -- <paths>`; never `git add -A`/`.` — the git-guard blocks it and it risks sweeping a concurrent session's files), commit, then push. **Never discard.**
   - **stashes present** → a stash cannot be pushed. **List them** so they are not forgotten, and leave them untouched.
   - **`DETACHED` / `none`** → surface; do not guess a branch or a remote to push to.
4. **Sweep merged worktrees** (git-workflow's sweep, applied across every repo): after the `--fetch`, a worktree whose branch `UPSTREAM` is `gone` was merged and deleted on the remote — the reliable "merged" signal under squash-merges, where `git branch --merged` sees nothing. Remove it and delete its local branch. **Skip — and report — any worktree that is dirty, has no upstream (never pushed = work in progress), or is the one you are standing in.**
   ```bash
   git -C <main-checkout> worktree remove <path>   # refuses if dirty — investigate, don't --force
   git -C <main-checkout> branch -D <branch>         # -D: a squash-merge leaves git unable to see it merged
   git -C <main-checkout> worktree prune
   ```
5. **Re-scan to confirm.** Every `ok` checkout should now read `ahead=0 behind=0`, and merged worktrees should be gone. Whatever remains (dirty trees, stashes, detached HEADs, repos left mid-conflict) is reported under "needs you" — that is the honest "nothing left behind" check, not a claim that everything reconciled.

## 3) Classify each checkout
The routines above key off the scan columns. The complete per-state decision matrix — every combination of `AHEAD`/`BEHIND`/`DIRTY`/`STASHES`/`UPSTREAM`/`DETACHED`, what it means, and the exact safe command — lives in `reference/playbook.md`. Read it whenever a checkout's state is not obvious, or before running a command you are unsure preserves work.

## 4) Report
End every run with a compact, actionable summary:
- **Done** — per repo, what happened (pulled / pushed / committed / rebased / worktrees removed), as a short list.
- **Needs you** — conflicts to resolve, dirty trees left uncommitted, stashes still parked, detached HEADs, `none`-upstream branches, fetch failures. Each with its path so the user can act.
- **Morning only** — remind the user to **restart Claude Code** for plugin updates to take effect.

Keep it short; spell out detail only where the user must act.

## Guardrails
- **Scan + plan before any mutation**, and confirm hard-to-reverse steps (commit, force-with-lease, worktree removal). Never on a schedule, never unprompted.
- **Never discard work.** No `git reset --hard`, no `checkout -- <file>` over dirty files, no `stash drop`, no `worktree remove --force`, no deleting an unpushed branch. "Identical" means *everything committed is pushed and everything remote is pulled* — not that local is overwritten to match remote. Anything that will not reconcile cleanly is **surfaced, not destroyed**.
- **Stage explicit paths only** (`git add -- <paths>`); never `git add -A`/`.`/`-u` (the git-guard blocks it) — so a concurrent session's files never ride into a commit.
- In the sweep, **skip the worktree you are standing in, dirty worktrees, and never-pushed branches.**
- Secrets and binaries never enter git (the `pre-commit` guard enforces it); text / code / Markdown only.
- **Defer per-repo mechanics to `yar:git-workflow`** (conflicts, rebase recovery, worktree detail) — don't reinvent them here.

## References
- `reference/playbook.md` — the full per-state decision matrix (ahead / behind / diverged / dirty / stash / detached / no-upstream / gone), conflict and offline handling, the plugin-update loop, configuring scan roots, and how daily-sync relates to git-workflow. **Read it when a checkout's state isn't obvious or a step needs the exact command.**
- `scripts/scan-repos.sh` — the read-only scanner that produces the status table the routines reason over. `--fetch` to refresh remote-tracking refs; `--help` for roots and columns.
- Relies on **`yar:git-workflow`** for the branch / commit / rebase / PR / worktree mechanics.
