#!/usr/bin/env bash
# gemini-research.sh — non-interactive deep research with the Gemini CLI.
#
# Usage:
#   gemini-research.sh "<research question/topic>" [output file path]
#   - If you don't provide an output file, the report is printed to stdout.
#
# Authentication (either is enough):
#   • GEMINI_API_KEY in the environment, or in a .env file in the current working dir → fully automatic, no browser.
#   • Or run `gemini` interactively once and log in with Google (free); auth is saved in ~/.gemini.
#
# Optional variable:
#   GEMINI_MODEL   model name (default: the CLI's own choice — usually gemini-2.5-pro).

set -euo pipefail

# If the key isn't already in the environment, safely pull just that one line from a .env
# in the CURRENT working directory (the project where you're running). Done BEFORE any cd.
if [ -z "${GEMINI_API_KEY:-}" ] && [ -f "$PWD/.env" ]; then
  _k="$(grep -E '^GEMINI_API_KEY=' "$PWD/.env" 2>/dev/null | head -1 | cut -d '=' -f2- || true)"
  _k="${_k%$'\r'}"; _k="${_k#\"}"; _k="${_k%\"}"
  if [ -n "${_k:-}" ]; then export GEMINI_API_KEY="$_k"; fi
fi

QUESTION="${1:-}"
OUTFILE="${2:-}"
if [ -z "$QUESTION" ]; then
  echo "usage: gemini-research.sh \"<research question>\" [output_file]" >&2
  exit 2
fi

# Convert the output path to absolute before cd (since we run inside a temp folder)
if [ -n "$OUTFILE" ]; then
  case "$OUTFILE" in
    /*) : ;;
    *)  OUTFILE="$PWD/$OUTFILE" ;;
  esac
fi

PREAMBLE='You are a meticulous research analyst conducting DEEP, multi-source web research.
Rules:
- Use web search/browsing extensively. Consult MULTIPLE independent, authoritative sources; prefer official / primary / government sources over blogs and SEO content.
- Cross-check every key claim against at least two sources. Explicitly flag disagreements, gaps, and uncertainty.
- Prefer the most recent information available; state dates.
- NEVER fabricate facts, sources, or URLs. If you cannot verify something, say so plainly.
- Output Markdown with EXACTLY these sections:
  ## TL;DR  (3-6 bullets, direct answers)
  ## Key findings  (detailed; tag claims with [1],[2]... tied to Sources)
  ## Caveats & what to verify
  ## Sources  (numbered: title - full URL - date if known)
- Be information-dense and neutral. No filler.'

PROMPT="$PREAMBLE

# Research question / topic
$QUESTION"

# Model only if GEMINI_MODEL is explicitly set (compatible with bash 3.2 + set -u)
MODEL_ARGS=()
if [ -n "${GEMINI_MODEL:-}" ]; then MODEL_ARGS=(--model "$GEMINI_MODEL"); fi

# Run in an isolated temp folder so that even in yolo mode it never writes into your project
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cd "$SCRATCH"

if [ -n "$OUTFILE" ]; then
  gemini ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} --approval-mode yolo --skip-trust -o text -p "$PROMPT" > "$OUTFILE"
  echo "[gemini-research] ✅ report written: $OUTFILE" >&2
else
  gemini ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} --approval-mode yolo --skip-trust -o text -p "$PROMPT"
fi
