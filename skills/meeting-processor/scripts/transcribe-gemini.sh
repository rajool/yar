#!/bin/bash
# transcribe-gemini.sh — Fallback transcription engine: turn a meeting recording
#                        (audio or video) into a speaker-labelled transcript with
#                        the Google Gemini API (audio understanding).
#
# Why this exists — ElevenLabs is the PRIMARY engine (transcribe-video.sh):
# Scribe's diarization and word timestamps are strictly better. But Scribe is
# unreachable from some networks (api.elevenlabs.io 403-blocks datacenter/VPN
# exit IPs at the network edge — even a keyless request gets 403), and a key
# can hit its quota. This script keeps the pipeline alive from such networks:
# transcribe-video.sh invokes it automatically on transport/access failures,
# or run it directly with the same CLI contract.
#
# Engine notes (learned the hard way — do not "simplify" these away):
#   - Upload via the Files API (resumable) — inline base64 blows the request
#     size limit for real meetings.
#   - MUST use :streamGenerateContent?alt=sse. The non-streaming
#     :generateContent call sits silent while Gemini processes long audio and
#     idle-killing middleboxes (VPNs, proxies) drop the connection (curl exit
#     16/52, empty reply). Streaming keeps bytes flowing.
#   - Default model gemini-2.5-flash: free-tier keys often have NO
#     gemini-2.5-pro quota at all ("limit: 0"). Override with GEMINI_MODEL.
#   - Diarization is approximate (no word-level timestamps, labels can slip at
#     turn boundaries) — the caller must resolve speaker_N identities from
#     content, not trust the labels blindly.
#
# Usage (same contract as transcribe-video.sh):
#   transcribe-gemini.sh <input> [output_path] [num_speakers]
#
# Output:
#   - Default: $PWD/transcripts/<sanitized-stem>.md  (override dir: MEETING_TRANSCRIPT_DIR)
#   - Also writes <output>.raw.txt with the model's verbatim output.
#
# Environment:
#   GEMINI_API_KEY       required. Resolved from (in order): the environment,
#                        $PWD/.claude/settings.local.json (.env.GEMINI_API_KEY),
#                        or $PWD/.env (GEMINI_API_KEY=…).
#   GEMINI_MODEL         model id (default: gemini-2.5-flash).
#   ELEVENLABS_LANG      ISO-639-3 language hint (e.g. eng, fas, spa) — same
#                        knob as the primary engine so callers set it once.
#   ELEVENLABS_KEYTERMS  comma-separated proper nouns to bias toward — same
#                        knob as the primary engine.
#   MEETING_TRANSCRIPT_DIR  output directory (default: $PWD/transcripts)
#
# Requirements: ffmpeg (audio extraction), curl, jq.

set -euo pipefail

# ---------- Constants ----------
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"
ELEVENLABS_LANG="${ELEVENLABS_LANG:-}"
AUDIO_BITRATE="64k"
AUDIO_RATE="16000"
API_BASE="https://generativelanguage.googleapis.com"

# ---------- Paths ----------
DEFAULT_OUT_DIR="${MEETING_TRANSCRIPT_DIR:-$PWD/transcripts}"

# ---------- Helpers ----------
usage() {
  cat >&2 <<'EOF'
Usage: transcribe-gemini.sh <input> [output_path] [num_speakers]

  <input>          local file path (mp4/mov/mp3/m4a/wav/webm/…)
  [output_path]    target .md path (default: $PWD/transcripts/<stem>.md)
  [num_speakers]   expected speaker count, sharpens the diarization prompt

Required:
  GEMINI_API_KEY in env, .claude/settings.local.json, or .env
  ffmpeg, curl, jq
EOF
  exit 1
}

err() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "$*" >&2; }

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
if [ -z "${GEMINI_API_KEY:-}" ] && [ -f "$PWD/.claude/settings.local.json" ]; then
  GEMINI_API_KEY=$(jq -r '.env.GEMINI_API_KEY // empty' "$PWD/.claude/settings.local.json" 2>/dev/null || true)
fi
if [ -z "${GEMINI_API_KEY:-}" ] && [ -f "$PWD/.env" ]; then
  GEMINI_API_KEY="$(grep -E '^GEMINI_API_KEY=' "$PWD/.env" 2>/dev/null | head -1 | cut -d '=' -f2- || true)"
fi
[ -n "${GEMINI_API_KEY:-}" ] || err "GEMINI_API_KEY not set (env, .claude/settings.local.json, or .env)"

# ---------- Input resolution ----------
[ -f "$INPUT" ] || err "input is not a local file: $INPUT (Drive inputs: download first — see transcribe-video.sh)"
FILE_PATH="$INPUT"

# ---------- Output path ----------
if [ -z "$OUT_PATH" ]; then
  mkdir -p "$DEFAULT_OUT_DIR"
  BASENAME=$(basename "$FILE_PATH")
  STEM="${BASENAME%.*}"
  STEM=$(echo "$STEM" | tr ' ' '-' | tr -cd 'A-Za-z0-9._-')
  OUT_PATH="$DEFAULT_OUT_DIR/${STEM}.md"
