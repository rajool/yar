#!/bin/bash
# transcribe-video.sh — Turn any meeting recording (audio or video) into a
#                       transcript with speaker diarization using ElevenLabs
#                       Scribe v2 (batch).
#
# Why ElevenLabs Scribe v2 — a top-tier engine for recorded speech-to-text:
#   - State-of-the-art accuracy across many languages; strong on non-English
#     audio where general models tend to garble names. (model_id=scribe_v2 was
#     verified live against /v1/speech-to-text returning 200.)
#   - scribe_v2 is the BATCH model, purpose-built for recorded audio/video.
#     (scribe_v2_realtime is a separate low-latency model for live agents —
#     fewer languages, lower accuracy. NOT used here; meetings are recorded.)
#   - Native speaker diarization (up to 32 speakers) + word-level timestamps.
#   - Single call handles long meetings (up to ~5GB / 10 hours) — no chunking.
#   - Optional keyterms prompting biases recognition toward proper nouns
#     (product names, people) that otherwise get garbled — see ELEVENLABS_KEYTERMS.
#   - Cheap: ~$0.13-0.22 per audio hour (+~20% when keyterms are used).
#
# Usage:
#   transcribe-video.sh <input> [output_path] [num_speakers]
#
# Input forms accepted:
#   - Local file path:       /path/to/recording.mp4   (mp4/mov/mp3/m4a/wav/webm/…)
#   - Google Drive file ID:  1FgYxLZOgAjqz7VczcoYIOF5Fux6Mk5VH  (script guides you to download)
#   - Google Drive URL:      https://drive.google.com/file/d/.../view
#
# Output:
#   - Default: $PWD/transcripts/<sanitized-stem>.md   (override dir: MEETING_TRANSCRIPT_DIR)
#   - Or as specified in the 2nd arg
#   - Also writes <output>.raw.json with the full API response (segments + words + speakers)
#
# Environment:
#   ELEVENLABS_API_KEY   required. Resolved from (in order): the environment,
#                        $PWD/.claude/settings.local.json (.env.ELEVENLABS_API_KEY),
#                        or $PWD/.env (ELEVENLABS_API_KEY=…).
#   ELEVENLABS_LANG      ISO-639-3 language hint (e.g. eng, fas, spa). Default:
#                        empty → Scribe auto-detects the language.
#   ELEVENLABS_KEYTERMS  comma-separated proper nouns to bias toward (e.g.
#                        "Acme,Jane Doe,Project Atlas"). Default: none.
#   GEMINI_API_KEY       optional. Enables the automatic FALLBACK engine
#                        (transcribe-gemini.sh) when ElevenLabs is unreachable
#                        (HTTP 000/403 — some networks' exit IPs are blocked at
#                        ElevenLabs' edge), out of quota (429), or down (5xx).
#                        Resolved from the same three places as the main key.
#   MEETING_TRANSCRIPT_DIR  output directory (default: $PWD/transcripts)
#
# Requirements: ffmpeg (audio extraction), curl, jq.

set -euo pipefail

# ---------- Constants ----------
ELEVENLABS_MODEL="scribe_v2"   # ONLY model. State-of-the-art batch STT. Do not downgrade to scribe_v1.
ELEVENLABS_LANG="${ELEVENLABS_LANG:-}"   # empty → auto-detect
AUDIO_BITRATE="64k"
AUDIO_RATE="16000"
API_BASE="https://api.elevenlabs.io/v1"

# ---------- Keyterms (optional — bias transcription toward proper nouns) ----------
# Keyterms MUST be sent as repeated -F "keyterms=<term>" fields (a JSON-array
# string is rejected with HTTP 400). Non-Latin scripts are accepted.
#   Supply:  ELEVENLABS_KEYTERMS="Acme,Jane Doe,Project Atlas"
#   Default: none (generic — this tool makes no assumptions about your domain).
KEYTERMS=()
if [ -n "${ELEVENLABS_KEYTERMS:-}" ]; then
  KT_LOWER=$(printf '%s' "$ELEVENLABS_KEYTERMS" | tr '[:upper:]' '[:lower:]')
  if [ "$KT_LOWER" != "none" ] && [ "$KT_LOWER" != "off" ]; then
    OLD_IFS="$IFS"; IFS=','; read -r -a KEYTERMS <<< "$ELEVENLABS_KEYTERMS" || true; IFS="$OLD_IFS"
  fi
