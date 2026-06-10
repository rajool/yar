---
name: meeting-processor
description: Turn a meeting recording or transcript into a clean Markdown summary — narrative, decisions, and action items (owner, deadline, priority) — then optionally route the outputs into the project's own tools: a task per action item, calendar events, formal decisions to a decisions record, per-person/project notes, status flags, and a follow-up email. Transcribes audio/video locally with ElevenLabs Scribe v2 (speaker diarization, any language) and keeps a verbatim transcript in the spoken language. Tracks a per-meeting processing ledger in the summary frontmatter — every stage from transcript through follow-up email — so "review the meetings" shows what is done vs. still pending per meeting. Deletes the source recording after the transcript and summary are saved (MEETING_DELETE_SOURCE). Use when asked to "process this meeting", "summarize this recording", "extract action items", "review the meetings", or after the meeting-recorder skill produces a file. Needs ELEVENLABS_API_KEY only when transcribing.
---

# meeting-processor — transcribe + summarize + extract action items + route

Goal: take a meeting **recording** (audio/video) or an **existing transcript** and produce a clean, structured Markdown summary — narrative summary, decisions, action items with owners/deadlines/priority, and open questions — then **route** those outputs into the tools the project already uses (task system, calendar, decisions record, status docs). The transcription engine is **ElevenLabs Scribe v2** (high-accuracy batch STT with speaker diarization, any language).