fi

OUT_DIR=$(dirname "$OUT_PATH")
mkdir -p "$OUT_DIR"

# ---------- Work dir ----------
WORK_DIR=$(mktemp -d -t transcribe-gemini-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

# ---------- [1/4] Extract audio ----------
log "[1/4] Extracting audio (mono ${AUDIO_BITRATE} mp3, ${AUDIO_RATE}Hz) from $(basename "$FILE_PATH") ..."
AUDIO_FILE="$WORK_DIR/audio.mp3"
ffmpeg -y -nostdin -loglevel error \
  -i "$FILE_PATH" \
  -vn -ac 1 -b:a "$AUDIO_BITRATE" -ar "$AUDIO_RATE" \
  "$AUDIO_FILE"

AUDIO_SIZE=$(stat -f%z "$AUDIO_FILE" 2>/dev/null || stat -c%s "$AUDIO_FILE")
AUDIO_SIZE_MB=$((AUDIO_SIZE / 1024 / 1024))
log "      Audio: ${AUDIO_SIZE_MB}MB"

# ---------- [2/4] Upload to the Gemini Files API (resumable) ----------
log "[2/4] Uploading audio to the Gemini Files API ..."
MIME="audio/mp3"

UPLOAD_URL=$(curl -sS -D - -o /dev/null \
  -X POST "$API_BASE/upload/v1beta/files?key=$GEMINI_API_KEY" \
  -H "X-Goog-Upload-Protocol: resumable" \
  -H "X-Goog-Upload-Command: start" \
  -H "X-Goog-Upload-Header-Content-Length: $AUDIO_SIZE" \
  -H "X-Goog-Upload-Header-Content-Type: $MIME" \
  -H "Content-Type: application/json" \
  -d '{"file":{"display_name":"meeting-transcription"}}' \
  | grep -i '^x-goog-upload-url:' | tr -d '\r' | cut -d ' ' -f2 || true)
[ -n "$UPLOAD_URL" ] || err "Gemini Files API did not return an upload URL (key invalid or API unreachable)"

FILE_JSON=$(curl -sS -X PUT "$UPLOAD_URL" \
  -H "X-Goog-Upload-Command: upload, finalize" \
  -H "X-Goog-Upload-Offset: 0" \
  -H "Content-Length: $AUDIO_SIZE" \
  --data-binary @"$AUDIO_FILE")
FILE_URI=$(echo "$FILE_JSON" | jq -r '.file.uri // empty')
FILE_NAME=$(echo "$FILE_JSON" | jq -r '.file.name // empty')
[ -n "$FILE_URI" ] || err "audio upload failed: $(echo "$FILE_JSON" | head -c 300)"
log "      Uploaded: $FILE_NAME"

# Wait for the file to become ACTIVE (Gemini processes uploads asynchronously)
STATE="PROCESSING"
for _ in $(seq 1 60); do
  STATE=$(curl -sS "$API_BASE/v1beta/$FILE_NAME?key=$GEMINI_API_KEY" | jq -r '.state // "UNKNOWN"')
  [ "$STATE" = "ACTIVE" ] && break
  sleep 5
done
[ "$STATE" = "ACTIVE" ] || err "uploaded file never became ACTIVE (state=$STATE)"

# ---------- [3/4] Transcribe via streaming generateContent ----------
log "[3/4] Transcribing with $GEMINI_MODEL (streaming) ..."

LANG_LINE=""
if [ -n "$ELEVENLABS_LANG" ]; then
  LANG_LINE="The spoken language is (ISO-639-3): $ELEVENLABS_LANG. Transcribe in that language."
fi
SPEAKERS_LINE="Auto-detect the number of speakers."
if [ -n "$NUM_SPEAKERS" ]; then
  SPEAKERS_LINE="There are $NUM_SPEAKERS speakers."
fi
KEYTERMS_LINE=""
if [ -n "${ELEVENLABS_KEYTERMS:-}" ]; then
  KEYTERMS_LINE="Proper nouns likely to occur (spell them exactly like this): ${ELEVENLABS_KEYTERMS}."
fi

PROMPT=$(cat <<EOF
This is a recorded meeting. Produce a VERBATIM speaker-diarized transcript.
$LANG_LINE
$SPEAKERS_LINE
$KEYTERMS_LINE

Rules:
- Transcribe faithfully, exactly as spoken (keep colloquial forms). Do NOT translate, summarize, or clean up.
- Label speakers consistently as speaker_0, speaker_1, ... (do not guess real names).
- One line per speaker turn, in exactly this format: [mm:ss] speaker_N: text
- The [mm:ss] timestamp is the approximate start of the turn.
- Cover the ENTIRE recording from start to finish. Do not stop early.
EOF
)

REQ_FILE="$WORK_DIR/request.json"
jq -n --arg uri "$FILE_URI" --arg mime "$MIME" --arg prompt "$PROMPT" '{
  contents: [{parts: [{file_data: {file_uri: $uri, mime_type: $mime}}, {text: $prompt}]}],
  generationConfig: {temperature: 0.1, maxOutputTokens: 65536}
}' > "$REQ_FILE"

