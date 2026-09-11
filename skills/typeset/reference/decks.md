# Decks

`kind: deck` sets the document's design on 16:9 pages, one slide per page, in
the same theme as the reports: the display face for the slide titles, the
label face for eyebrows and the slide foot, the table register for tables, the
weight set for emphasis. Nothing on a slide is coloured except the eyebrow.

## Writing a deck

```markdown
---
title: Quarterly review
subtitle: What moved, what did not, and the plan for the next quarter
type: Board deck
kind: deck
prepared_for: The board
author: Finance
confidentiality: Confidential
---

###### Where we are
## Revenue held while the cost base was rebuilt

- Revenue flat by choice while the operating model changed
- Pre-tax margin from 14.6% to 33.6% in one year

---

###### Financial snapshot · CAD
## Profitable in the books, more profitable on the run-rate

| Consolidated | FY2025 | FY2026 | Run-rate |
|---|---|---|---|
| Revenue | 8,961,560 | 12,219,070 | 12,274,823 |
| **Profit before tax** | **1,306,710** | **3,068,224** | **4,126,257** |

---

###### Not in the price
## Options the buyer receives without paying for them

<div class="cols-2" markdown="1">
<div class="tile" markdown="1">
<p class="k">Minority stake · 16%</p>
Carried at cost; revenue about USD 120,000 a month.
</div>
<div class="tile" markdown="1">
<p class="k">Playbook</p>
The operating model built this year, portable to other industries.
</div>
</div>
```

- **Slides are separated by a horizontal rule** (`---` on its own line).
- **The frontmatter makes the title slide**: mark, eyebrow (`type`), title,
  subtitle, and a meta line from `prepared_for`, `author`, `date`, `version`.
- **`######` (h6) directly above the slide title is the eyebrow**: small
  tracked capitals in the accent.
- **`##` is the slide title**; `#` works the same. Keep it to one or two lines.
- **Columns**: `<div class="cols-2" markdown="1">` ... `</div>` (also `cols-3`,
  `cols-4`); `markdown="1"` lets Markdown work inside. A `.tile` is a column
  block with a hairline above; `<p class="k">` inside it is its label.
- **Hero figures**: `<p class="stat">4.9<small>×</small></p>` sets a large
  display-weight number with a small unit.
- **Notes**: `<p class="note">` for a source line under a table.
- **The slide foot** carries the identity, the deck title, the classification
  and the slide number; it is generated, not written.

## Geometry

The page is 338.67 × 190.5 mm (13.33 × 7.5 in), margins 16 mm, body type at
1.55× the document's base size. All four are theme fields under `deck`
(`width_mm`, `height_mm`, `margin_mm`, `base_scale`).

## Checking a deck

Rasterise a few slides (`pdftoppm -png -r 60 -f 1 -l 4 deck.pdf /tmp/slide`) and
read them at thumbnail size: a slide that needs zooming has too much on it.
Tables keep the document register (right-aligned figures, ruled totals); if a
table needs more than about eight rows, it belongs in an appendix, not a slide.
