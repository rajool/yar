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
# Optional variables:
#   GEMINI_MODEL    pin to ONE model (skips the fallback ladder). e.g. gemini-2.5-flash-lite
#   GEMINI_TIMEOUT  per-attempt timeout in seconds (default 420).
#
# Why a model ladder (2026): the free tier gives gemini-2.5-pro a quota of *zero*
# ("limit: 0" → instant "Quota exceeded / unexpected critical error"). flash and
# flash-lite are the usable free models, and they have daily caps that reset ~midnight
# Pacific. So we DON'T default to pro: we try flash, then flash-lite, each time-boxed,
# and fail fast with a clear message instead of hanging.

set -uo pipefail   # NB: not -e — we handle gemini failures ourselves and fall back.

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

# --- Portable per-attempt timeout (macOS has no `timeout` by default) ---
run_with_timeout() {
  local secs="$1"; shift
  if command -v gtimeout >/dev/null 2>&1; then gtimeout "$secs" "$@";
  elif command -v timeout >/dev/null 2>&1; then timeout "$secs" "$@";
  else perl -e '$t=shift;alarm $t;exec @ARGV' "$secs" "$@"; fi
}

# --- Model ladder: explicit override wins; otherwise the free-tier ladder (NO pro) ---
if [ -n "${GEMINI_MODEL:-}" ]; then
  MODELS=("$GEMINI_MODEL")
else
  MODELS=("gemini-2.5-flash" "gemini-2.5-flash-lite")
fi
TIMEOUT="${GEMINI_TIMEOUT:-420}"

# Run in an isolated temp folder so that even in yolo mode it never writes into your project
SCRATCH="$(mktemp -d)"
TMP_OUT="$(mktemp)"
TMP_ERR="$(mktemp)"
trap 'rm -rf "$SCRATCH" "$TMP_OUT" "$TMP_ERR"' EXIT
cd "$SCRATCH"

FATAL_OUT='An unexpected critical error occurred'
QUOTA_RE='Quota exceeded for metric|RESOURCE_EXHAUSTED|limit: 0|status.?429|Too Many Requests|429 '
AUTH_RE='API key|API_KEY_INVALID|PERMISSION_DENIED|unauthor|status.?401|status.?403'

ok=0; used_model=""
for M in "${MODELS[@]}"; do
  echo "[gemini-research] trying model: $M (timeout ${TIMEOUT}s)…" >&2
  : > "$TMP_OUT"; : > "$TMP_ERR"
  run_with_timeout "$TIMEOUT" gemini --model "$M" --approval-mode yolo --skip-trust -o text -p "$PROMPT" >"$TMP_OUT" 2>"$TMP_ERR"
  rc=$?

  # Success = clean exit, real output, no fatal crash marker, no quota marker in stderr, and not a stub.
  out_bytes=$(wc -c < "$TMP_OUT" | tr -d ' ')
  if [ "$rc" -eq 0 ] && [ "${out_bytes:-0}" -gt 200 ] \
     && ! grep -qF "$FATAL_OUT" "$TMP_OUT" \
     && ! grep -qiE "$QUOTA_RE" "$TMP_ERR"; then
    ok=1; used_model="$M"; break
  fi

  # Classify the failure so the log is actionable.
  if grep -qiE "$QUOTA_RE" "$TMP_ERR" "$TMP_OUT"; then
    echo "[gemini-research] ⚠ $M: free-tier quota exhausted / not available — falling back." >&2
  elif [ "$rc" -eq 124 ] || [ "$rc" -eq 142 ]; then
    echo "[gemini-research] ⚠ $M: timed out after ${TIMEOUT}s — falling back." >&2
  elif grep -qiE "$AUTH_RE" "$TMP_ERR" "$TMP_OUT"; then
    echo "[gemini-research] ✖ authentication problem — set GEMINI_API_KEY (in .env) or run 'gemini' once to log in. Stopping." >&2
    break   # another model won't fix auth
  else
    echo "[gemini-research] ⚠ $M: failed (exit $rc, ${out_bytes:-0} bytes) — falling back." >&2
  fi
done

if [ "$ok" -ne 1 ]; then
  {
    echo "[gemini-research] ✖ FAILED — Gemini free-tier research did not succeed."
    echo "[gemini-research]   Likely cause: free-tier quota. gemini-2.5-pro is limit:0 on the free tier;"
    echo "[gemini-research]   flash / flash-lite have daily caps that reset ~midnight Pacific; web grounding can 429."
    echo "[gemini-research]   Options:"
    echo "[gemini-research]     1) retry after the daily reset;"
    echo "[gemini-research]     2) pin the lightest model:  GEMINI_MODEL=gemini-2.5-flash-lite bash <this script> \"…\" out.md"
    echo "[gemini-research]     3) use a billed key / the paid skill  boote:gemini-research-paid;"
    echo "[gemini-research]     4) fall back to Claude's own /deep-research."
    echo "---- last gemini stderr (tail) ----"
    tail -n 12 "$TMP_ERR"
  } >&2
  exit 1
fi

if [ -n "$OUTFILE" ]; then
  cp "$TMP_OUT" "$OUTFILE"
  echo "[gemini-research] ✅ report written: $OUTFILE (model: $used_model)" >&2
else
  cat "$TMP_OUT"
  echo "[gemini-research] ✅ done (model: $used_model)" >&2
fi
