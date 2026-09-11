# The theme file — a project's stationery set

A theme is a small JSON file that lives in the **host project**, never in yar:

```text
<project>/.claude/pdf-theme.json     preferred
<project>/.pdf-theme.json            alternative
<project>/docs/pdf-theme.json        alternative
```

The renderer walks up from the Markdown file until it finds one. With no theme
it falls back to a monochrome default, which is a perfectly respectable
document — just not *that project's* document.

A starting point is in [`assets/theme.example.json`](../assets/theme.example.json).

## Fields

Every field is optional. Anything omitted is derived or defaulted.

### Identity

| Field | Meaning |
|---|---|
| `name` | The display name. Becomes the wordmark when there is no logo, and the PDF's author metadata. |
| `legal_name` | The registered name, when it differs. |
| `tagline` | One short line under the mark. Not a slogan — a description. |
| `contact` | A list of strings for the foot of the cover and the letterhead. |
| `website` | Appended to the contact line. |
| `logo` | Path to a mark, relative to the theme file. |
| `logo_width_mm` | Printed width of the mark. Default 16. |

**Logo format.** Prefer SVG: it is inlined into the document and stays vector
through Chrome's print pipeline. A raster logo is embedded as a data URI
instead. Use a monochrome mark that fills with `currentColor` so it inherits the
ink; a full-colour logo fights everything else on the page.

### Colour

| Field | Meaning |
|---|---|
| `ink` | The near-black body colour. Default `#111111`. |
| `accent` | The single brand colour. Omit it and the document is fully monochrome. |

The accent is **derived, not used raw**. A screen brand colour is usually too
light to carry a hairline or a folio on paper, so it is darkened along its own
hue until it clears 4.5:1 against white. The secondary greys are all mixes of
the ink, so a warm-black ink produces a warm grey ramp.

The accent appears on at most four things: the eyebrow, the cover rule, the
classification line, and link underlines. Body text is never coloured.

### Type and mood

A mood names five type roles, not one family, because a page that sets its
title and its small print in the same face at two sizes looks converted rather
than designed. Any role may be overridden on its own.

| Field | Meaning |
|---|---|
| `mood` | One of `modern` `formal` `editorial` `technical` `warm` `classic`. |
| `fonts.persian_display` | Arabic-script face for the title and section heads. |
| `fonts.persian` | Arabic-script face for running text. |
| `fonts.latin_display` | Latin face for the title and section heads. |
| `fonts.latin` | Latin face where Latin is the primary script. |
| `fonts.latin_guest` | Latin face for Latin runs *inside* a right-to-left sentence. |
| `fonts.persian_label` | Arabic-script face for small labels, table heads and the folio. |
| `fonts.latin_label` | Latin face for the same. |
| `fonts.mono` | Override the code family. |
| `base_size_pt` | Override the body size. |
| `line_height` | Override the leading. |
| `weights.display` `weights.heading` `weights.body` `weights.emphasis` `weights.label` | Override any weight of the mood's set. `emphasis` is what `<strong>` sets; keep it one step above the body rather than 700. |
| `table.size_em` | Table type relative to the body. Default 0.86. |
| `deck.width_mm` `deck.height_mm` `deck.margin_mm` `deck.base_scale` | Geometry of `kind: deck` slides. Defaults 338.67 × 190.5 mm, 16 mm, 1.55. |

A theme naming only `persian`, `latin` and `mono` still works: the display and
guest roles fall back to those faces.

**The guest role earns its keep.** In a Persian document the Latin words are
company names and terms embedded mid-clause; they must match the class of the
Persian text face and then get out of the way. A sans Persian text face takes a
sans guest, a naskh takes a serif. Setting `fonts.latin` explicitly overrides
the guest in a right-to-left document too, which is how you insist.

**The label role.** Labels, table heads, the running head and the folio are
set small and tracked, where a naskh or a garalde muddies. They take the face
with the largest x-height and the most complete numeral and separator set,
which by default is the family already loaded to supply the Arabic separators
-- so the label role normally costs no extra embedded font. It is also the
right home for a face like Vazirmatn in a document whose prose is set in
something more formal.

**Some faces cannot set text.** Markazi Text, Cormorant Garamond and Fraunces
are display faces: superb at 30pt, spidery at 11. Naming one as a text face is
corrected to the safe face for that script, and `--describe` says so.

The mood picks a pairing and a set of weights, spacing and rule habits.
`python3 scripts/md_to_pdf.py --list-moods` prints the pairings and
`--list-fonts` the full catalogue.

Each mood also carries a weight set (display / heading / body / emphasis /
label): `modern` 300 / 500 / 400 / 500 / 500; the others 300–400 / 600 / 400 /
600 / 500.