SSE_FILE="$WORK_DIR/stream.sse"
RAW_TEXT="$WORK_DIR/model-output.txt"
ATTEMPT=0
CURL_OK=""
while [ "$ATTEMPT" -lt 3 ]; do
  ATTEMPT=$((ATTEMPT + 1))
  # --http1.1 + streaming: keeps bytes flowing so idle-killing middleboxes
  # (VPNs/proxies) don't drop the connection while the model processes audio.
  if curl -sS --http1.1 -N --max-time 1800 \
      -X POST "$API_BASE/v1beta/models/$GEMINI_MODEL:streamGenerateContent?alt=sse&key=$GEMINI_API_KEY" \
      -H "Content-Type: application/json" \
      -d @"$REQ_FILE" > "$SSE_FILE"; then
    CURL_OK="yes"
  else
    log "      attempt $ATTEMPT: transport failure, retrying ..."
    sleep 10
    continue
  fi

  # A non-200 response arrives as a single JSON error object, not SSE lines.
  API_ERR=$(jq -r '.[0].error.message // .error.message // empty' "$SSE_FILE" 2>/dev/null || true)
  if [ -n "$API_ERR" ]; then
    err "Gemini API error: $API_ERR"
  fi

  grep '^data: ' "$SSE_FILE" | sed 's/^data: //' \
    | jq -r 'select(.candidates) | .candidates[0].content.parts[]?.text // empty' \
    > "$RAW_TEXT" || true

  WORDS=$(wc -w < "$RAW_TEXT" | tr -d ' ')
  if [ "$WORDS" -gt 0 ]; then
    break
  fi
  log "      attempt $ATTEMPT: empty transcript, retrying ..."
  sleep 10
done
[ -n "$CURL_OK" ] || err "Gemini streaming call failed after $ATTEMPT attempts (transport)"
WORDS=$(wc -w < "$RAW_TEXT" | tr -d ' ')
[ "$WORDS" -gt 0 ] || err "Gemini returned an empty transcript after $ATTEMPT attempts"

FINISH=$(grep '^data: ' "$SSE_FILE" | sed 's/^data: //' \
  | jq -r 'select(.candidates) | .candidates[0].finishReason // empty' | tail -1)
if [ -n "$FINISH" ] && [ "$FINISH" != "STOP" ]; then
  log "      WARNING: finishReason=$FINISH — the transcript may be truncated"
fi
log "      Words: $WORDS · finishReason: ${FINISH:-unknown}"

# ---------- [4/4] Format output ----------
log "[4/4] Formatting transcript to $OUT_PATH ..."

OUT_STEM=$(basename "${OUT_PATH%.md}")
# The model streams in chunks, so turns can arrive split across lines, and it
# sometimes pads timestamps with stray spaces ("[ 0:03 ]", "[ 0: 34 ]"): glue
# everything back together, normalize the [mm:ss] markers, then split turns.
TURNS_FILE="$WORK_DIR/turns.md"
tr '\n' ' ' < "$RAW_TEXT" \
  | sed -E 's/\[[[:space:]]*([0-9]{1,2})[[:space:]]*:[[:space:]]*([0-9]{2})[[:space:]]*\]/\n[\1:\2]/g' \
  | sed -E 's/^\[([0-9]{1,2}:[0-9]{2})\][[:space:]]*(speaker_[0-9]+)[[:space:]]*:[[:space:]]*/**[\2 — \1]**  /' \
  | sed '/^[[:space:]]*$/d' > "$TURNS_FILE"

SPEAKER_COUNT=$(grep -oE 'speaker_[0-9]+' "$TURNS_FILE" | sort -u | wc -l | tr -d ' ')

{
  echo "# Transcript — $OUT_STEM"
  echo ""
  echo "**Source:** $FILE_PATH"
  echo "**Generated:** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "**Provider:** Google Gemini (model=$GEMINI_MODEL) — fallback engine; diarization approximate, resolve speaker identities from content"
  echo "**Language:** ${ELEVENLABS_LANG:-auto}"
  echo "**Speakers detected:** $SPEAKER_COUNT"
  echo ""
  echo "---"
  echo ""
  echo "## Conversation (speaker-separated)"
  echo ""
  awk '{print; print ""}' "$TURNS_FILE"
  echo "---"
  echo ""
  echo "## Full text"
  echo ""
  sed -E 's/^\*\*\[[^]]+\]\*\*  //' "$TURNS_FILE" | tr '\n' ' '
  echo ""
} > "$OUT_PATH"

cp "$RAW_TEXT" "${OUT_PATH%.md}.raw.txt"

# Best-effort cleanup of the uploaded audio (it auto-expires in ~48h anyway).
curl -sS -X DELETE "$API_BASE/v1beta/$FILE_NAME?key=$GEMINI_API_KEY" >/dev/null 2>&1 || true

log ""
log "Transcript:  $OUT_PATH"
log "Raw output:  ${OUT_PATH%.md}.raw.txt"
log "Speakers:    $SPEAKER_COUNT detected (approximate)"
log ""
echo "$OUT_PATH"