fi

# ---------- Paths ----------
DEFAULT_OUT_DIR="${MEETING_TRANSCRIPT_DIR:-$PWD/transcripts}"

# ---------- Helpers ----------
usage() {
  cat >&2 <<'EOF'
Usage: transcribe-video.sh <input> [output_path] [num_speakers]

Input forms:
  - Local file:  /path/to/recording.mp4
  - Drive ID:    1FgYxLZOgAjqz7VczcoYIOF5Fux6Mk5VH
  - Drive URL:   https://drive.google.com/file/d/.../view

  <input>          local file path (mp4/mov/mp3/m4a/wav/webm/…)
  [output_path]    target .md path (default: $PWD/transcripts/<stem>.md)
  [num_speakers]   expected speaker count, helps diarization accuracy (default: auto-detect)

Required:
  ELEVENLABS_API_KEY in env, .claude/settings.local.json, or .env
  ffmpeg, curl, jq

Example:
  transcribe-video.sh ~/Downloads/meeting.mp4 "" 5
EOF
  exit 1
}

err() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "$*" >&2; }

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# A Gemini key anywhere (env → settings.local.json → .env) enables the fallback
# engine (transcribe-gemini.sh) when ElevenLabs is unreachable or out of quota.
gemini_key_available() {
  [ -n "${GEMINI_API_KEY:-}" ] && return 0
  if [ -f "$PWD/.claude/settings.local.json" ]; then
    [ -n "$(jq -r '.env.GEMINI_API_KEY // empty' "$PWD/.claude/settings.local.json" 2>/dev/null || true)" ] && return 0
  fi
  if [ -f "$PWD/.env" ]; then
    grep -qE '^GEMINI_API_KEY=.+' "$PWD/.env" 2>/dev/null && return 0
  fi
  return 1
}

fallback_to_gemini() {
  log ""
  log "==> Falling back to the Gemini engine: $1"
  log "    (diarization will be approximate — resolve speaker identities from content)"
  exec "$SCRIPT_DIR/transcribe-gemini.sh" "$INPUT" "$OUT_PATH" "$NUM_SPEAKERS"
}

# ---------- Parse args ----------
[ "$#" -ge 1 ] || usage
INPUT="$1"
OUT_PATH="${2:-}"
NUM_SPEAKERS="${3:-}"

# ---------- Tool check ----------
command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg not installed. Run: brew install ffmpeg"
command -v curl   >/dev/null 2>&1 || err "curl not installed"
command -v jq     >/dev/null 2>&1 || err "jq not installed. Run: brew install jq"

# ---------- API key resolution (env → settings.local.json → .env) ----------
if [ -z "${ELEVENLABS_API_KEY:-}" ] && [ -f "$PWD/.claude/settings.local.json" ]; then
  ELEVENLABS_API_KEY=$(jq -r '.env.ELEVENLABS_API_KEY // empty' "$PWD/.claude/settings.local.json" 2>/dev/null || true)
fi
if [ -z "${ELEVENLABS_API_KEY:-}" ] && [ -f "$PWD/.env" ]; then
  ELEVENLABS_API_KEY="$(grep -E '^ELEVENLABS_API_KEY=' "$PWD/.env" 2>/dev/null | head -1 | cut -d '=' -f2- || true)"
fi
if [ -z "${ELEVENLABS_API_KEY:-}" ]; then
  if gemini_key_available; then
    fallback_to_gemini "ELEVENLABS_API_KEY not set, but a GEMINI_API_KEY is available"
  fi
  err "ELEVENLABS_API_KEY not set (env, .claude/settings.local.json, or .env) — and no GEMINI_API_KEY for the fallback engine"
fi

# ---------- Input resolution ----------
FILE_PATH=""