**This skill is invoke-only** and project-agnostic — it makes no assumptions about your repo layout. It writes **one summary file** (plus the verbatim transcript) and never scatters content into opinionated folders. Routing is **opt-in and caller-driven**: the skill extracts a clean structure and *offers* to route it into whatever you already have; it asks before any outbound write and invents no tools or destinations of its own. The caller (a project's CLAUDE.md, another skill, or the user) supplies the task system, people map, decisions record, and status docs.

## The processing ledger — what's done vs. pending, per meeting
A meeting is rarely "done" in one pass: transcribing, summarizing, filing tasks, updating docs, and sending a follow-up often land across several sessions. So **every meeting carries a ledger** of its processing stages, stored in the summary's frontmatter under `processing:`. Initialize it when you write the summary (step 3) and **keep it current** as each later step finishes or is declined (steps 4–5). It is the single source of truth for "where is this meeting?" — when asked, read the ledger; never report status from memory.

**Stages** — every meeting has all of them; mark each one:

| Stage | Means | Set in |
|---|---|---|
| `transcript` | verbatim transcript saved | step A |
| `summary` | structured summary written | steps 2–3 |
| `tasks` | action items filed in the task system | step 4 |
| `calendar` | dated commitments added to a calendar | step 4 |
| `decisions` | formal decisions filed in the decisions record | step 4 |
| `context_docs` | status / roadmap / per-person / per-project notes updated | step 4 |
| `followup_email` | follow-up email to attendees sent | step 4 |
| `source_cleanup` | source recording deleted | step 5 |

**State of each stage** — use exactly one:
- `done` — completed. Optionally annotate: `done — 3 tasks in Linear`, `done (2026-06-04)`.
- `pending` — applies and is **still owed** (a real to-do).
- `skipped` — offered, user declined.
- `n/a` — doesn't apply here (no dated commitments → `calendar: n/a`; no formal decisions → `decisions: n/a`; a transcript-only input → `transcript: n/a`, `source_cleanup: n/a`).

Because routing is opt-in (step 4), `pending` vs `skipped` carries meaning: a stage **not yet decided** is `pending`; one the user **declined** is `skipped`. Never claim a stage is `done` unless you actually did it, and don't quietly downgrade a `pending` to `n/a` to make the row look finished.

### Review mode — status across all meetings
When asked to **review the meetings** — "what's left?", "which meetings still need follow-up?", "where are we on the meetings?" — do **not** reprocess anything. Instead:
1. Find the project's meeting summaries (default `meetings/*.md`, or wherever this project keeps them).
2. Read each one's `processing:` frontmatter. If a summary predates the ledger (no `processing:` block), infer `transcript`/`summary` from the files on disk and treat every downstream stage as `pending` (unknown — never assume `done`).
3. Print a **status matrix**, one row per meeting, using `✓` done · `•` pending · `–` n/a or skipped:

   | Meeting | tx | sum | task | cal | dec | ctx | mail | clean |
   |---|---|---|---|---|---|---|---|---|
   | 2026-06-04 team-sync | ✓ | ✓ | • | – | ✓ | • | • | ✓ |
   | 2026-06-02 partner-review | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ |

4. Below the matrix, list the **outstanding items** grouped by meeting — just the `pending` stages, in plain language (e.g. "team-sync: 3 tasks not filed · context docs not updated · follow-up email not sent") — then **offer to clear them now** (step 4's routing applies). Where it's cheap to verify against reality, do: if a stage reads `done` but the destination is reachable (the task system, the calendar), sanity-check the items are actually there before reporting it green.

## 0) Determine the input
Detect which you have:
1. **Audio/video file** (mp4/mov/m4a/mp3/wav/webm/…) → transcribe first (step A).
2. **Google Drive ID or URL** → fetch first (step B).
3. **Existing transcript** (a `.md`/`.txt`, or pasted text) → skip to step 1.

### A) Local audio/video → transcribe with ElevenLabs Scribe v2
```bash
"${CLAUDE_PLUGIN_ROOT}/skills/meeting-processor/scripts/transcribe-video.sh" "<path-to-file>" [output_path] [num_speakers]
```
The script: extracts audio with ffmpeg (mono mp3) → sends one call to ElevenLabs `scribe_v2` with diarization and word timestamps → writes `transcripts/<stem>.md` (with "Conversation (speaker-separated)" and "Full text" sections) + `<stem>.raw.json`. No chunking (Scribe handles up to ~10 hours per call). ~2 min for a 66-min recording; ~$0.13–0.22 per audio hour.

Knobs (environment variables — all optional):
- `ELEVENLABS_API_KEY` — **required for transcription.** Resolved from env → `$PWD/.claude/settings.local.json` (`.env.ELEVENLABS_API_KEY`) → `$PWD/.env`. Get one at [elevenlabs.io](https://elevenlabs.io).
- `ELEVENLABS_LANG` — ISO-639-3 hint (e.g. `eng`, `fas`, `spa`). Default: empty → Scribe auto-detects. Set it when you know the language and want maximum accuracy.
- `ELEVENLABS_KEYTERMS` — comma-separated proper nouns to bias toward (e.g. `"Acme,Jane Doe,Project Atlas"`) so domain names don't get garbled. Default: none.
- 3rd arg `num_speakers` — pass the expected count (e.g. `5`) for sharper diarization; otherwise auto-detect.

Pre-reqs: `ffmpeg`, `curl`, `jq` (`brew install ffmpeg jq`).

After transcription:
- The transcript is usually high quality, but **speaker_0..speaker_N identities need resolving** — infer from context (who addresses whom, who owns which topic). Mark anything ambiguous as `unknown` and ask the user rather than guessing.
- Archive the transcript + `raw.json` wherever the project keeps them (don't leave them in a temp/inbox spot).

### B) Google Drive ID or URL
Don't pull large video through an MCP as base64 — it destroys context. Instead open the direct-download URL in the browser:
```bash
open "https://drive.google.com/uc?export=download&id=<DRIVE_ID>&confirm=t"
```
Tell the user to confirm the download, then process the file from `~/Downloads/` via step A.

### Language — two artifacts, two rules
- **Verbatim transcript** = the faithful record. Always keep it in the **language actually spoken**; never translate or clean it up. It is a first-class deliverable, separate from the summary.
- **Summary** = written in the **same language as the meeting** (or the user's stated working language). Keep verbatim quotes in their original language.
- Translating the summary/minutes into a different target language is a **caller concern**, not this skill's job — do it only if the caller explicitly asks. This skill stays language-neutral.

## 1) Identify the meeting type
A light classification shapes what you look for:

| Signal | Type |
|---|---|
| 2 people, one clearly the manager/report | 1-on-1 |
| Several team members + a lead | team sync / leadership |
| External company name, "proposal", "review" | opportunity / partner review |
| "negotiation", "term sheet", "valuation", "pricing" | negotiation |
| "candidate", "interview" | interview |
| "customer", "support", a customer name | customer call |
| board, directors, "resolution", "approve", governance | board / governance |
| otherwise | general internal meeting |

If unclear, **ask**.

## 2) Structured extraction
From the transcript, extract the following. For each section, explicitly write "none" if nothing applies.

**a) Metadata** — date (of the meeting, not of processing), approx duration, attendees (+ roles if known), meeting type.

**b) Summary** (5–10 sentences) — main topic, overall outcome, tone.

**c) Decisions made** — for each: topic · the decision · explicit or implicit agreement? · owner · **formal?** (routine working decision vs a formal/governance decision — a board/leadership resolution, approval, policy, or anything that belongs in an official record).
> Flag **implicit** decisions: "I think it was decided that X, though no one said it outright — confirm?"
> Mark **formal** decisions so step 4 can offer to file them in the project's decisions record.

**d) Action items** (the most important part) — for each:
```
- What:     {verb-first description}
- Owner:    {person}
- Deadline: {YYYY-MM-DD if stated, else "unspecified"}
- Priority: high | medium | low
- Source:   {which moment in the meeting}
```
Distinguish **"should do"** (weak — leave out unless it firms up) from **"will do"** (an explicit commitment → an action item).

**e) Deadlines / commitments** — dated commitments worth a calendar entry: `{commitment}: by {date} — {owner}`.

