# recipes — ready-to-use commands for resolving conflicts and recovery

> Open this when work gets "tangled." Read each command before running it; the ones marked with `--force` or `reset --hard` rewrite history/files.

## I accidentally committed on `main` (haven't pushed yet)
Move the commits to a branch and reset `main` back to the remote:
```bash
git branch feat/save-my-work        # mark the current commits onto a branch
git reset --hard origin/main        # pull local main back (the commits are safe on the branch)
git switch feat/save-my-work        # continue working on the branch
```
If you've **already pushed too**, don't force `main` on your own — create a branch from that point, open a PR, and coordinate with your team.

## Branch is behind / PR has a conflict
```bash
git fetch origin
git rebase origin/main              # replay the branch onto the latest main
# for each conflicting file: open it, resolve the <<<<<<< ======= >>>>>>> markers, then:
git add path/to/resolved-file
git rebase --continue               # repeat until all commits are done
git push --force-with-lease         # safely update the branch remote (not raw --force)
```
`--force-with-lease` prevents overwriting someone's work if they pushed to the same branch at the same time.

## The rebase broke, forget it
```bash
git rebase --abort                  # go back to the state before the rebase
```

## I messed up a merge/rebase/reset and want to go back
Every HEAD change is recorded in the `reflog`:
```bash
git reflog                          # list of previous points with HEAD@{n}
git reset --hard HEAD@{3}           # go back to the good point (pick n correctly)
```

## `git pull` keeps creating a merge commit
Set pull to rebase once and for all:
```bash
git config pull.rebase true         # this repo only; for everywhere: --global
```

## In the middle of my work, I need to do something else urgently
```bash
git stash                           # temporarily set aside your working changes
# ... the urgent task / switching branches ...
git stash pop                       # restore the changes
```

## I forgot to create a branch, changed things on main but haven't committed yet
`git switch -c` carries the uncommitted changes with it to the new branch:
```bash
git switch -c feat/my-work          # now on a branch; main is untouched
```

## Discard / unstage local changes to a file
```bash
git restore path/to/file            # discard uncommitted changes (irreversible)
git restore --staged path/to/file   # unstage (the changes remain)
```

## I committed a file that belongs to another session (last commit, not pushed)
Back the file out of your commit **without** losing the other session's work — its content stays in the working tree for them:
```bash
git reset --soft HEAD~1                    # undo the commit; everything it had stays staged
git restore --staged path/to/their-file    # unstage just their file (its changes remain in the working tree)
git diff --cached --name-only              # confirm only YOUR files are left staged
git commit -m "type(scope): your message" -- your/file.md  # re-commit your own files (pathspec = no re-contamination)
```

## My commit swept in another session's files **and I already pushed it**
Don't reset/force-push the shared branch — the contaminated commit may be the only copy of the other session's in-progress work, and a branch-switch can revert their uncommitted edits off disk. Instead, build a **clean commit in an isolated worktree, sourced from the bad commit** (never from the churning shared working tree), then leave the bad branch untouched for the other session to recover from:
```bash
git fetch origin
git worktree add ../<repo>-clean -b <type>/<summary> origin/main   # isolated checkout off latest main
cd ../<repo>-clean
git checkout <bad-commit-sha> -- your/file1 your/file2             # bring ONLY your files, from the commit
git status --short                                                 # confirm: exactly your files, nothing else
git commit -m "type(scope): your message" -- your/file1 your/file2
git push -u origin HEAD && gh pr create --fill && gh pr merge --squash --delete-branch
cd - && git worktree remove ../<repo>-clean                        # immediate cleanup
```
The other session's work stays intact on the original (pushed) branch; it can recover its files from that commit the same way.

## A binary/secret file got staged by mistake (the pre-commit hook caught it)
```bash
git restore --staged path/to/file.pdf   # unstage it
# binary → external storage (not git) · secret → .env (which is in .gitignore)
```
