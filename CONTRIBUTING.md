# Contributing to yar

Thanks for contributing! yar is a public, reusable Claude Code plugin. This guide
covers how to set up, make a change, run the checks, and the two repo-wide rules that
keep it shareable. The rules are enforced automatically, so you rarely have to think
about them — but here is what they mean and how to proceed if a guard stops you.

## Development setup

```bash
git clone https://github.com/rajool/yar
cd yar
claude --plugin-dir .        # load the plugin in Claude Code without installing it
```

The skills themselves need no build step or dependencies. The tooling below is only for
running the checks locally; CI runs the same checks on every pull request.

## Making a change

Work on a short-lived branch, keep `main` clean, and squash-merge your own PR. The
bundled `yar:git-workflow` skill runs this flow for you ("create a branch", "commit
this", "open a PR", "merge this"). The guards enforce the safety rails: no bulk/force
`git add`, no edits on `main`, no binaries or secrets in a commit.

- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): summary`, where `type` is one of `feat fix docs chore refactor`.
- **User-facing changes** bump `version` in
  [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) and add an entry to
  [`CHANGELOG.md`](CHANGELOG.md) (Keep a Changelog format).
- **Adding a skill?** Use the `yar:skill-builder` skill — it scaffolds
  `skills/<name>/SKILL.md`, validates it, and follows the Agent Skills standard. Then
  update the catalog table in [`README.md`](README.md).

## Running the checks

These mirror [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

```bash
python3 -m unittest discover -s tests -v                       # tests — no dependencies
for d in skills/*/; do python3 skills/skill-builder/scripts/validate.py "$d"; done
ruff check .                                                   # pip install ruff  (or: uvx ruff check .)
shellcheck $(git ls-files '*.sh') scripts/pre-commit           # brew install shellcheck
npx markdownlint-cli2                                          # needs Node
```

The guard scripts stay **dependency-free at runtime** (only Python 3 and standard Unix
tools). Ruff, ShellCheck, and markdownlint are development/CI tools only.

## Repo-wide rules

### 1. English only

All source, docs, comments, and filenames must be in English (no non-Latin scripts).

- Enforced at write time by `.claude/hooks/english-guard.py` (a Claude Code PreToolUse hook).
- If it blocks you: rewrite the content in English and try again.
- This rule is about *this repo*. yar's own skills still work on users' non-English files
  at runtime — that is expected and unaffected.
- Rare local bypass: `ENGLISH_GUARD=off`.

### 2. No private / context-specific content

Everything here must be generic and public. Do not commit content tied to a specific
person, company, or machine:

- personal email addresses (a placeholder like `you@example.com` is fine)
- absolute home paths (write `/Users/you/...`, not a real user's directory)
- secrets / API keys / private keys (real secrets belong in a gitignored `.env`)
- references to private or internal systems by name

Enforced in two places:

- **Write time** — `.claude/hooks/context-guard.py` (PreToolUse hook), for fast local feedback.
- **Merge gate** — the `no-context` GitHub Actions check (`.github/workflows/no-context.yml`)
  re-scans every pull request. If it finds private content, the check fails and the PR
  should not be merged.

If a guard stops you, here is how to continue:

| Situation | What to do |
|---|---|
| It is real private content | Remove it or replace it with a placeholder, then re-push. |
| Genuine false positive (a placeholder that only looks real) | Add the marker `context-guard:allow` on that line. |
| A private term keeps recurring and you want it blocked repo-wide | Add it to `.claude/hooks/context-denylist.local.txt` (gitignored — never committed). |

Local one-off bypass for the Claude hook only: `CONTEXT_GUARD=off`. The CI merge gate has
no bypass, on purpose.

## Code of Conduct

By participating, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