# Match Google Drive URL with file ID
if [[ "$INPUT" =~ ^https?://drive\.google\.com/.*[/=]([a-zA-Z0-9_-]{20,}) ]]; then
  DRIVE_ID="${BASH_REMATCH[1]}"
  log "Detected Google Drive URL → file ID: $DRIVE_ID"
  log ""
  log "This script does not download from Drive directly (needs OAuth)."
  log "Download the file, then re-run with the local path:"
  log ""
  log "    open 'https://drive.google.com/uc?export=download&id=$DRIVE_ID&confirm=t'"
  log ""
  exit 2
elif [[ "$INPUT" =~ ^[a-zA-Z0-9_-]{20,}$ ]]; then
  DRIVE_ID="$INPUT"
  log "Detected Google Drive file ID: $DRIVE_ID"
  log ""
  log "This script does not download from Drive directly (needs OAuth)."
  log "Download the file, then re-run with the local path:"
  log ""
  log "    open 'https://drive.google.com/uc?export=download&id=$DRIVE_ID&confirm=t'"
  log ""
  exit 2
elif [ -f "$INPUT" ]; then
  FILE_PATH="$INPUT"
else
  err "input not recognized as local file, Drive ID, or Drive URL: $INPUT"
fi

# ---------- Output path ----------
if [ -z "$OUT_PATH" ]; then
  mkdir -p "$DEFAULT_OUT_DIR"
  BASENAME=$(basename "$FILE_PATH")
  STEM="${BASENAME%.*}"
  # Sanitize: spaces→dashes, drop non-portable chars
  STEM=$(echo "$STEM" | tr ' ' '-' | tr -cd 'A-Za-z0-9._-')
  OUT_PATH="$DEFAULT_OUT_DIR/${STEM}.md"
fi

OUT_DIR=$(dirname "$OUT_PATH")
mkdir -p "$OUT_DIR"

# ---------- Work dir ----------
WORK_DIR=$(mktemp -d -t transcribe-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

# ---------- [1/3] Extract audio ----------
log "[1/3] Extracting audio (mono ${AUDIO_BITRATE} mp3, ${AUDIO_RATE}Hz) from $(basename "$FILE_PATH") ..."
AUDIO_FILE="$WORK_DIR/audio.mp3"
ffmpeg -y -nostdin -loglevel error \
  -i "$FILE_PATH" \
  -vn -ac 1 -b:a "$AUDIO_BITRATE" -ar "$AUDIO_RATE" \
  "$AUDIO_FILE"

AUDIO_SIZE=$(stat -f%z "$AUDIO_FILE" 2>/dev/null || stat -c%s "$AUDIO_FILE")
AUDIO_SIZE_MB=$((AUDIO_SIZE / 1024 / 1024))
log "      Audio: ${AUDIO_SIZE_MB}MB"

# ---------- [2/3] Call ElevenLabs Scribe API ----------
log "[2/3] Calling ElevenLabs Scribe API (model=$ELEVENLABS_MODEL, lang=${ELEVENLABS_LANG:-auto}, diarize=true) ..."
RESPONSE_FILE="$WORK_DIR/response.json"

# Build curl args
CURL_ARGS=(
  -sS
  -X POST
  "$API_BASE/speech-to-text"
  -H "xi-api-key: $ELEVENLABS_API_KEY"
  -F "file=@$AUDIO_FILE"
  -F "model_id=$ELEVENLABS_MODEL"
  -F "diarize=true"
  -F "timestamps_granularity=word"
  -F "tag_audio_events=false"
)
if [ -n "$ELEVENLABS_LANG" ]; then
  CURL_ARGS+=(-F "language_code=$ELEVENLABS_LANG")
fi
if [ -n "$NUM_SPEAKERS" ]; then
  CURL_ARGS+=(-F "num_speakers=$NUM_SPEAKERS")
  log "      num_speakers: $NUM_SPEAKERS"
else
  log "      num_speakers: auto-detect"
fi
if [ "${#KEYTERMS[@]}" -gt 0 ]; then
  for kt in "${KEYTERMS[@]}"; do CURL_ARGS+=(-F "keyterms=$kt"); done
  log "      keyterms: ${#KEYTERMS[@]} terms"
else
  log "      keyterms: none"
fi

# Capture HTTP status code separately by writing body to file.
# A transport failure (no connection at all) must not kill the script here —
# it is a fallback trigger, so map it to status 000.
HTTP_STATUS=$(curl -w "%{http_code}" -o "$RESPONSE_FILE" "${CURL_ARGS[@]}") || HTTP_STATUS="000"

if [ "$HTTP_STATUS" != "200" ]; then
  log "      HTTP $HTTP_STATUS"
  cat "$RESPONSE_FILE" >&2 2>/dev/null || true
  # Transport/access failures → try the fallback engine if a Gemini key exists:
  #   000 = no connection · 403 = ElevenLabs' edge blocks this exit IP
  #   (datacenter/VPN — even keyless requests get 403) · 429 = quota
  #   exhausted · 5xx = service down.
  # Config errors (400/401/422) stay fatal: falling back would mask a bug the
  # user should fix (bad key, bad request).
  case "$HTTP_STATUS" in
    000|403|429|5??)
      if gemini_key_available; then
        fallback_to_gemini "ElevenLabs API unreachable/refused (HTTP $HTTP_STATUS)"
      fi
      err "ElevenLabs API returned HTTP $HTTP_STATUS (no GEMINI_API_KEY available for the fallback engine)"
      ;;
    *)
      err "ElevenLabs API returned HTTP $HTTP_STATUS"
      ;;
  esac
fi

# Check for error in body
ERR_MSG=$(jq -r '.detail.message // .detail // .error // empty' "$RESPONSE_FILE" 2>/dev/null || true)
if [ -n "$ERR_MSG" ] && [ "$ERR_MSG" != "null" ]; then
  err "ElevenLabs API error: $ERR_MSG"
fi

# ---------- [3/3] Format output ----------
log "[3/3] Formatting transcript to $OUT_PATH ..."

OUT_STEM=$(basename "${OUT_PATH%.md}")
LANG_CODE=$(jq -r '.language_code // "unknown"' "$RESPONSE_FILE")
SPEAKER_COUNT=$(jq -r '[.words[]?.speaker_id // empty] | unique | length' "$RESPONSE_FILE")

{
  echo "# Transcript — $OUT_STEM"
  echo ""
  echo "**Source:** $FILE_PATH"
  echo "**Generated:** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "**Provider:** ElevenLabs Scribe (model=$ELEVENLABS_MODEL)"
  echo "**Language:** $LANG_CODE"
  echo "**Speakers detected:** $SPEAKER_COUNT"
  echo "**Keyterms biased:** ${#KEYTERMS[@]}"
  echo ""
  echo "---"
  echo ""
  echo "## Conversation (speaker-separated)"
  echo ""
  # Group consecutive words by speaker → produce one paragraph per turn
  # ElevenLabs returns .words[] (word-level with speaker_id) and .text (full).
  # We build turns by walking words[] and grouping consecutive same speaker_id.
  jq -r '
    if (.words | length) > 0 then
      [
        .words[] | select(.type == "word" or .type == null) |
        { spk: (.speaker_id // "unknown"), text: .text, start: .start, end: .end }
      ]
      | reduce .[] as $w ([];
          if (length == 0) or (.[-1].spk != $w.spk) then
            . + [{ spk: $w.spk, start: $w.start, end: $w.end, text: $w.text }]
          else
            (.[:-1]) + [{
              spk: .[-1].spk,
              start: .[-1].start,
              end: $w.end,
              text: (.[-1].text + " " + $w.text)
            }]
          end
        )
      | .[] | "**[\(.spk) — \(.start | tostring | .[0:7])s → \(.end | tostring | .[0:7])s]**  \(.text)\n"
    else
      .text // "(no transcript returned)"
    end
  ' "$RESPONSE_FILE"
  echo ""
  echo "---"
  echo ""
  echo "## Full text"
  echo ""
  jq -r '.text // ([.words[]? | select(.type == "word" or .type == null) | .text] | join(" "))' "$RESPONSE_FILE"
} > "$OUT_PATH"

cp "$RESPONSE_FILE" "${OUT_PATH%.md}.raw.json"

log ""
log "Transcript:  $OUT_PATH"
log "Raw JSON:    ${OUT_PATH%.md}.raw.json"
log "Speakers:    $SPEAKER_COUNT detected"
log ""
echo "$OUT_PATH"
