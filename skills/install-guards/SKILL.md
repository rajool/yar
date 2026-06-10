---
name: install-guards
description: Install the plugin's git-level pre-commit guard (blocks committing binaries/secrets) into the current repository. Run once per repo or clone. Invoked manually as /yar:install-guards; it does not auto-run.
disable-model-invocation: true
---

# install-guards — wire the git-level pre-commit guard into this repo

Install the plugin's git-level `pre-commit` guard into the **current** repository, then report the result.

Run:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/install.sh"
```

If `$CLAUDE_PLUGIN_ROOT` is empty in the shell, find the plugin's installer under `~/.claude/plugins/` (look for `yar/scripts/install.sh`) and run that instead.

After it succeeds, confirm to the user that:

- **git-guard** (blocks bulk/force `git add` and `git commit -a`) and **branch-guard** (blocks edits on `main`) are already active via the plugin's Claude hooks — they need no installation.
- the **pre-commit** guard now blocks committing binaries/secrets on **any** git client (terminal, GUI, Claude). Bypass a single commit with `git commit --no-verify`.
