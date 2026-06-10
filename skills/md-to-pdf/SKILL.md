---
name: md-to-pdf
description: Convert a Markdown file into a print-ready, RTL-aware PDF using the Vazirmatn font and headless Chrome — built for Persian/Farsi (and other right-to-left) documents, but works for LTR too. Renders headings, tables, lists, code, blockquotes, and an optional YAML frontmatter block into a clean A4 layout. Fonts are fetched once on first use (no binaries in the repo) and cached. Use when asked to "make a PDF", "export this markdown to PDF", "PDF فارسی بساز", "این مارک‌داون رو PDF کن", or when another skill needs a polished Persian/RTL PDF of a generated document. macOS (or any host with Chrome/Chromium).
---

# md-to-pdf — Markdown → print-ready RTL PDF

Goal: turn a Markdown file into a clean, A4, **print-ready** PDF that renders
Persian/Farsi and other RTL text correctly, using the **Vazirmatn** font. The
heavy lifting is a single self-contained Python script that builds styled HTML
and prints it with headless Chrome.

**This skill is invoke-only.** It converts a file only when you ask (or when a
sibling skill calls it for its own document output).

## 1) Pre-flight
- **Python 3** with the `markdown` package — if missing: `pip3 install markdown`.
- **Google Chrome / Chromium** (used headless for HTML→PDF). The script auto-locates
  Chrome, Chrome Canary, or Chromium on macOS, then `chromium`/`google-chrome` on `PATH`.
- **Fonts:** the three Vazirmatn weights are downloaded **once** (pinned release,
  via jsDelivr) into `~/.cache/yar/md-to-pdf/fonts/` and reused. First run needs
  network; afterwards it works offline. With no cache and no network it degrades
  gracefully to system fonts (SF Arabic / Geeza Pro / Tahoma) — the PDF still renders.

## 2) Convert
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/md-to-pdf/scripts/md_to_pdf.py" <input.md> <output.pdf>
```
- `<input.md>` — the Markdown source. A leading `---` YAML frontmatter block, if
  present, is rendered as a small monospace header box (not parsed as content).
- `<output.pdf>` — destination path; parent directory should already exist.
- Supports tables, fenced code, `attr_list`, and single-newline line breaks.

## 3) Verify before handoff
- The script prints `PDF created: <path>` on success; a non-zero exit prints the
  Chrome stderr. Confirm the file exists.
- Page count: check with `file <output.pdf>` or open it. If the caller wants a
  one-pager and it spilled to two pages, tighten the source Markdown and re-run.

## Special behaviors
- **Fonts cache:** delete `~/.cache/yar/md-to-pdf/fonts/` to force a re-download
  (e.g. after a Vazirmatn version bump in the script's `FONT_TAG`).
- **Reproducible output:** the font release is pinned (`FONT_TAG`) so the same
  Markdown yields the same PDF across machines.
- **Offline:** missing fonts only change the typeface (system fallback), never
  fail the render.
- **No binaries in git:** unlike bundling woff2 files, fonts live in the per-user
  cache — the repo stays binary-free (consistent with the `pre-commit` guard).

## Self-check
- [ ] `PDF created: …` printed and the file exists at the requested path?
- [ ] Persian/RTL text reads right-to-left and renders with Vazirmatn (not a
      tofu/box fallback)? If boxes appear, the font download failed — check network
      or pre-warm the cache.
- [ ] If a specific page count was requested, verified with `file`?

## Dependencies
- **Script:** `scripts/md_to_pdf.py` (stdlib + `markdown`; fonts fetched on demand).
- **System:** Python 3, `markdown` pip package, Google Chrome / Chromium.
- **Font:** Vazirmatn (SIL OFL) — fetched from the pinned release on jsDelivr,
  cached under `~/.cache/yar/md-to-pdf/`.
