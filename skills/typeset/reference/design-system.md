# The design system — and why each rule is there

The house style is deliberately narrow: black ink on white, hierarchy carried by
weight and space, at most one accent used four times. Everything below is a
setting the renderer actually applies, with the reason it applies it.

## 1. The page

- **Letter with asymmetric margins.** Outer wider than inner, bottom deeper than
  top: 26 / 38 / 26 / 32 mm by default. Equal margins on four sides is the
  single clearest signal of a generated document. The canons of page
  construction put the ratios near 2:3:4:6; this is a business-document
  compromise on that idea.
- **Inner follows the reading direction.** In a right-to-left document the
  inner margin is on the right, and so are the running head and the binding
  allowance; the folio moves to the outer edge on the left.
- **Measure is held at 34 em.** The text block is wider than that, so prose is
  capped while tables, code and rules use the full width. Unrestrained prose on
  Letter runs past 90 characters a line, well beyond the 45-75 that reads
  comfortably.

## 2. Type

- **Body 10.5 pt at 1.52 leading for Latin; 11.5-13.5 pt at 1.85-1.95 for
  Persian.** Arabic-script letterforms carry their ink far above and below the
  Latin x-height, so at an equal nominal size Persian both looks smaller and
  crowds vertically. Naskh faces, with deeper descenders and a smaller
  x-height, take the top of both ranges.
- **A formal text face is not a friendly one.** A geometric Persian sans reads
  approachable, which is the wrong register on a contract. The formal mood sets
  prose in an institutional Arabic sans and keeps the geometric one for the
  label layer, where its large x-height and complete numeral set are exactly
  what small tracked type needs.
- **Three layers, not two.** Display for the title and heads, text for prose,
  and a label face for table heads, meta labels, the running head and the
  folio. The label face defaults to the family already loaded for the Arabic
  separators, so the third layer usually costs nothing.
- **Two pairs, not one family.** A display pair sets the title, the identity
  and the section heads; a text pair sets everything that is actually read. A
  page whose title and small print are the same face at two sizes looks
  converted; the change of face is what reads as designed.
- **Display-only faces never set text.** A low-x-height naskh or a
  high-contrast garalde is immaculate at 30pt and spidery at 11pt. Those faces
  are marked in the catalogue, and a theme that names one as its text face is
  corrected to the safe face for that script and told so.
- **Paired by x-height per pair.** In a right-to-left document the Persian
  family is primary and the Latin family is layered on with a `unicode-range`
  restricted to *letters*, plus a `size-adjust` computed from the two measured
  x-heights -- once for the display pair and once for the text pair. Digits,
  punctuation, spaces and the zero-width non-joiner stay with the Persian
  family, so a mixed sentence keeps one digit design and no fallback splits an
  Arabic shaping run.
- **Latin is a guest in a Persian sentence.** The Latin words in a Persian
  document are names and terms embedded mid-clause. They must match the class
  of the Persian text face and then disappear: a garalde serif spliced into a
  Persian sans sentence pulls the eye onto "Ltd" instead of the clause. So a
  sans Persian text face takes a sans guest, a naskh takes a serif, and the
  mood's own Latin face is used only where Latin is the primary script.
- **A Latin run keeps its own punctuation.** A neutral character caught between
  a Latin run and the surrounding Persian takes the paragraph direction, so the
  full stop of "Northwind Ventures Corp." migrates to the far side and the name
  reads ". Northwind Ventures Corp". Latin runs are therefore wrapped in an
  isolate.
- **A separator fallback.** Several good Persian families omit the Arabic
  decimal and thousands separators. Left alone, a system font draws them with
  Latin sidebearings and a clean number limps. Those three codepoints are
  therefore always taken from a family known to have them.
- **No letter-spacing on Arabic script.** Tracking must not be applied between
  characters that are shaped together. In a right-to-left document every
  tracked label -- eyebrow, table head, meta label -- drops to zero.
- **Hierarchy by weight, not colour -- and not by bold.** Each mood names a
  weight set: display, heading, body, emphasis, label. `<strong>` sets at the
  emphasis weight, one step above the body (500 or 600), never 700: on a page
  whose hierarchy is carried by weight, a bold strong shouts over the headings
  and flattens the scale. Table heads, eyebrows and meta labels take the label
  weight (500). Light weights appear only at display sizes. A project with a
  taste for a lighter page sets `weights` in its theme (body 300, heading 500,
  emphasis 500 is a common register for a neo-grotesque like Inter).
