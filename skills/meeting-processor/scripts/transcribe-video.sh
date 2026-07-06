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
#   - HTTPS URL:             https://host/path/recording.mp4
#                            → REMOTE MODE: the URL is handed to ElevenLabs as
#                              source_url and fetched server-side — nothing is
#                              downloaded or uploaded locally (zero bandwidth).
#                              The URL must be fetchable without cookies/headers
#                              (public, presigned, or token-in-query).
#   - Google Drive file ID:  1FgYxLZOgAjqz7VczcoYIOF5Fux6Mk5VH
#   - Google Drive URL:      https://drive.google.com/file/d/.../view
#                            → both are rewritten to the direct-download form and
#                              tried in REMOTE MODE first. That works only while
#                              the file is link-accessible ("anyone with link" —
#                              the caller toggles that on/off, e.g. via a Drive
#                              MCP tool, and should revoke it right after). If
#                              the file is private the script detects the HTML
#                              interstitial and falls back to the old guidance:
#                              download locally, re-run with the local path.
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
  - HTTPS URL:   https://host/recording.mp4   (remote mode — ElevenLabs fetches it, zero local bandwidth)
  - Drive ID:    1FgYxLZOgAjqz7VczcoYIOF5Fux6Mk5VH   (remote mode if link-accessible)
  - Drive URL:   https://drive.google.com/file/d/.../view

  <input>          local file path or URL (mp4/mov/mp3/m4a/wav/webm/…)
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
  # The Gemini engine uploads a local file — it cannot fetch remote URLs.
  if [ -n "${REMOTE_URL:-}" ] || [[ "${INPUT:-}" =~ ^https?:// ]]; then
    err "$1 — and the Gemini fallback cannot fetch remote URLs. Download the file locally and re-run with the local path."
  fi
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
# ffmpeg is only needed for local files (audio extraction) — checked in step [1/3].
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
REMOTE_URL=""   # non-empty → REMOTE MODE: ElevenLabs fetches the URL server-side (source_url)
REMOTE_STEM=""

# What does this URL actually serve? Range-reads the first bytes (nothing is
# downloaded) and prints the content type. text/html on a Drive direct link
# means the file is NOT link-accessible (login or virus-scan interstitial).
probe_content_type() {
  curl -sSL -r 0-63 -o /dev/null -w '%{content_type}' --max-time 30 "$1" 2>/dev/null || echo ""
}

drive_private_guidance() {
  # $1 = Drive file ID
  log ""
  log "Drive file $1 is not link-accessible, so ElevenLabs cannot fetch it."
  log "Two ways forward:"
  log ""
  log "  a) Zero-download (preferred): make the file link-readable, re-run, revoke."
  log "     With the file's owner account, add an 'anyone with link' reader"
  log "     permission (e.g. a Drive MCP link-access tool, or drive.google.com UI),"
  log "     re-run this script with the same input, then remove the permission."
  log ""
  log "  b) Local download (works for files you don't own):"
  log "     open 'https://drive.google.com/uc?export=download&id=$1&confirm=t'"
  log "     then re-run with the downloaded file's local path."
  log ""
  exit 2
}

# Drive URL / bare Drive ID → rewrite to the direct-download endpoint and try
# remote mode. drive.usercontent.google.com serves the raw bytes (no virus-scan
# interstitial) as long as the file is link-accessible.
DRIVE_ID=""
if [[ "$INPUT" =~ ^https?://drive\.google\.com/.*[/=]([a-zA-Z0-9_-]{20,}) ]]; then
  DRIVE_ID="${BASH_REMATCH[1]}"
elif [[ "$INPUT" =~ ^[a-zA-Z0-9_-]{20,}$ ]]; then
  DRIVE_ID="$INPUT"
fi

if [ -n "$DRIVE_ID" ]; then
  log "Detected Google Drive input → file ID: $DRIVE_ID"
  REMOTE_URL="https://drive.usercontent.google.com/download?id=${DRIVE_ID}&export=download&confirm=t"
  REMOTE_STEM="drive-${DRIVE_ID}"
  log "Probing link accessibility ..."
  CT=$(probe_content_type "$REMOTE_URL")
  case "$CT" in
    text/html*|"") drive_private_guidance "$DRIVE_ID" ;;
    *) log "      Direct download serves: $CT → remote mode (server-side fetch, zero local bandwidth)" ;;
  esac
elif [[ "$INPUT" =~ ^https?:// ]]; then
  REMOTE_URL="$INPUT"
  REMOTE_STEM=$(basename "${INPUT%%\?*}")
  REMOTE_STEM="${REMOTE_STEM%.*}"
  [ -n "$REMOTE_STEM" ] || REMOTE_STEM="remote-audio"
  CT=$(probe_content_type "$REMOTE_URL")
  case "$CT" in
    text/html*|"") err "URL does not serve a media file (content-type: ${CT:-unreachable}) — it must be fetchable without cookies/headers: $INPUT" ;;
    *) log "Remote URL serves: $CT → remote mode (server-side fetch, zero local bandwidth)" ;;
  esac
elif [ -f "$INPUT" ]; then
  FILE_PATH="$INPUT"
else
  err "input not recognized as local file, HTTPS URL, Drive ID, or Drive URL: $INPUT"
fi

# ---------- Output path ----------
if [ -z "$OUT_PATH" ]; then
  mkdir -p "$DEFAULT_OUT_DIR"
  if [ -n "$REMOTE_URL" ]; then
    STEM="$REMOTE_STEM"
  else
    BASENAME=$(basename "$FILE_PATH")
    STEM="${BASENAME%.*}"
  fi
  # Sanitize: spaces→dashes, drop non-portable chars
  STEM=$(echo "$STEM" | tr ' ' '-' | tr -cd 'A-Za-z0-9._-')
  OUT_PATH="$DEFAULT_OUT_DIR/${STEM}.md"
fi

OUT_DIR=$(dirname "$OUT_PATH")
mkdir -p "$OUT_DIR"

# ---------- Work dir ----------
WORK_DIR=$(mktemp -d -t transcribe-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

# ---------- [1/3] Prepare audio (local) or hand off the URL (remote) ----------
if [ -n "$REMOTE_URL" ]; then
  log "[1/3] Remote mode — no local audio extraction; ElevenLabs fetches the file server-side."
else
  command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg not installed. Run: brew install ffmpeg"
  log "[1/3] Extracting audio (mono ${AUDIO_BITRATE} mp3, ${AUDIO_RATE}Hz) from $(basename "$FILE_PATH") ..."
  AUDIO_FILE="$WORK_DIR/audio.mp3"
  ffmpeg -y -nostdin -loglevel error \
    -i "$FILE_PATH" \
    -vn -ac 1 -b:a "$AUDIO_BITRATE" -ar "$AUDIO_RATE" \
    "$AUDIO_FILE"

  AUDIO_SIZE=$(stat -f%z "$AUDIO_FILE" 2>/dev/null || stat -c%s "$AUDIO_FILE")
  AUDIO_SIZE_MB=$((AUDIO_SIZE / 1024 / 1024))
  log "      Audio: ${AUDIO_SIZE_MB}MB"
fi

# ---------- [2/3] Call ElevenLabs Scribe API ----------
log "[2/3] Calling ElevenLabs Scribe API (model=$ELEVENLABS_MODEL, lang=${ELEVENLABS_LANG:-auto}, diarize=true) ..."
RESPONSE_FILE="$WORK_DIR/response.json"

# Build curl args. Exactly one of file / source_url goes to the API:
# source_url = remote mode (ElevenLabs downloads the media itself — supports
# hosted audio/video URLs; verified live returning 200), file = local upload.
# --http1.1: long-lived requests to the ElevenLabs edge die with
# "curl: (16) Error in the HTTP2 framing layer" on some networks (observed
# live 2026-07). HTTP/1.1 is immune and costs nothing here.
CURL_ARGS=(
  -sS
  --http1.1
  -X POST
  "$API_BASE/speech-to-text"
  -H "xi-api-key: $ELEVENLABS_API_KEY"
  -F "model_id=$ELEVENLABS_MODEL"
  -F "diarize=true"
  -F "timestamps_granularity=word"
  -F "tag_audio_events=false"
)
if [ -n "$REMOTE_URL" ]; then
  CURL_ARGS+=(-F "source_url=$REMOTE_URL")
else
  CURL_ARGS+=(-F "file=@$AUDIO_FILE")
fi
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

# Baseline: newest stored transcript id BEFORE we post. If the connection dies
# mid-wait (curl 16/28/52 → HTTP 000), the job usually KEEPS RUNNING server-side
# (observed live 2026-07: two "failed" HTTP 000 calls had both completed and
# were retrievable). We then recover it from GET /speech-to-text/transcripts
# instead of re-posting — a blind retry creates (and bills) a duplicate job.
BASELINE_ID=$(curl -sS --http1.1 "$API_BASE/speech-to-text/transcripts" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" 2>/dev/null | jq -r '.transcripts[0].id // empty' || true)

recover_orphaned_job() {
  # $1 = reason. On success fills $RESPONSE_FILE with the completed transcript.
  log "      Connection died mid-wait ($1) — the job may still be running server-side."
  log "      Polling the transcripts list for the orphaned job (up to 5 min) ..."
  local new_id="" code n
  for _ in $(seq 1 20); do
    new_id=$(curl -sS --http1.1 "$API_BASE/speech-to-text/transcripts" \
      -H "xi-api-key: $ELEVENLABS_API_KEY" 2>/dev/null | jq -r '.transcripts[0].id // empty' || true)
    [ -n "$new_id" ] && [ "$new_id" != "$BASELINE_ID" ] && break
    new_id=""
    sleep 15
  done
  [ -n "$new_id" ] || return 1
  log "      Found orphaned job: $new_id — polling until it completes (up to 60 min) ..."
  for _ in $(seq 1 120); do
    code=$(curl -sS --http1.1 -o "$RESPONSE_FILE" -w '%{http_code}' \
      "$API_BASE/speech-to-text/transcripts/$new_id" \
      -H "xi-api-key: $ELEVENLABS_API_KEY" 2>/dev/null || echo 000)
    if [ "$code" = "200" ]; then
      n=$(jq -r '((.words // []) | length) + ((.text // "") | length)' "$RESPONSE_FILE" 2>/dev/null || echo 0)
      if [ "${n:-0}" -gt 0 ]; then
        log "      Recovered completed transcript $new_id."
        return 0
      fi
    fi
    sleep 30
  done
  return 1
}

# Capture HTTP status code separately by writing body to file.
# A transport failure (no connection at all) must not kill the script here —
# it is a fallback/recovery trigger, so map it to status 000.
HTTP_STATUS=$(curl -w "%{http_code}" -o "$RESPONSE_FILE" --connect-timeout 30 --max-time 5400 "${CURL_ARGS[@]}") || HTTP_STATUS="000"

if [ "$HTTP_STATUS" != "200" ]; then
  log "      HTTP $HTTP_STATUS"
  cat "$RESPONSE_FILE" >&2 2>/dev/null || true
  # Transport/access failures:
  #   000 = connection died (or never connected). The job often completed
  #         server-side anyway → FIRST try to recover it (no duplicate billing),
  #         only then consider the fallback engine.
  #   403 = ElevenLabs' edge blocks this exit IP (datacenter/VPN — even
  #         keyless requests get 403) · 429 = quota exhausted · 5xx = down.
  # Config errors (400/401/422) stay fatal: falling back would mask a bug the
  # user should fix (bad key, bad request).
  case "$HTTP_STATUS" in
    000)
      if recover_orphaned_job "HTTP 000"; then
        HTTP_STATUS="200"
      elif gemini_key_available; then
        fallback_to_gemini "ElevenLabs API unreachable (HTTP 000, no orphaned job found)"
      else
        err "ElevenLabs API returned HTTP 000 and no orphaned server-side job was found (no GEMINI_API_KEY for the fallback engine)"
      fi
      ;;
    403|429|5??)
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
  echo "**Source:** ${FILE_PATH:-$REMOTE_URL}"
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