| Mood | Display pair | Text pair | RTL guest | Reads as |
|---|---|---|---|---|
| `modern` | Estedad / Inter | Vazirmatn / Inter | Inter | Quiet, current, unbranded. The default. |
| `formal` | Markazi Text / EB Garamond | IBM Plex Sans Arabic / EB Garamond | IBM Plex Sans | Institutional, considered, printed. |
| `editorial` | Estedad / Newsreader | Vazirmatn / Literata | Inter | Written, with a voice. |
| `technical` | Vazirmatn / IBM Plex Sans | Vazirmatn / IBM Plex Sans | IBM Plex Sans | Engineered, dense, precise. |
| `warm` | Vazirmatn / Fraunces | Vazirmatn / Literata | Inter | Human, readable, unhurried. |
| `classic` | Markazi Text / Cormorant Garamond | Noto Naskh Arabic / Source Serif 4 | Source Serif 4 | Traditional and conservative. |

### Locale

| Field | Meaning |
|---|---|
| `language` | BCP-47-ish code. `fa` implies right-to-left, Jalali dates, Persian digits. A document's own `lang:` frontmatter overrides it. |
| `direction` | `rtl` or `ltr`. Derived from the language unless set. |
| `calendar` | `jalali` or `gregorian`. Derived from the language. |
| `digits` | `persian` or `latin`. Derived from the language. |
| `locales` | A per-language layer: `{"fa": {"tagline": ...}, "en": {"mood": "modern", "fonts": {...}, "weights": {...}, "table": {...}}}`. When the document's language matches a key, its identity fields (`name`, `legal_name`, `tagline`, `contact`, `website`, `confidentiality`, `footer_note`) and its register (`mood`, `fonts`, `weights`, `table`, `page`, `base_size_pt`, `line_height`, `ink`, `accent`) override the top-level ones. One theme file serves a project that writes formal Persian and light, modern English. |

### Page and furniture

The margins *are* the measure: prose fills the text block rather than being
capped again inside it. Two levers subtracting from the same edge is what
leaves one side of a page conspicuously empty, so line length is set by
widening or narrowing the margins, not by a separate cap.

| Field | Meaning |
|---|---|
| `page.size` | Default `letter` (8.5 x 11 in), because these documents print on North American trays. `a4` for paper printed outside North America, `legal`, `a5`, or an explicit `"215.9mm 279.4mm"`. Overridable for a single render with `--page-size letter` / `--page-size a4`. |
| `page.margin_*_mm` | `top` `bottom` `inner` `outer`. Inner follows the reading direction. Defaults are near-symmetric, because these documents are read single-sided on a screen; a bound, duplex piece wants the asymmetric spread instead. |
| `cover` | `auto` (cover when the document has a title), `always`, or `never`. |
| `running_header` | The document title at the top inner corner from page two. |
| `page_numbers` | The folio at the bottom outer corner from page two. |
| `confidentiality` | A classification line on the cover. |

## Deriving a theme from a project

When a project has no theme file, build one from what the project already
declares rather than inventing an identity:

1. **Name, tagline, contact** — the README's first heading and description, the
   package manifest (`name`, `description`, `homepage`, `author`), or the
   project's own context document.
2. **Accent** — a brand colour already committed somewhere: a CSS custom
   property, a Tailwind config, a design-token file, `theme_color` in a web app
   manifest, or the dominant colour of an existing logo. Take the *brand* value;
   the renderer handles making it printable.
3. **Logo** — an SVG already in the repo (`assets/`, `public/`, `docs/`,
   `.github/`). Prefer a monochrome or mark-only variant.
4. **Mood** — inferred from what the project *is*, then confirmed with the user:
   a developer tool reads `technical`, a research organisation `formal`, a
   publication `editorial`, a consumer product `modern` or `warm`.
5. **Language** — the language the project's own documents are written in.

Show the resolved theme with `--describe` and confirm it before the first
render. Write the file once, and every later document in that project inherits
it.

## Frontmatter

Per-document metadata goes in the Markdown's YAML frontmatter and feeds the
cover or letterhead. It is never printed as a raw block.

```yaml
---
title: Platform Reliability Review
subtitle: Incident patterns and the remediation plan
type: Engineering Report      # the eyebrow above the title
kind: report                  # report | memo | letter | note | deck
lang: en                      # picks the locales identity
prepared_for: Architecture Council
author: Reliability Group
version: "2.1"
status: Final
reference: DOC-2026-014
confidentiality: Confidential
---
```

`kind: letter` and `kind: memo` produce a letterhead with a reference block
(date, reference, attachment) and an addressee block (`to`, `from`, `subject`)
instead of a cover page. `kind: deck` produces 16:9 slides with a title slide
from the same fields (see the decks reference beside this file). A document with no `title` and
no first-level heading gets neither, which is right for a short note.
