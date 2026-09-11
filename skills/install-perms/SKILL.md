---
name: install-perms
description: Merge yar's recommended permission policy (an allow-list plus a destructive-command deny-list) into the current repository's .claude/settings.local.json — the personal, git-ignored settings file, so the policy never gets committed or pushed. Run once per repo. Invoked manually as /yar:install-perms; it does not auto-run.
disable-model-invocation: true
---

# install-perms — merge yar's permission policy into this repo

Merge the plugin's recommended permission policy into the **current** repository's `.claude/settings.local.json` (the personal, git-ignored settings file — not the shared, committed `settings.json`), then report what changed.

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/install-perms.py"
```

If `$CLAUDE_PLUGIN_ROOT` is empty in the shell, find the plugin under `~/.claude/plugins/` (look for `yar/scripts/install-perms.py`) and run that instead.

After it succeeds, confirm to the user that:

- The **allow-list** (`Bash(*)`, `Read(*)`, `Edit(*)`, `Write(*)`, `Grep(*)`, `Glob(*)`, `WebSearch`) now auto-approves those common tools, so fewer permission prompts. It is **merged, not overwritten** — existing entries (and any other keys such as `hooks`) are preserved, and re-running is safe (idempotent).
- The policy lives in **`.claude/settings.local.json`** — personal and per-machine, so it never rides into a commit or a push and is never imposed on teammates. The script makes sure the file is git-ignored (adds it to `.gitignore` if needed, and warns if the file is somehow already tracked). Claude Code merges all settings sources, so permissions behave exactly as they would from the shared `settings.json`.
- The **deny-list** (`Bash(rm -rf *)`, `Bash(docker rm -f *)`) blocks those destructive commands; a settings `deny` always beats an `allow`, from any settings file.
- The plugin's **perms-guard** PreToolUse hook is the always-on, unbypassable backstop for the same destructive patterns — it works in every project the plugin is enabled in, with no install. This command is just the opt-in layer that is also visible in `/permissions`.
- To undo, edit `.claude/settings.local.json` and remove the entries (or `PERMS_GUARD=off <command>` to bypass the hook once). If an older run of this command put the policy into the shared `.claude/settings.json`, remove those entries there too if you no longer want them committed.