**f) Open questions** — raised but not resolved; things to follow up later.

## 3) Write the summary
Write **one** Markdown file (default `meetings/<YYYY-MM-DD>-<topic-slug>.md` under the current project — or wherever the project keeps meeting notes). The verbatim transcript from step A is the second artifact; keep both together.
```markdown
---
date: YYYY-MM-DD
type: {meeting_type}
attendees: [{names}]
duration_min: {N or unknown}
source: {transcript_or_recording_path}
processing:
  transcript: done            # or n/a for transcript-only input
  summary: done
  tasks: pending              # done | pending | skipped | n/a
  calendar: pending
  decisions: pending
  context_docs: pending
  followup_email: pending
  source_cleanup: pending     # or n/a for transcript-only input
---

# {topic}

## Summary
{narrative summary}

## Decisions
- {decision} — owner: {name} ({explicit|implicit}{, formal if applicable})

## Action items
- [ ] {owner} — {action} (due: {date}, priority: {p})

## Open questions
- {open question}
```

Seed the `processing:` ledger as you write the file: `transcript` and `summary` → `done` (or `transcript: n/a` for transcript-only input); every routing stage → `pending`, except set a stage to `n/a` right away when the meeting plainly has nothing for it (no dated commitments → `calendar: n/a`; no formal decisions → `decisions: n/a`).

## 4) Route the outputs (opt-in)
First present a short recap: the summary file path, the decisions list, the action items grouped by owner, and the dated commitments.

Then **offer** — never assume — to route each output into the tools this project actually has. Do nothing outbound until the user confirms; if they decline, the summary file is the deliverable. Probe what exists (a connected MCP, a sibling skill, a conventional file) and only offer routes that are real here.

- **Action items → the project's task system.** *(ledger: `tasks`)* If the project has one — a task/issue skill, a PM/issue MCP (Linear, Jira, GitHub Issues, Asana…), or a conventional tasks file/board — offer to create **one task per action item**, preserving owner, deadline, priority, and a link back to the meeting. Map each owner to the project's people (ask when a name is ambiguous rather than guessing). **For any action item you (the assistant) can complete yourself, offer to just do it now** instead of only filing a task.
- **Dated commitments → a calendar.** *(ledger: `calendar`)* If a calendar MCP (e.g. Google Calendar) is connected, offer to create events for the dated commitments from section (e).
- **Formal/governance decisions → a decisions record.** *(ledger: `decisions`)* If some decisions were flagged **formal** and the project keeps an official record — a decision log, ADR folder, minutes/registers, or a governance doc — offer to append them there in that record's format.
- **Status / roadmap / planning docs → flag for update.** *(ledger: `context_docs`)* If the meeting changed the project's status, plans, or priorities and the project maintains living status/roadmap/planning docs, name which ones likely need updating and offer to update them.
- **Per-person / per-project notes.** *(ledger: `context_docs`)* If the project keeps per-person or per-project notes, offer to append the relevant items. (This stage and the one above share the `context_docs` slot — mark it `done` once the notes/docs are updated, `n/a` if the project keeps none.)
- **Follow-up email → attendees.** *(ledger: `followup_email`)* If a recap to participants is warranted and a mail MCP is connected (e.g. Gmail) — or the user just wants a draft — offer to compose a follow-up: a short recap, the decisions, and each owner's action items with deadlines. **Draft first, show the user, and send only on explicit confirmation** (email is outbound and hard to unsend). No mail tool and no request → `followup_email: n/a`.
  - **Mind the date — relative time must match reality.** The meeting has a real date (the summary frontmatter), which is often **not** the day you're drafting. Before writing, compare the meeting date to **today's date** and phrase the reference accordingly: a meeting that was yesterday is "yesterday" (not "today's meeting"), one from earlier in the week is "on Monday" / "the other day". Never greet with "thanks for today's good meeting" for a meeting that happened on a previous day. Applies to any prose that says *when* the meeting happened (greeting, recap line), not just the frontmatter.
  - **Keep it short — the reader was there.** A recap to attendees is a *reminder*, not a write-up. They sat through the meeting, so do **not** re-explain the context, restate the stats, or justify the reasoning behind each decision — they already heard it. Give the decisions, each owner's actions with deadlines, and any **new** nuance or instruction, then stop. Cut "because X, so Y" justification sentences and restated background; if a line only repeats what everyone in the room already knows, delete it. A tight 4-point recap beats a thorough one.

