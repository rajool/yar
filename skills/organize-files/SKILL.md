---
name: organize-files
description: Project-agnostic engine for organizing, sorting, deduplicating, and renaming files in any folder or repo, and for keeping each destination folder's README in sync. Use whenever you sort or clean up files, classify new uploads or downloads, notice possible duplicates, or add/move/create a file into a folder. Enforces meaningful naming (`YYYY-MM-DD-descriptive-name.ext`), detects exact and near-duplicate files (name, checksum, size, text, image resolution), picks the best version (preferring signed, then final, newer, higher-quality, more-complete, else asks), deletes safely (trash, never `rm`; confirm or ledger), and updates the destination folder's README with a one-line content summary on every add. Reads file contents via the `yar:file-inspector` agent; the caller supplies any project-specific destination map, storage split, or off-limits folders. Triggers include "organize", "sort files", "clean up", "tidy", "where does this file go", "duplicate", or "organize inbox".
---

# organize-files — a project-agnostic file-organizing engine

This is the reusable **engine** for tidying files in any project: naming, duplicate detection, best-version selection, safe deletion, a standard workflow, and README upkeep. It is deliberately **project-agnostic** — it knows *how* to organize, not *where things go in your project*.

Four core jobs:

1. **Meaningful naming** of files before they move
2. **Detecting duplicate or near-duplicate** files
3. **Choosing the best version** to keep
4. **Updating the destination folder's README** after every add (§9)

> **The caller supplies the project layer.** A wrapping skill (or you, inline) provides: the **drop point(s)** to scan, the **destination map** (which folder a kind of file belongs in), any **storage split** (e.g. a repo + cloud mount where text and binaries live in different places), and any **off-limits folders** the inspector must not read. This skill applies the mechanics on top of that layer. With no caller layer, sensible defaults apply: scan the named folder, keep files in place, treat `.git`/hidden as off-limits.

---

## 1. Naming convention (mandatory)

Every file you move or rename **must** get a meaningful, English name.

### Standard format

```
YYYY-MM-DD-short-descriptive-name.ext
```

### Rules

- **Date first.** If the file has a date (from PDF content or metadata), use it. Otherwise use the file's creation date.
- **Short description**, dash-separated: `lab-cbc-results`, `car-insurance-renewal`, `dr-ahmadi-cardiology-visit`.
- **Always English** — even if the file's content is in another language (name it `tax-return-1404.pdf`, never in the document's source-language script).
- **lowercase**, **dash-separated**. No spaces, no underscores, no CamelCase.
- **Correct extension**: `.pdf`, `.jpg`, `.png`, `.docx`, …
- If a second version must be kept alongside the first (rare), suffix `-v2` or `-revised`: `2026-03-10-contract-signed-v2.pdf`.

### Examples

| Original (bad) | Organized (good) |
|---|---|
| `IMG_20260301_142533.jpg` | `2026-03-01-passport-photo.jpg` |
| `Scan001.pdf` | `2026-04-15-lab-cbc-results.pdf` |
| `azmayesh-khoon.pdf` | `2026-04-15-lab-blood-results.pdf` |
| `Final_Final_v3 (1).docx` | `2026-05-10-rental-agreement-final.docx` |
| `WhatsApp Image 2026-02-14.jpg` | `2026-02-14-family-trip-photo.jpg` |

---

## 2. Duplicate detection

Before moving any file, **check** whether another copy already exists in the search scope.

### Detection methods (in priority order)

#### a. Similar name

```bash
# Search the destination and related folders; exclude .git and any caller off-limits paths
find . -type f -iname "*keyword*" -not -path "./.git/*"
```

A near-identical name → inspect the content (next steps).

#### b. Content checksum

```bash
# Compare sha256 for an exact match
shasum -a 256 file1 file2
```

Identical checksum → exact duplicate. Keep one.

#### c. Size and file type

Two files with similar names but different sizes are probably different versions.

#### d. Text content (PDF / Word)

For two similar-named documents, extract and compare text (use a PDF/text-extraction tool).

#### e. Images

Compare resolution and file size:

```bash
sips -g pixelWidth -g pixelHeight image.jpg
```

---

## 3. Choosing the best version (preference rules)

When several similar versions exist, apply these rules **in order**:

### Rule 1 — a signed copy wins

If one version is digitally signed (signed PDF/contract), keep it.

