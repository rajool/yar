# Security Policy

`yar` is a Claude Code plugin. Once enabled, it ships hooks that run small
shell/Python guard scripts before certain tool calls, an installer that writes a
git `pre-commit` hook into your repository, and (on macOS) a self-built audio
recorder. Because these components execute on your machine, security reports are
taken seriously.

## Supported versions

Only the latest released version receives security fixes. `yar` is distributed
through a plugin marketplace, so a fix ships in the next version bump.

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability):

1. Open the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, the affected component, and a reproduction if you have one.

You can expect an initial response within a few days. When a fix is ready it is
released in a new version and noted in [`CHANGELOG.md`](CHANGELOG.md).

## Scope

The areas most worth scrutiny:

- **Guard hooks** (`scripts/*.py`, `.claude/hooks/*.py`) — a bypass that lets a
  blocked pattern through (e.g. `rm -rf`, bulk/force `git add`, a committed
  secret, or non-generic content in CI).
- **`pre-commit` hook and installers** (`scripts/install.sh`,
  `scripts/pre-commit`, `scripts/install-perms.py`) — anything that writes
  outside its intended target or mishandles an existing hook.
- **Meeting recorder** (`skills/meeting-recorder/`) — the CoreAudio capture and
  build/sign path.
- Any handling of API keys (`GEMINI_API_KEY`, `ELEVENLABS_API_KEY`).

## A note on the guards

The guards are a **safety net, not a sandbox**. They
[fail open](CONTRIBUTING.md) by design: if a script errors or cannot decide, the
action is allowed, so legitimate work is never blocked. They exist to prevent
*mistakes* — they are not a security boundary against someone who already has
shell access. Report bypasses anyway: reducing the mistake surface is the goal.
