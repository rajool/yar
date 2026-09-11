---
name: meeting-recorder
description: Record a meeting (Google Meet, Zoom, or any call) as a small audio-only .m4a on macOS using a self-built CoreAudio process-tap recorder — no third-party app. Captures both the remote participants' audio (system output) and your own microphone, regardless of output device (AirPods or speakers), names the file by date+topic, and hands off to the meeting-processor skill for transcription + summary. Use when asked to "record this meeting", "start/stop recording", "record the call", or to capture a conversation for later transcription. macOS 14.4+ only.
---

# meeting-recorder — audio-only meeting recording on macOS

Goal: record a meeting as a small **audio-only** `.m4a` with a self-built Swift tool — no third-party app, no Screen-Recording permission. It captures the **other participants** (from the system output mix) and **your own mic**, mixes them into one mono AAC file (~14 MB/hour vs a 0.5–1.2 GB video), and hands the file to `meeting-processor` to transcribe + summarize.

The tool is `recorder/main.swift` → built into `bin/MeetingRecorder.app` (a CoreAudio *process tap* for system audio + AVAudioEngine for the mic). The wrapper `scripts/meet-recorder.sh` drives it and muxes the two tracks with ffmpeg. **Device-independent** — works the same on AirPods or the Mac speakers, because it taps the output mix, not a specific device.

**This skill is invoke-only.** It records only when you ask it to start, and stops only when you ask it to stop.

## 1) Pre-flight
- macOS 14.4+ (the process-tap API). This skill runs a local tool; it needs no project context.
- Dependencies: `swiftc` + `codesign` (build only — Xcode Command Line Tools), `ffmpeg` (mux), `caffeinate` (built in). On a standard dev Mac these are present.
- If `bin/MeetingRecorder.app` is missing, `start` builds it automatically (or build manually — see below).
- **One-time permission:** the first recording triggers macOS prompts for **Microphone** and **Audio Recording** → Allow both. Details + troubleshooting: [`reference/recorder-setup.md`](reference/recorder-setup.md).

## 2) Start recording
When the user says "record this meeting" (optionally with a topic/participants for the filename):
1. Make a short English slug from the topic (e.g. "call with Sara and the design team" → `sara-design-team`). If no topic is given, use the calendar event title or `meeting`.
2. Run:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/skills/meeting-recorder/scripts/meet-recorder.sh" start "<slug>"
   ```
3. Confirm recording started, and **once** remind the user it's good practice to tell participants they're being recorded (consent/transparency — and the law in many places).

## 3) Stop + hand off
When the user says "stop recording":
1. Run:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/skills/meeting-recorder/scripts/meet-recorder.sh" stop "<slug>"
   ```
   stdout: the `.m4a` path — by default `recordings/<YYYY-MM-DD>-<slug>.m4a` under the current project (override the directory with `MEETING_REC_DIR`).
2. Offer the handoff: "Want me to transcribe + process this now?" If yes, invoke the **meeting-processor** skill on the file (it transcribes with ElevenLabs Scribe v2, then summarizes + extracts action items). The recorder only produces the `.m4a`; transcription/analysis is the sibling skill's job. By default the processor deletes this `.m4a` (moves it to the Trash, recoverable) once the transcript + summary are saved — set `MEETING_DELETE_SOURCE=never` to keep it.

## Build (one-time / after editing the source)
```bash
"${CLAUDE_PLUGIN_ROOT}/skills/meeting-recorder/scripts/meet-recorder.sh" build
```
Compiles `recorder/main.swift`, embeds Info.plist, ad-hoc-signs → `bin/MeetingRecorder.app`. The `bin/` build is git-ignored (machine-local); only the source is committed. The build is signed with a stable identity (`io.yar.meetingrecorder`) so the TCC permission grants stick across projects and don't re-prompt every run.

## Special behaviors
- **status:** `meet-recorder.sh status` → whether a recording is in progress (pid / topic / start time).
- **AirPods and speakers:** both work with no extra setup (the tap captures the output mix, not a specific device).
- **Mic unavailable:** recording continues with system audio only and the wrapper warns "only system audio captured" — tell the user (usually means the Microphone permission wasn't granted).
- **Long silence:** a tap may not advance during total silence; in a real meeting with continuous audio this is a non-issue. ffmpeg muxes the two tracks with `amix duration=longest` to keep them aligned.
- **One recording at a time:** `start` errors while a recording is active; `stop` first.
- **Never fail silently:** if `start` dies immediately, the wrapper prints the recorder log (usually a permission issue — point to `reference/recorder-setup.md`).
- **Output location:** default `./recordings/` in the current project. Override with `MEETING_REC_DIR=/path`. Bitrate override: `MEETING_REC_BITRATE=96k`.

## Self-check before handoff
- [ ] File created at `recordings/<YYYY-MM-DD>-<slug>.m4a` (or `MEETING_REC_DIR`)?
- [ ] Both your voice and the other participants are in the file? (If "only system" warned, tell the user — likely the mic permission.)
- [ ] Handoff to the `meeting-processor` skill offered?
- [ ] Recording-transparency reminder given (first time)?

## Dependencies
- **Tool:** `recorder/` (main.swift + Info.plist + build.sh) → `bin/MeetingRecorder.app`; wrapper `scripts/meet-recorder.sh`.
- **System:** swiftc + codesign (build), ffmpeg (mux), caffeinate (keeps the Mac awake during the meeting).
- **Sibling skill:** `meeting-processor` (+ `transcribe-video.sh`, ElevenLabs Scribe v2) — consumes the output.
- **Setup / permissions / troubleshooting:** [`reference/recorder-setup.md`](reference/recorder-setup.md).