**Detect:** filename contains `signed`, `signed-final`, `executed` (or the equivalent in the document's language); when in doubt, read the PDF and look for a signature block.

### Rule 2 — the final version wins

If one is marked `final`, `revised`, `approved` (or the equivalent in the document's language) in name/content, keep it.

### Rule 3 — the newer date wins

If the rules above don't apply, compare:
1. Date in the filename (if `YYYY-MM-DD`)
2. File creation/modification date (`stat -f "%Sm" file`)
3. Date in the content (e.g. an invoice/version date)

### Rule 4 — higher quality for images

- Higher resolution wins.
- Larger file size (same format) usually means better quality.
- An uncompressed format (PNG/HEIC) usually beats a low-quality compressed one (JPG).

### Rule 5 — more complete content wins

- More pages = more content = probably more up to date.
- A larger PDF with the same page count usually means a better scan or more content.

### Rule 6 — on a tie, ask the user

If none of the above resolves it, **tell the user** and present the options.

---

## 4. Deletion policy (trash + ledger)

- **Normal work:** get the user's **confirmation** before deleting (see §6).
- **Batch jobs:** exact duplicates and obvious junk may go to **trash automatically** and be recorded in a `ledger.md` — without asking file by file:
  - Command: `trash "<file>"` (to the OS/cloud trash, **recoverable ~30 days**). **Never `rm`.**
  - Each deletion in the ledger: source path + reason + the sha256 of the kept winner.
- Ambiguous cases (near-dupes, close quality) → ask the user, or move to a needs-review area.

> In a large batch job, the **caller's playbook** owns ordering, batching, and checkpointing/resumability. This skill is the **per-file engine** it calls; it doesn't drive the batch.

---

## 5. Standard workflow

When organizing files, run these steps **in order**:

### Step 1 — Inventory

List the caller's drop point(s); filter out system/README files:

```bash
ls -A <drop-point>/ 2>/dev/null | grep -vE '^(README\.md|\.DS_Store)$'
```

Use filenames only for **initial planning**, never for the final decision.

### Step 2 — Deep inspection (parallel)

For **each file**, dispatch a `yar:file-inspector` agent. Call them **all in one message, in parallel**:

```
Agent({
  description: "Inspect file X",
  subagent_type: "yar:file-inspector",
  prompt: "Inspect <drop-point>/fileX.pdf deeply. Use destination convention <caller's map>, and do NOT read <caller's off-limits folders>. Return a structured report including subject, dates, signatures, version markers, and a suggested name/destination."
})
```

If several files look related (similar name or same type), give the agent that context in the same call:

```
prompt: "Inspect <drop>/Scan001.pdf deeply. Compare with candidate duplicates:
  - <drop>/IMG_4523.pdf
  - <dest>/2026-03-10-lab-cbc-results.pdf
Return a structured report and a verdict on which is the best version."
```

⚠️ **Never** read full file contents in the main context yourself unless the file is tiny (e.g. a short txt). Always use this subagent.

#### Google Workspace files (Docs / Sheets / Slides / Forms)

For Google-native files (`.gdoc`, `.gsheet`, `.gslides`, `.gform`, or shortcut/link files whose mimeType is `application/vnd.google-apps.*`):

- **Never** decide from the name or link alone — the content isn't on local disk.
- **Always** open and read it via your Google Drive MCP:
  - `get_file_metadata` for type and mimeType
  - `read_file_content` / `download_file_content` for the full text (Docs → text, Sheets → CSV/values, Slides → text)
- Only then decide destination, name, and duplication.
- Multiple Google files → open each **in parallel** (several tool calls in one message).

### Step 3 — Duplicate search

In parallel with inspection, search the destination and related folders for same-name or same-type files (see §2). Respect the caller's storage split — search where that kind of file actually lives.

### Step 4 — Resolution

With the structured reports in hand:

- Exact duplicate → pick the winner by §3, mark the rest for deletion.
- A new version that beats the old one → mark the old one.
- Unsure → ask the user.

### Step 5 — Rename + Move

```bash
mv "<drop-point>/Scan001.pdf" "<destination>/2026-04-15-lab-cbc-results.pdf"
```

Take the name from the inspector's `suggested_name`. **Preserve metadata** — use `mv`, not `cp + rm`.

**Cross-boundary moves (cloud upload — e.g. Google Drive / S3 via an MCP or CLI).** When the destination isn't a local path you can `mv` to, the upload only *copies* the file; the original stays at the source. A move isn't finished until that source copy is gone — leaving it behind creates a duplicate and breaks the one-file-one-home rule (the exact thing this skill exists to prevent). So treat it as a two-step move:

1. **Upload** the file to the destination.
2. **Verify it landed** — the upload returned a file id, or the file now lists at the destination with the right size. Never skip this.
3. **Propose deleting the source**, then get the user's confirmation (the normal-work rule, §4) before removing it. A batch playbook may pre-authorize this.
4. On confirmation, `trash "<source>"` (never `rm`) and record it in the ledger.

**Never delete the source before the destination copy is verified.**

### Step 5.5 — Update the destination README (mandatory)

After moving **any** file into a folder, update that folder's README — see [§9](#9-readme-maintenance-rule).

### Step 6 — Report

Give the user a summary:
- What moved and where
- Which files were duplicates and the recommendation
- What needs a user decision (delete an old file, resolve ambiguity, …)
- Any important flags (e.g. an unusual value in a document)

---

## 6. ⚠️ Warnings

- **Never** delete a file without the user's confirmation. Only propose.
- **Never** move a file out of its folder if you're unsure where it goes — leave it in the source and ask.
- For **sensitive** files (medical, financial, identity), confirm the type and destination with the user **before** moving.
- **Preserve metadata** (creation date, photo EXIF) on the move. `mv` does this; `cp + rm` may not.
- After a **cloud upload** (a copy, not an `mv`), don't leave the original at the source. Verify the upload landed, then propose deleting the source (§4, Step 5). An un-deleted source is a silent duplicate.
- Respect the caller's **off-limits** folders — don't read or restructure them.

---

## 7. Useful tools

| Task | Tool |
|---|---|
| Extract text from a PDF | a PDF text-extraction skill/tool |
| Photo metadata | `sips -g all image.jpg` or `mdls image.jpg` |
| Creation/modification date | `stat -f "%Sm %SB" file` |
| Checksum | `shasum -a 256 file` |
| Find files | `find . -type f -iname "*pattern*"` |
| Text file content | the `Read` tool |
| Google Docs/Sheets/Slides content | a Google Drive MCP (`read_file_content` / `download_file_content`) |
| Deep, full-content single-file read | the **`yar:file-inspector`** agent |

---

## 8. Full example

**Scenario:** two PDFs in the drop point:
- `Scan001.pdf` (created 2026-04-10)
- `IMG_4523.pdf` (created 2026-04-15)

**Assistant actions:**

1. Inspects both with `yar:file-inspector` (in parallel).
2. Finds both are the same CBC lab result — one a draft, one final.
3. Determines the second (newer + "final" in content + signed) is the winner.
4. Moves the winner to its destination folder as `2026-04-15-lab-cbc-results.pdf`.
5. Writes a summary note `2026-04-15-summary.md` (if the project keeps text notes).
6. Updates that folder's README — a new row with the filename + a one-line content summary.
7. Reports to the user:
   > Found two copies of the CBC lab. Kept the final (signed, dated 2026-04-15). The draft `Scan001.pdf` is a duplicate — OK to delete it?

---

## 9. README maintenance rule

**Golden rule:** every time a file is added to a folder (via `mv`, a new file, or a download), that folder's README must be updated. Goal: *anyone reading a folder's README understands what's inside and what each file contains — without opening the files.*

> **Linking under a storage split:** if a file lives in a **different store** than its folder's README (e.g. a repo + a cloud mount, where the README is in the repo and the binary is in the mount), the caller defines how links resolve. With no split, link by relative filename (`[x.pdf](x.pdf)`).

### When it fires

- ✅ Moving a file from a drop point into a destination folder
- ✅ Creating a new file (e.g. a `summary.md` beside a PDF)
- ✅ Downloading a file directly into a folder
- ✅ Renaming an existing file
- ❌ Caller off-limits folders (don't touch)
- ❌ Temp, lock, or hidden files (`.DS_Store`, `~$*.docx`, …)

### Workflow

#### a. Does a README exist?

```bash
ls "<destination-folder>/README.md" 2>/dev/null
```

#### b. If not → create it

```markdown
# <Folder Name>

> <one line on what this folder holds — infer from the folder name and file contents>

## Files

| File | Description |
|---|---|
| [<filename>](<filename>) | <one-line content summary — from the yar:file-inspector report or a direct read> |

## Subfolders

| Folder | Contents |
|---|---|
<!-- list subfolders if any; otherwise delete this section -->
```

If the folder already has several files and had no README, list **all** existing files, not just the new one.

#### c. If it exists → update it

1. Read the current README.
2. Identify its structure (table, list, a specific section).
3. Add a new row with two columns (or the matching format):
   - **Filename** as a markdown link: `[2026-04-15-lab-cbc-results.pdf](2026-04-15-lab-cbc-results.pdf)`
   - **One-line content description**: from the `summary` in the `yar:file-inspector` report; if you authored the file, write a one-line gist from its content.
4. Order: usually newest on top (by the date in the filename). If the README is alphabetical, keep it alphabetical.
5. If the file **replaces** an old version (e.g. a signed copy replacing a draft), remove the old row instead of adding.

### Description content rules

- **One line, max ~80 chars.** Need more detail? Write a separate summary file.
- **Describe "what it is", not "what happened"**: "CBC result, low hemoglobin" — not "assistant added this today".
- **Key numbers and dates** in the description if they matter: "T1 2025 return — $1,200 refund".

### Before / after example

**Before** — `lab-results/README.md`:
```markdown
# Lab Results

| File | Description |
|---|---|
| [2026-03-10-lab-cbc.pdf](2026-03-10-lab-cbc.pdf) | CBC March — all normal |
```

**After** a new file is added:
```markdown
# Lab Results

| File | Description |
|---|---|
| [2026-04-15-lab-cbc-results.pdf](2026-04-15-lab-cbc-results.pdf) | CBC April — hemoglobin 11.2 (low), rest normal |
| [2026-04-15-summary.md](2026-04-15-summary.md) | Summary and reading of the April CBC |
| [2026-03-10-lab-cbc.pdf](2026-03-10-lab-cbc.pdf) | CBC March — all normal |
```

### Checklist before finishing

- [ ] Destination README exists (created if it was missing)?
- [ ] New file recorded in the README?
- [ ] One-line description genuinely comes from content, not the filename?
- [ ] The markdown link points to the right file?
- [ ] If a file was deleted or replaced, its row was removed?
