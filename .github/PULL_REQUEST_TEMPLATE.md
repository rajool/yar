<!-- Thanks for contributing to yar! Keep changes generic, public, and English-only. -->

## What & why

<!-- What does this change, and why? Link any issue, e.g. "Closes #123". -->

## Type of change

- [ ] `feat` — new skill / agent / capability
- [ ] `fix` — bug fix
- [ ] `docs` — documentation only
- [ ] `refactor` / `chore` — no user-facing behavior change

## Checklist

- [ ] `python3 -m unittest discover -s tests` passes
- [ ] `ruff check .` and `shellcheck` are clean (if I touched Python / shell)
- [ ] `validate.py` passes for any skill I changed
- [ ] Content is generic, public, and English-only (no secrets, private paths, or personal data)
- [ ] Bumped `version` in `.claude-plugin/plugin.json` and updated `CHANGELOG.md` (for user-facing changes)
- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
