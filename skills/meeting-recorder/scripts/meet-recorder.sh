#!/bin/bash
# meet-recorder.sh — start/stop a lightweight audio-only meeting recording.
#
# Wraps the self-built MeetingRecorder.app (CoreAudio process tap + mic) and
# muxes its two lossless temp tracks into one small AAC .m4a with ffmpeg, named
# by date+topic and dropped into the recordings directory (default ./recordings
# under the current project; override with MEETING_REC_DIR). The companion
# meeting-processor skill picks it up to transcribe + summarize.
#
# Usage:
#   meet-recorder.sh build                 # compile + sign the recorder (.app)
#   meet-recorder.sh start [topic-slug]    # begin recording (system audio + mic)
#   meet-recorder.sh stop  [topic-slug]    # stop, mux to .m4a, print final path
#   meet-recorder.sh status                # is a recording in progress?
#
# Environment:
#   MEETING_REC_DIR      output directory for .m4a   (default: $PWD/recordings)
#   MEETING_REC_BITRATE  AAC mono bitrate            (default: 64k, ~14 MB/hour)
#
# Requirements: swiftc + codesign (build only), ffmpeg (mux). All present on a
# standard dev Mac. One-time: grant Microphone + Audio Recording when prompted.

set -euo pipefail

# ---------- Paths ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP="$SKILL_DIR/bin/MeetingRecorder.app/Contents/MacOS/MeetingRecorder"
BUILD_SH="$SKILL_DIR/recorder/build.sh"
# Output goes to the current working directory (the project you're in), NOT the
# plugin install location — so recordings land in your project, not the cache.
RECORDINGS_DIR="${MEETING_REC_DIR:-$PWD/recordings}"
# Sibling skill that transcribes the result (resolved relative to this plugin).
TRANSCRIBE_SH="$SKILL_DIR/../meeting-processor/scripts/transcribe-video.sh"
STATE_FILE="${TMPDIR:-/tmp}/yar-meeting-recorder.state"

# ---------- Tunables ----------
AAC_BITRATE="${MEETING_REC_BITRATE:-64k}"   # mono speech; ~14 MB/hour

# ---------- Helpers ----------
err()  { echo "ERROR: $*" >&2; exit 1; }
log()  { echo "$*" >&2; }

sanitize_slug() {
  # lowercase, spaces→dash, keep alnum/dash, collapse repeats, trim
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr ' _' '--' \
    | tr -cd 'a-z0-9-' | sed -E 's/-+/-/g; s/^-//; s/-$//'
}

ensure_built() {
  if [ ! -x "$APP" ]; then
    log "Recorder not built yet — building…"
    command -v swiftc >/dev/null 2>&1 || err "swiftc not found. Install: xcode-select --install"
    bash "$BUILD_SH" >&2 || err "build failed"
  fi
}

# ---------- Commands ----------
cmd_build() {
  command -v swiftc >/dev/null 2>&1 || err "swiftc not found. Install: xcode-select --install"
  bash "$BUILD_SH"
}

cmd_status() {
  if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    if kill -0 "${REC_PID:-0}" 2>/dev/null; then
      log "Recording in progress (since ${REC_START:-?}, topic='${REC_SLUG:-meeting}', pid=$REC_PID)."
      return 0
    fi
    log "Stale state found (process $REC_PID not running). Run 'stop' to finalize or clean up."
    return 0
  fi
  log "Not recording."
}

cmd_start() {
  local slug; slug="$(sanitize_slug "${1:-meeting}")"; [ -n "$slug" ] || slug="meeting"

  if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    if kill -0 "${REC_PID:-0}" 2>/dev/null; then
      err "already recording (pid $REC_PID, topic='${REC_SLUG:-meeting}'). Run 'stop' first."
    fi
  fi

  ensure_built
  command -v ffmpeg >/dev/null 2>&1 || err "ffmpeg not installed. Run: brew install ffmpeg"
  mkdir -p "$RECORDINGS_DIR"

  local work; work="$(mktemp -d -t yar-meet)"
  # Launch detached so it survives this script exiting; logs to the work dir.
  nohup "$APP" --system "$work/system.caf" --mic "$work/mic.caf" \
        >"$work/out.log" 2>"$work/rec.log" &
  local pid=$!
  disown 2>/dev/null || true
  # Keep the Mac awake for the duration of the recording (auto-exits with it).
  nohup caffeinate -dimsu -w "$pid" >/dev/null 2>&1 & disown 2>/dev/null || true

  cat > "$STATE_FILE" <<EOF
REC_PID=$pid
REC_WORK="$work"
REC_SLUG="$slug"
REC_START="$(date +%Y-%m-%dT%H:%M:%S)"
REC_DATE="$(date +%F)"
EOF

  # Give it a moment to fault early (e.g. tap permission denied).
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    log "Recorder exited immediately. Log:"; sed 's/^/  /' "$work/rec.log" >&2 || true
    rm -f "$STATE_FILE"
    err "recorder failed to start (often a permission issue — see reference/recorder-setup.md)"
  fi

  log "Recording started (topic='$slug', pid=$pid)."
  log "On first run, approve the Microphone + Audio Recording prompts."
  log "Stop with:  meet-recorder.sh stop \"$slug\""
}

