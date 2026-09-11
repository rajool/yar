# Skill testing, evaluation, and iteration (methodology)

> Cited reference for `skill-builder`. Once the skill draft is ready and you want to truly measure whether it works and make it better, read this file.
> Adapted from Anthropic's official `skill-creator` skill. The entire manual method is here; for the two heavy automated tools (section 8) we refer to skill-creator.

## Contents
1. [When an eval is needed](#1-when-an-eval-is-needed)
2. [Building a test prompt](#2-building-a-test-prompt)
3. [The evals.json file](#3-evalsjson)
4. [Running with-skill against baseline](#4-running)
5. [Objective assertions and grading](#5-grade)
6. [Manual benchmark](#6-benchmark)
7. [The improvement loop](#7-improvement)
8. [Description optimization + optional heavy tools](#8-description-opt)
9. [Sources](#9-sources)

---

## 1) When an eval is needed
- **Objective/verifiable** output (file conversion, data extraction, code generation, the fixed steps of a workflow) → an eval is worthwhile.
- **Subjective** output (writing style, design, art) → usually no assertion is needed; judge it with human judgment.
Propose a sensible default but the user decides. (Source: skill-creator → Capture Intent)

## 2) Building a test prompt
After the draft, build 2–3 **real** prompts — something a real user would actually type. Specific and detailed: file name, path, amount, date, context. Show them to the user and get confirmation: "I want to run these few sample tests; are they right, or should I add anything?"
- Bad: "Format this data."
- Good: "My boss sent this Q4.xlsx file to Downloads; add a profit-margin column as a percentage; revenue is column C, cost is column D."

## 3) evals.json
Start from `assets/evals-template.json`. First just the prompts (without assertions); add the assertions in the next step, during the run.
```json
{
  "skill_name": "example-skill",
  "evals": [
    { "id": 1, "prompt": "the user's request", "expected_output": "the expected output", "files": [], "assertions": [] }
  ]
}
```

## 4) Running
For each test case, **in one go** spawn two subagents with the Agent tool so they finish at the same time:
- **with-skill:** do the work with the skill loaded; save the output to `<skill>-workspace/iteration-<N>/eval-<id>/with_skill/outputs/`.
- **baseline:** the same prompt — for a new skill **without the skill**; for improving an existing skill **the old version** (first take a snapshot with `cp -r`). In `without_skill/` or `old_skill/`.

If you don't have a subagent (e.g. a simple environment), read SKILL.md yourself and run each prompt manually, one by one — a less rigorous measure but useful; human review makes up for it. (Source: skill-creator → Running and evaluating / Claude.ai-specific)

## 5) grade
For each assertion, write it objectively and verifiably and measure the result against the output. If something can be checked programmatically, write a short script (faster and reusable) instead of doing it by eye. Output of each assertion: text + passed (yes/no) + evidence. (Source: skill-creator → Step 4 / schemas.md)

## 6) benchmark
Gather the results: the pass rate of the assertions, and the time/tokens if you have them (from the completion notification of each subagent). Put with-skill next to baseline so it's clear "did the skill actually make it better?" If you don't have a baseline (simple environment), drop the quantitative benchmark and focus on the user's qualitative feedback.

## 7) improvement
The heart of the work. After seeing the results:
1. **Generalize, don't overfit.** The goal is a skill that works on thousands of prompts, not just these few samples. Instead of a tiny change specific to one example or smothering MUSTs, if a problem is stubborn try a different metaphor/pattern.
2. **Keep the prompt light.** Remove anything that doesn't pull its weight. Read the run transcript, not just the final output — if the skill sends the model on useless work, remove that part.
3. **Explain the "why".** The model is smart; give it a reason so it acts beyond a dry instruction. Seeing ALWAYS/NEVER in capitals = a yellow flag.
4. **Bundle repetitive work.** If across several tests the subagents all wrote a similar helper script, put it in `scripts/` once and tell the skill to use it.

The loop: improve → run all the tests again in `iteration-<N+1>/` → get feedback → repeat. Stop when: the user is satisfied, the feedback is empty, or meaningful progress has stalled. (Source: skill-creator → Improving the skill / The iteration loop)

## 8) description-opt
The description is the most important trigger lever. After the skill is good, the **manual** method:
- Build ~20 queries: 8–10 "should activate" (different phrasings of one intent, formal/casual, even without the skill's explicit name) + 8–10 "should not activate" (especially near-misses that share a keyword but are a different task). The queries should be real and detailed.
- Test the description against these; fix wherever it triggered incorrectly; repeat. Test on the held-out queries so it doesn't overfit.

**Optional heavy automated tools (not re-implemented here — use them directly from skill-creator):**
- Automatic description optimizer: `python -m scripts.run_loop --eval-set <...> --skill-path <...> --model <model-id> --max-iterations 5` (60/40 train/test, up to 5 iterations, returns `best_description`).
- HTML viewer for human review of outputs/benchmark: `eval-viewer/generate_review.py`.
Both are in the skill-creator folder. For everyday work the manual method is usually enough.

## 9) sources
- Anthropic's official `skill-creator` skill (`SKILL.md`, `references/schemas.md`, `scripts/run_loop.py`, `eval-viewer/generate_review.py`).
- platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices — triggering mechanism and skill selection.
