---
name: <skill-name>
# ↑ kebab-case (a-z, 0-9, hyphen), ≤ 64 characters, exactly matching the folder name, no "--"
description: <write in the third person: what this skill does and exactly when it should activate. 100–1024 characters, no "<" and ">", a bit "pushy" with concrete trigger phrases>
---

# <skill-name> — <short title>

Goal: <in one or two sentences — what this skill does and when it's used. "What" goes here; "when" goes in the description.>

## 0) <first step — usually clarification or scope detection>
<if the input is ambiguous, ask 2–3 short questions and then continue; if it's clear, go straight ahead.>

## 1) <main step>
<write imperatively ("do this"), not descriptively. Briefly explain the "why" so the model can generalize. Avoid MUST/NEVER in capitals.>

```bash
# if there's a specific command/script, put it here with an example
```

## 2) <next step / output>
<state the output format explicitly if it matters — a fixed template if the shape matters.>

## 3) Update related docs (if it changed anything)
<if the project keeps an index/README/notes that this touches, update them in the same change — leave no stale doc.>

## Guardrails
- <this skill's safety limits.>
- Secrets (credentials, API keys) and binary files must **not** go into git — text/Markdown/code only.
- For regulated/high-stakes domains, gather facts but route the final interpretation to a qualified human/expert.

## References (only if the skill grows large — progressive disclosure)
<if SKILL.md approaches ~500 lines, move the details to the files below and point to them from here with a "when to read" note:>
- `reference/<topic>.md` — <what it is, when to read it>
- `assets/<file>` — <template/asset for the output>
- `scripts/<file>.py` — <repetitive/deterministic work that's better as a script>