cmd_stop() {
  [ -f "$STATE_FILE" ] || err "not recording (no state file)."
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  local work="${REC_WORK:-}" pid="${REC_PID:-0}"
  local slug; slug="$(sanitize_slug "${1:-${REC_SLUG:-meeting}}")"; [ -n "$slug" ] || slug="meeting"
  local date="${REC_DATE:-$(date +%F)}"
  if [ -z "$work" ] || [ ! -d "$work" ]; then err "work dir missing ($work). State cleared."; fi

  # Ask the recorder to finalize, then wait for it to close its files.
  if kill -0 "$pid" 2>/dev/null; then
    kill -INT "$pid" 2>/dev/null || true
    local i
    # shellcheck disable=SC2034  # bounded loop counter; its value is intentionally unused
    for i in $(seq 1 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    if kill -0 "$pid" 2>/dev/null; then kill -TERM "$pid" 2>/dev/null || true; sleep 1; fi
  fi

  local sys="$work/system.caf" mic="$work/mic.caf"
  local have_sys=0 have_mic=0
  [ -s "$sys" ] && have_sys=1
  [ -s "$mic" ] && have_mic=1
  [ "$have_sys" = 1 ] || [ "$have_mic" = 1 ] || { rm -rf "$work"; rm -f "$STATE_FILE"; err "no audio captured (check permissions)."; }

  mkdir -p "$RECORDINGS_DIR"
  local out="$RECORDINGS_DIR/${date}-${slug}.m4a"
  # Avoid clobbering: append -2, -3, … if needed.
  local n=2; while [ -e "$out" ]; do out="$RECORDINGS_DIR/${date}-${slug}-${n}.m4a"; n=$((n+1)); done

  log "Mixing → $(basename "$out") (AAC mono $AAC_BITRATE) …"
  if [ "$have_sys" = 1 ] && [ "$have_mic" = 1 ]; then
    # Mix both; resample to keep them aligned; mono out for small size + transcription.
    ffmpeg -y -nostdin -loglevel error \
      -i "$sys" -i "$mic" \
      -filter_complex "[0:a]aresample=async=1:first_pts=0[s];[1:a]aresample=async=1:first_pts=0[m];[s][m]amix=inputs=2:duration=longest:dropout_transition=0:normalize=1" \
      -ac 1 -c:a aac -b:a "$AAC_BITRATE" "$out"
  else
    local src="$sys"; [ "$have_sys" = 1 ] || src="$mic"
    log "  (only $([ "$have_sys" = 1 ] && echo system || echo microphone) audio was captured)"
    ffmpeg -y -nostdin -loglevel error -i "$src" -ac 1 -c:a aac -b:a "$AAC_BITRATE" "$out"
  fi

  rm -rf "$work"
  rm -f "$STATE_FILE"

  local size; size=$(du -h "$out" | cut -f1)
  log ""
  log "Saved: $out  ($size)"
  if [ -f "$TRANSCRIBE_SH" ]; then
    log "Next:  transcribe + process with the meeting-processor skill:"
    log "  \"$TRANSCRIBE_SH\" \"$out\""
  fi
  echo "$out"
}

# ---------- Dispatch ----------
cmd="${1:-}"; shift || true
case "$cmd" in
  build)  cmd_build "$@" ;;
  start)  cmd_start "$@" ;;
  stop)   cmd_stop  "$@" ;;
  status) cmd_status "$@" ;;
  *) err "usage: meet-recorder.sh {build|start [slug]|stop [slug]|status}" ;;
esac