- **Three visible heading levels.** H1 by size and space, H2 by a hairline
  above, H3 by weight alone. H4 and below become a tracked uppercase label, not
  another size.

## 3. Colour

- **Body text is the ink, always.** Default `#111111`.
- **The grey ramp is mixed from the ink**, at 32% (secondary), 55% (muted) and
  80% (rules), so a warm black yields a warm grey rather than a neutral one
  fighting it.
- **The accent is derived for print.** A brand colour is darkened along its hue
  until it clears 4.5:1 on white, because the raw screen value cannot carry a
  hairline rule or a folio on paper.
- **The accent appears four times at most**: eyebrow, cover rule,
  classification line, link underline. With no brand colour the document is
  fully monochrome, which is the default.

## 4. Tables

- **A register of their own.** Type a step smaller than the prose (0.86 em by
  default), tighter leading, the column heads as small tracked labels under a
  single rule. Body-size figures in a table are the surest sign of a converted
  document.
- **Figures align on the right in tabular lining numerals**, header included,
  so a column of amounts reads down the page. `tables.py` finds the numeric
  columns; nothing is asked of the author.
- **Rules only where they mean something.** In a numeric table there is no
  rule between ordinary rows: the aligned figures carry the eye. A hairline
  above a sub-total, a firmer rule above a total, a double rule under the final
  line. Text tables keep a hairline between rows because long cells need the
  guide. Never vertical rules, boxes, zebra stripes or a reversed header.
- **A bold label is a total.** In a numeric table, a row whose first cell is
  bold is set as a total (rule above, emphasis weight) when such rows are the
  minority; the last of them takes the double rule. In a text table bold is
  just a label.
- **Statements are tables with structure**: section heads in small caps,
  groups, indented items, group sub-totals, key lines, a double-ruled last line
  (`statements.py`). Figures print whole, negatives in parentheses, nil as a
  dash -- the conventions of a printed statement.
- Outer cells lose their side padding, so the table's edges sit flush with the
  text block instead of floating inside it.

## 5. Fragmentation

- **The margins are the measure.** Prose fills the text block; there is no
  second em-based cap inside it. Two levers subtracting from the same edge is
  what leaves a page looking half-used.
- Headings never end a page: `break-after: avoid`.
- Paragraphs keep three lines together at a break; list items and quotations two.
- **A long table breaks and repeats its `<thead>`.** Refusing the break is the
  worst thing a print stylesheet can do: a twenty-row table that does not fit
  in the remaining space is moved whole to the next page and leaves most of
  this one blank. What must not break is a *row* -- a rule drawn through the
  middle of a cell reads as a defect -- and a head must never be stranded from
  its first row.
- A short table (sixteen rows or fewer) stays whole; a total row never starts
  a page, so a sum is not stranded from what it sums.
- Code blocks and figures stay whole; they are short by nature and a split
  border reads as damage.
- **A deck is the same design on a 16:9 page.** One slide per page, the slide
  is the page (margins move inside it), no running head or folio -- the slide
  foot carries the identity, the deck title, the classification and the
  number. Titles in the display face, eyebrows in the label face and the
  accent, tables in the table register.
- The cover carries no running head and no folio; page numbering starts to
  appear on page two.

## 6. What this deliberately does not do

- **No justified text.** In this script a browser can only stretch word spaces,
  which opens rivers; kashida justification is not implemented in Chrome.
  Ragged is the honest setting.
- **No frontmatter block on the page.** Metadata becomes the cover or the
  letterhead. A monospace dump of YAML at the top of page one is the classic
  generated-document tell.
- **No repeated title.** When the cover states the title, the matching first
  heading is removed from the body.
- **No decorative colour, gradients, boxes or drop shadows.** If an element
  needs emphasis, it gets space or weight.

## 7. Sources

The rules above follow the mainstream of print typography practice: Butterick's
*Practical Typography* (point size, measure, margins, headings, tables, colour,
widow and orphan control), Bringhurst via Rutter's *The Elements of Typographic
Style Applied to the Web* (measure, leading, tracking of caps), the `booktabs`
documentation and Tufte (rules, no vertical lines, no striping), the W3C
*Arabic and Persian Layout Requirements* and CSS Text Level 3 (leading,
justification, letter-spacing on shaped runs), Unicode CLDR and the Persian
computing literature (digits, separators, punctuation, the zero-width
non-joiner), and the restrained end of institutional identity practice for the
stationery layer.
