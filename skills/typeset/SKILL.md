---
name: typeset
description: Design and typeset documents from Markdown in the host project's own house style, with PDF as the output (formerly md-to-pdf). A per-project theme (identity, logo, one accent, type pairing, mood, weights, locale) gives every project a consistent identity; hierarchy comes from font weight and whitespace, never bold-and-bigger. Reports get a cover, letters and memos a letterhead, decks 16:9 slides. Tables are set in their own register (smaller type, right-aligned tabular figures, rules only under the head and above totals, bold label rows read as totals) and financial statements (sections, groups, indented items, double-ruled final line) render from Python rows or a QuickBooks export. RTL/Persian is first-class (mirrored layout, x-height-matched pairs, Persian digits, Jalali dates). Paper is Letter; A4 on request. Fonts open-licence, pinned, cached. Use when asked to "make a PDF", "typeset this", "design a proper document", "build a deck", "lay out these statements", "پی‌دی‌اف بساز". Needs Chrome/Chromium.
---

# typeset — designed documents from Markdown, in the project's own house style

Turns a Markdown file into a document that looks like it came from a design
studio rather than a converter, and prints it to PDF: black ink, hierarchy
carried by font weight and whitespace, at most one accent, a real cover or
letterhead, a running head and a folio — or, for a deck, one 16:9 slide per
page. Right-to-left and Persian typography are first-class, and Latin
documents get the same care.

Three things make it a design system rather than a renderer:

- **A theme per project.** Identity, ink, accent, type pairing, mood, weights
  and locale live in a small JSON file in the *host* project, so the same skill
  produces a different, internally consistent house style everywhere it is used.
- **A weight register, not bold.** Display, heading, body, emphasis and label
  weights are named by the mood and can be tuned per project. `<strong>` sets
  one step above the body, so emphasis never shouts over the headings.
- **A table register.** Every Markdown table is classified: numeric columns
  align on the right in tabular figures, bold label rows become ruled totals,
  numeric tables drop the rules between ordinary rows, text tables keep a
  hairline. Financial statements come from Python rows or straight from a
  QuickBooks export and render with sections, groups, indented items and a
  double-ruled final line.

**This skill is invoke-only.** It renders a file when you ask, or when a
sibling skill needs a polished document.

---

## 1. Establish the project's identity first

**Before the first render in a project, resolve that project's theme.** Do not
render a generic document and do not carry another project's identity over.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/typeset/scripts/typeset.py" <input.md> --describe
```

This prints the resolved theme — faces, sizes, weights, table size, locale — and
the file it came from.

- **A theme file already exists** (`.claude/pdf-theme.json` at the project
  root, or `.pdf-theme.json`, or `docs/pdf-theme.json`) — you are done, render.
- **No theme file** — build one from what the project already declares, then
  confirm it with the user before writing it:
  1. **Identity** — name, tagline and contact from the README's opening, the
     package manifest, or the project's own context document. Read the project's
     declared context source; never assume one. A project that writes in two
     languages puts the second identity under `locales`.
  2. **Accent** — a brand colour the project already commits: a CSS custom
     property, a design-token file, a Tailwind config, a web-app manifest
     `theme_color`, or the dominant colour of its logo. One colour, not a
     palette. Omit it and the document is monochrome, which is a legitimate answer.
  3. **Logo** — an SVG already in the repo. Prefer a monochrome or mark-only
     variant that fills with `currentColor`.
  4. **Mood** — inferred from what the project is, then confirmed:
     `technical` for a developer tool, `formal` for an institution,
     `editorial` for a publication, `modern` or `warm` for a consumer product.
  5. **Weights** — only if the project has a stated preference (a light body
     face, a lighter emphasis). The mood's set is right for most projects.
  6. **Language** — the language the project's own documents are written in.

  Write it to `<project>/.claude/pdf-theme.json`. Every later document in that
  project inherits it, so this is a one-time step per project.

Full field list and the derivation recipe: [`reference/theming.md`](reference/theming.md).

## 2. Render

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/typeset/scripts/typeset.py" <input.md> <output.pdf>
```

| Flag | Effect |
|---|---|
| `--theme PATH` | Use a specific theme file instead of discovering one. |
| `--mood NAME` | `modern` `formal` `editorial` `technical` `warm` `classic`. |
| `--lang CODE` | Override the language; drives direction, calendar, digits and the `locales` identity. |
| `--accent HEX` | Override the accent for one render. |
| `--kind KIND` | `report` `memo` `letter` `note` `deck`. Letters and memos get a letterhead; a deck gets 16:9 slides. |
| `--page-size SIZE` | `letter` (default, 8.5 x 11 in) or `a4`. Letter is the paper in North American trays; ask for `a4` only for a document printed outside North America. |
| `--no-cover` | Never render a cover page. |
| `--offline` | Never reach the network; use cached fonts or system fallbacks. |
| `--describe` | Print the resolved theme and exit. |
| `--keep-html PATH` | Also write the intermediate HTML, for debugging a layout. |
| `--list-moods`, `--list-fonts` | Print the pairings and the font catalogue. |

## 3. Give the document its metadata

Frontmatter becomes the cover, the letterhead or the title slide — it is never
printed as a raw block, and a title stated on the cover is removed from the body
so it is not said twice.

