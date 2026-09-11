# One-time setup — Meeting Recorder

The audio-only meeting recorder is a tiny Swift binary that builds and signs itself inside this plugin — you install no third-party app. This guide is only for the **first run** (build + grant permission) and **troubleshooting**. Day to day, you just say "record this meeting / stop recording".

---

## How it works (in brief)
- **The other participants' audio** is captured with a *CoreAudio process tap* on the system output mix — so it doesn't matter whether you're on AirPods or the Mac speakers.
- **Your own voice** is captured from the microphone.
- The two lossless tracks are mixed into one mono AAC `.m4a` with `ffmpeg` (~14 MB/hour, vs a 0.5–1.2 GB Meet video).
- The file lands in `recordings/` under your current project (override with `MEETING_REC_DIR`), ready for the `meeting-processor` skill to transcribe + summarize.

---

## Step 1 — Build (one-time)
Building needs only Xcode Command Line Tools (`swiftc` + `codesign`). Usually already present; if not:
```bash
xcode-select --install
```
Then:
```bash
"${CLAUDE_PLUGIN_ROOT}/skills/meeting-recorder/scripts/meet-recorder.sh" build
```
Output: `skills/meeting-recorder/bin/MeetingRecorder.app` (machine-local; git-ignored — only the source is committed).
> `start` also builds automatically if it sees no build, so this step is optional.

---

## Step 2 — Permissions (one-time, the important step)
The first time you start a recording, macOS shows two permission prompts for **"Meeting Recorder"**:
1. **Microphone** — for your own voice → **Allow**.
2. **System Audio Recording** ("wants to record this computer's audio") — for the other participants → **Allow**.

If no prompt appears, or the recording comes out empty/silent, enable them manually:
- **System Settings → Privacy & Security**
  - Under **Microphone** → turn on "Meeting Recorder".
  - Under **Screen & System Audio Recording** (the current name on recent macOS) → turn on "Meeting Recorder".
- Then take a short test recording.

> Why a signed `.app`? So these grants attach to a stable identity (`io.yar.meetingrecorder`) and macOS doesn't ask every time.

---

## Step 3 — Health check (20 seconds)
1. Play any YouTube video / test call that produces sound.
2. "record this meeting" → speak for a few seconds → "stop recording".
3. Open `recordings/<date>-<topic>.m4a` and play it:
   - You should hear **both the video/other side and your own voice**.
   - The file should be small (a few MB).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Empty/silent file (Duration N/A) | System Audio Recording not granted | Enable it in System Settings, re-record |
| "only system audio captured" message | Microphone not granted or unavailable | Enable Microphone for the app |
| Only your voice, no other side | System Audio Recording not active | Same as above |
| `swiftc not found` at build | Command Line Tools missing | `xcode-select --install` |
| Re-prompts for permission after a rebuild | The binary changed (normal) | Allow once more |
| Audio choppy/odd | A previous recording wasn't closed cleanly | Make sure nothing is running (`status`), then retry |

---

## Notes
- **Always finish with `stop`** (not a manual kill). A clean stop releases the tap and aggregate device properly; an abrupt close can briefly upset the Mac's audio state.
- **One recording at a time.** `status` tells you whether one is in progress.
- **AirPods mic:** if you speak through AirPods, your voice is recorded at Bluetooth-call quality (~16 kHz) — fine for transcription. The other side always comes through the tap at full quality.
- **Privacy:** the `.m4a` and the `bin/` build are git-ignored; neither goes to the repo.
- **Bitrate (optional):** default mono 64k. To change: `MEETING_REC_BITRATE=96k meet-recorder.sh stop ...`.