Wait for confirmation before any outbound write (tasks, calendar events, edits to records, emails). Route only confirmed items — don't promote a tentative "should do" into a filed task, or an implicit decision into the official record, without the user's nod.

**Keep the ledger honest.** After each route — done, or declined — update the matching `processing:` stage in the summary frontmatter: `done` when you actually completed it (annotate with the destination, e.g. `done — 4 tasks in Linear`), `skipped` when the user declined, `n/a` when it never applied. This is what makes a later "review the meetings" (review mode above) accurate.

## 5) Delete the source recording
The transcript and summary are the durable record; the heavy source media (and a potentially sensitive recording) doesn't need to linger once they exist. As the **last** step, after the transcript **and** summary are written to disk (step 3) and any routing the user asked for is done (step 4), remove the original audio/video file you were handed:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/meeting-processor/scripts/cleanup-source.sh" "<path-to-source-media>"
```

The helper moves the file to the macOS Trash (recoverable) and **refuses to delete anything that isn't a media file**, so it can never remove a transcript, `raw.json`, or summary.

Hard rules:
- **Source media only.** Delete just the input audio/video. **Never** delete the transcript, `raw.json`, or the summary — those are the deliverables.
- **Only after the transcript and summary are safely on disk.** If transcription or summarizing failed, keep the source. Never delete the only copy of the content.
- **Existing-transcript input → nothing to delete.** When the input was a transcript/pasted text (no media), skip this step.
- A Google-Drive download (step B) is safe to delete locally — the cloud copy remains.

Behaviour is set by **`MEETING_DELETE_SOURCE`** (default `always`):
- `always` *(default)* — delete the source automatically once processing succeeds.
- `ask` — show the user the file (and size) and confirm before deleting.
- `never` — keep everything; skip this step.

Permanent instead of Trash: pass `--hard` (or set `MEETING_DELETE_HARD=1`) — gone immediately, not recoverable. After deleting, tell the user what was removed and where it went (Trash vs permanent), then set `source_cleanup: done` in the ledger (`n/a` for transcript-only input, `skipped` when `MEETING_DELETE_SOURCE=never` left the file in place).

## Self-check before delivery
- [ ] Quantitative attribution verified — every number/stat tied to the right speaker; ambiguous → "unspecified", not a guess.
- [ ] Conditional framing preserved — don't turn "if X then Y" into a firm decision, or a suggestion into an instruction.
- [ ] Ownership correct — who said / agreed to / asked for what (don't conflate reported-vs-asked).
- [ ] Ambiguous speaker? Show the user one representative quote per unknown speaker to identify, rather than guessing from an attendee list.
- [ ] No invented entities — never turn an ambiguous or garbled transcript token into a named person, vendor, advisor, or tool. STT routinely mishears ordinary words as proper names; if an entity can't be independently confirmed (the project's people map, prior docs, or the user), flag it as uncertain or drop it — never assert it as fact in a summary, decision, task, or email.
- [ ] Summary written in the meeting's language; verbatim transcript kept in the spoken language; neither silently translated.
- [ ] Routing is opt-in and confirmed — only formal decisions go to the official record; only firm commitments become tasks/events.
- [ ] Processing ledger written and current — every stage marked `done` / `pending` / `skipped` / `n/a`; nothing reads `done` that wasn't actually done, and no `pending` was quietly hidden as `n/a`.
- [ ] Source recording handled per `MEETING_DELETE_SOURCE` — removed **only** after the transcript and summary were saved, and only the media file (transcript, `raw.json`, and summary kept).

## Dependencies
- **Script:** `scripts/transcribe-video.sh` (ElevenLabs Scribe v2 — used only for audio/video input).
- **Script:** `scripts/cleanup-source.sh` (moves a processed source recording to the Trash; `--hard` to delete permanently).
- **System (for transcription):** ffmpeg, curl, jq.
- **Sibling skill:** `meeting-recorder` produces the `.m4a` this skill consumes.
- **Routing targets are the caller's:** the task system, people map, calendar, decisions record, status docs, and a mail tool (for the follow-up email) are supplied by the project — this skill provides the extracted structure, tracks each in the per-meeting `processing:` ledger, and offers to fill them.