```yaml
---
title: Platform Reliability Review
subtitle: Incident patterns and the remediation plan for the coming quarter
type: Engineering Report          # the small label above the title
kind: report                      # report | memo | letter | note | deck
prepared_for: Architecture Council
author: Reliability Group
version: "2.1"
status: Final
confidentiality: Confidential
lang: en                          # per-document language; picks the locales identity
---
```

For a letter or memo add `kind: letter`, then `to`, `from`, `subject`,
`reference` and `attachment` as needed. A short note with no title gets neither
cover nor letterhead, which is correct.

## 4. Tables and statements

Write ordinary Markdown tables; the register does the rest. What it reads:

- **Bold the label of a total row** (`| **Total** | 1,200 |`). In a table whose
  columns are mostly figures, bold label rows are set as totals with a rule
  above; the last one gets the double rule. In a text table bold labels are
  just labels.
- **Figures are figures.** A column whose cells are mostly numbers (thousands
  separators, `%`, `×`, parentheses for negatives, a dash for nil) is aligned
  on the right in tabular figures, header included.
- **Short tables stay whole**, long ones break and repeat their head; a total
  is never stranded from the lines it sums.

A full financial statement — sections, groups, indented items, group
sub-totals, a double-ruled final line, footnote markers — comes from
`scripts/statements.py`, and `scripts/quickbooks_export.py` reads a
QuickBooks Online report export into rows for it. Recipe and the row classes:
[`reference/tables-and-statements.md`](reference/tables-and-statements.md).

## 5. Decks

`kind: deck` sets the same design on 16:9 pages. Split slides with a horizontal
rule (`---`); a `######` line above the slide title is the eyebrow; the
frontmatter makes the title slide; `<div class="cols-2" markdown="1">` lays two
columns, `.stat` sets a hero figure. Recipe: [`reference/decks.md`](reference/decks.md).

## 6. Verify before handoff

- The script prints `PDF created:` with the theme, the kind and the page
  count. Confirm the file exists and the page count is what was asked for.
- **Look at it.** Rasterise and actually read a page or two:
  `pdftoppm -png -r 90 -f 1 -l 2 out.pdf /tmp/page` then open the PNGs.
  Check the cover reads as one composition, the running head and folio appear
  from page two (never on the cover), no heading is stranded at a page foot,
  and tables read as designed: figures right-aligned, totals ruled, no rule
  between the ordinary rows of a numeric table.
- **Persian text:** confirm right-to-left flow, correct Persian digits, tight
  decimal and thousands separators, punctuation that stays with its own Latin
  run ("Corp." not ". Corp"), and no tofu boxes. Boxes mean the font download
  failed — check the network or pre-warm the cache.
- **Look for a page that stops early.** A page whose last third is blank means
  something refused to break. Long tables are expected to break and repeat
  their head; if one jumped whole to the next page, that is a bug, not the content.
- If a one-pager spilled to two pages, tighten the source Markdown rather than
  shrinking the type.

## Special behaviours

- **Fonts are pinned, fetched once, cached.** Open-licence variable fonts come
  from a pinned Fontsource release into `~/.cache/yar/typeset/fonts/` (a cache
  left by the former `md-to-pdf` name is adopted). First run needs network;
  afterwards it is offline. No binaries in any repo.
- **Reproducible.** The same Markdown plus the same theme yields the same PDF
  on any machine.
- **Degrades, never fails.** A missing font changes the typeface to a system
  fallback; the PDF still renders.
- **Latin context is preserved.** In a Persian document, digits inside version
  strings, URLs, paths, emails and code stay ASCII, because those are Latin
  context and must read as such.
- **Author classes survive.** A cell or table that already carries a class
  keeps it; the register merges its own classes in rather than replacing them.

## Self-check

- [ ] Theme resolved from *this* project — not the default, not another project's?
- [ ] `PDF created: …` printed and the file exists?
- [ ] Pages inspected as images, not just assumed?
- [ ] Cover has no running head or folio; page two onward has both?
- [ ] Tables: figures right-aligned, totals ruled, text tables hairlined?
- [ ] Persian: right-to-left, Persian digits, correct separators, Latin runs
      keeping their own punctuation, no tofu?
- [ ] No page ending in a large blank because something refused to break?
- [ ] Requested page count met?

## Dependencies

- **Scripts:** `scripts/typeset.py` (CLI; `md_to_pdf.py` is a compatibility
  entry point), `scripts/theme.py` (theme model, moods, weights, table and deck
  settings, Jalali dates, digits, colour), `scripts/render.py` (HTML and CSS,
  bidi isolation, localized stationery, the deck layer), `scripts/tables.py`
  (the table register), `scripts/statements.py` (financial statements),
  `scripts/quickbooks_export.py` (QuickBooks report exports → rows),
  `scripts/fonts.py` (font catalogue, display-only guard, fetching).
- **System:** Python 3, the `markdown` pip package, Google Chrome or Chromium.
  `openpyxl` only for reading a QuickBooks export; `poppler` (`pdftoppm`) is
  optional but is what makes visual verification possible.
- **Fonts:** open-licence (SIL OFL) families from a pinned Fontsource release,
  cached under `~/.cache/yar/typeset/`.
- **Design rationale:** [`reference/design-system.md`](reference/design-system.md).
- **Theme reference:** [`reference/theming.md`](reference/theming.md).
- **Tables and statements:** [`reference/tables-and-statements.md`](reference/tables-and-statements.md).
- **Decks:** [`reference/decks.md`](reference/decks.md).
- **Samples:** [`assets/samples/`](assets/samples/) — a report with tables, a statement, a deck.
