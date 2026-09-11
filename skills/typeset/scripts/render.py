#!/usr/bin/env python3
"""HTML + CSS generation for typeset.

The document is assembled in three layers: a stationery layer (cover or
letterhead, running head, folio) built from the theme; a content layer from the
Markdown; and a typographic layer that is entirely weight- and space-driven --
one ink, at most one accent, no decorative colour anywhere.

Two faces carry the type: a display pair sets the title, the identity and the
section heads, and a text pair sets everything that is actually read. Each
@font-face is embedded as base64, so the emitted faces are deduplicated by
(family, unicode-range, size-adjust) -- naming the same family in two roles must
not double the file.

Tables are a register of their own (smaller type, tabular figures, rules only
where they mean something -- see tables.py and statements.py for the classes),
and `kind: deck` sets the same design on 16:9 pages, one slide per page.
"""
import html as html_mod
import re
from html.parser import HTMLParser

import fonts
import theme as theme_mod

# Elements whose text is Latin context by definition and must not be touched.
_OPAQUE = ("code", "pre", "script", "style", "kbd", "samp", "var")
_VOID = ("area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr")
# A cell is numeric when it holds only digits (ASCII or Persian), separators,
# signs and currency marks -- those get tabular figures so columns line up.
_NUMERIC_CELL = re.compile(
    "^[\\s\\d.,%+\\-()$\u20ac\u00a3"
    "\u060c\u066a\u066b\u066c\u06f0-\u06f9]+$"
)
_PERSIAN_DIGIT_RANGE = ("\u06f0", "\u06f9")
# A Latin run inside a right-to-left sentence. Isolating the run is what keeps
# the full stop of "Northwind Ventures Corp." at the end of the name: a neutral
# character caught between a Latin run and the surrounding Persian takes the
# paragraph direction, so the bidi algorithm moves it to the far side and the
# name reads ". Northwind Ventures Corp". The pattern takes a first token that
# holds at least one letter, any further tokens joined by internal punctuation,
# and the punctuation that closes the run.
_LATIN_RUN = re.compile(
    "[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*"
    "(?:[ \u00a0&/'\u2019._:+#!?-]+[A-Za-z0-9]+)*"
    "[.!?]?"
)


class _Walker(HTMLParser):
    """Rewrites an HTML fragment: digit conversion and bidi isolation.

    Text inside code-like elements is left exactly as written, inline code and
    links get dir="auto" so a Latin run inside a Persian sentence keeps its own
    base direction, bare Latin runs in a right-to-left document are wrapped in
    an isolate so their own punctuation stays with them, and numeric table
    cells are marked for tabular figures.
    """

    def __init__(self, digits="latin", isolate_latin=False):
        super().__init__(convert_charrefs=False)
        self.digits = digits
        self.isolate_latin = isolate_latin
        self.out = []
        self.depth_opaque = 0
        self._cell = None
        self._cell_tag = None

    def handle_starttag(self, tag, attrs):
        attrs = list(attrs)
        if tag in _OPAQUE:
            self.depth_opaque += 1
        if tag in ("code", "a", "time") and not any(k == "dir" for k, _ in attrs):
            attrs.append(("dir", "auto"))
        if tag in ("td", "th"):
            self._cell = len(self.out)
            self._cell_tag = (tag, list(attrs))
        self.out.append(self._tag(tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.out.append(self._tag(tag, list(attrs), close=True))

    def handle_endtag(self, tag):
        if tag in _OPAQUE and self.depth_opaque:
            self.depth_opaque -= 1
        if tag in ("td", "th") and self._cell is not None:
            text = "".join(self.out[self._cell + 1:])
            has_digit = any(
                c in "0123456789"
                or _PERSIAN_DIGIT_RANGE[0] <= c <= _PERSIAN_DIGIT_RANGE[1]
                for c in text
            )
            if text.strip() and has_digit and _NUMERIC_CELL.match(text):
                # Merge into any class the author (or tables.py) already set: a
                # second class="..." on one tag is dropped by the parser.
                ctag, cattrs = self._cell_tag
                self.out[self._cell] = self._tag(ctag, _with_class(cattrs, "num"))
            self._cell = None
        self.out.append("</{}>".format(tag))

    def handle_data(self, data):
        if self.depth_opaque:
            self.out.append(data)
            return
        if self.digits == "persian":
            data = theme_mod.to_persian_digits(data)
        if self.isolate_latin:
            data = _LATIN_RUN.sub(
                lambda m: '<span dir="ltr">{}</span>'.format(m.group(0)), data)
        self.out.append(data)

    def handle_entityref(self, name):
        self.out.append("&{};".format(name))

    def handle_charref(self, name):
        self.out.append("&#{};".format(name))

    def handle_comment(self, data):
        self.out.append("<!--{}-->".format(data))

    @staticmethod
    def _tag(tag, attrs, close=False):
        parts = ["<" + tag]
        for key, value in attrs:
            parts.append(" {}".format(key) if value is None
                         else ' {}="{}"'.format(key, html_mod.escape(value, quote=True)))
        parts.append("/>" if close or tag in _VOID else ">")
        return "".join(parts)


def _with_class(attrs, token):
    """attrs with `token` merged into the class attribute (never a second class=)."""
    out, classes = [], []
    for key, value in attrs:
        if key == "class":
            classes.extend((value or "").split())
        else:
            out.append((key, value))
    if token not in classes:
        classes.append(token)
    out.append(("class", " ".join(classes)))
    return out


def transform(html_fragment, digits="latin", isolate_latin=False):
    walker = _Walker(digits=digits, isolate_latin=isolate_latin)
    walker.feed(html_fragment)
    walker.close()
    return "".join(walker.out)


# Stationery labels per language. A Persian letter that says "SUBJECT" over a
# Persian subject line is a template showing through; the label belongs to the
# reader's language, not to the code's.
LABELS = {
    "fa": {
        "Prepared for": "\u062a\u0647\u06cc\u0647\u200c\u0634\u062f\u0647 \u0628\u0631\u0627\u06cc",
        "Prepared by": "\u062a\u0647\u06cc\u0647\u200c\u0634\u062f\u0647 \u062a\u0648\u0633\u0637",
        "Author": "\u0646\u0648\u06cc\u0633\u0646\u062f\u0647",
        "Date": "\u062a\u0627\u0631\u06cc\u062e",
        "Version": "\u0646\u0633\u062e\u0647",
        "Status": "\u0648\u0636\u0639\u06cc\u062a",
        "Reference": "\u0634\u0645\u0627\u0631\u0647",
        "Attachment": "\u067e\u06cc\u0648\u0633\u062a",
        "To": "\u0628\u0647",
        "From": "\u0627\u0632",
        "Subject": "\u0645\u0648\u0636\u0648\u0639",
    },
}


def _esc(value):
    return html_mod.escape(str(value), quote=True)


def _label(theme, text):
    """The stationery label for one field, in the document's own language."""
    base = str(theme.get("language") or "en").split("-")[0].lower()
    return LABELS.get(base, {}).get(text, text)


def _local(theme, text):
    """Apply the theme's digit system to a short stationery string."""
    text = str(text)
    return theme_mod.to_persian_digits(text) if theme["digits"] == "persian" else text


# --- stationery ------------------------------------------------------------
def _mark(theme, inline_svg=None):
    """The identity mark: an inlined SVG when the theme has one, else a wordmark."""
    if inline_svg:
        width = theme.get("logo_width_mm") or 16
        return '<div class="mark" style="width:{}mm">{}</div>'.format(width, inline_svg)
    name = theme.get("name")
    if not name:
        return ""
    return '<div class="mark wordmark">{}</div>'.format(_esc(name))


def _contact_line(theme):
    bits = list(theme.get("contact") or [])
    if theme.get("website"):
        bits.append(theme["website"])
    if not bits:
        return ""
    sep = '<span class="sep">/</span>'
    return '<div class="contact">{}</div>'.format(
        sep.join('<span dir="auto">{}</span>'.format(_esc(b)) for b in bits))


def cover_html(theme, meta, inline_svg=None):
    """A restrained cover: mark, eyebrow, title, one rule, a meta grid, a foot line."""
    rows = []
    for label, key in (("Prepared for", "prepared_for"), ("Prepared by", "prepared_by"),
                       ("Author", "author"), ("Date", "date"), ("Version", "version"),
                       ("Status", "status"), ("Reference", "reference")):
        value = meta.get(key)
        if value:
            rows.append(
                '<div class="row"><dt>{}</dt><dd dir="auto">{}</dd></div>'.format(
                    _esc(_label(theme, label)), _esc(_local(theme, value))))
    eyebrow = meta.get("type") or meta.get("kind")
    parts = ['<section class="cover">', '<header class="cover-top">',
             _mark(theme, inline_svg)]
    if theme.get("tagline"):
        parts.append('<div class="tagline">{}</div>'.format(_esc(theme["tagline"])))
    parts.append("</header>")
    parts.append('<div class="cover-title">')
    if eyebrow:
        parts.append('<p class="eyebrow">{}</p>'.format(_esc(eyebrow)))
    parts.append('<h1 class="display">{}</h1>'.format(_esc(meta.get("title") or "")))
    if meta.get("subtitle"):
        parts.append('<p class="subtitle">{}</p>'.format(_esc(meta["subtitle"])))
    if theme["mood_spec"].get("cover_rule") != "none":
        parts.append('<div class="cover-rule {}"></div>'.format(
            theme["mood_spec"].get("cover_rule", "short")))
    if rows:
        parts.append('<dl class="meta">{}</dl>'.format("".join(rows)))
    parts.append("</div>")
    foot = [_contact_line(theme)]
    if meta.get("confidentiality") or theme.get("confidentiality"):
        foot.append('<div class="classification">{}</div>'.format(
            _esc(meta.get("confidentiality") or theme["confidentiality"])))
    parts.append('<footer class="cover-foot">{}</footer>'.format("".join(f for f in foot if f)))
    parts.append("</section>")
    return "".join(parts)


def letterhead_html(theme, meta, inline_svg=None):
    """A letter/memo head: identity block, hairline, then the reference block."""
    refs = []
    for label, key in (("Date", "date"), ("Reference", "reference"),
                       ("Attachment", "attachment")):
        if meta.get(key):
            refs.append('<div><dt>{}</dt><dd dir="auto">{}</dd></div>'.format(
                _esc(_label(theme, label)), _esc(_local(theme, meta[key]))))
    addressed = []
    for label, key in (("To", "to"), ("From", "from"), ("Subject", "subject")):
        if meta.get(key):
            addressed.append('<div><dt>{}</dt><dd dir="auto">{}</dd></div>'.format(
                _esc(_label(theme, label)), _esc(meta[key])))
    parts = ['<section class="letterhead">', '<div class="lh-top">',
             '<div class="lh-identity">', _mark(theme, inline_svg)]
    if theme.get("tagline"):
        parts.append('<div class="tagline">{}</div>'.format(_esc(theme["tagline"])))
    parts.append("</div>")
    if refs:
        parts.append('<dl class="lh-refs">{}</dl>'.format("".join(refs)))
    parts.append("</div>")
    parts.append(_contact_line(theme))
    parts.append('<div class="lh-rule"></div>')
    if addressed:
        parts.append('<dl class="lh-address">{}</dl>'.format("".join(addressed)))
    if meta.get("title"):
        parts.append('<h1 class="letter-title">{}</h1>'.format(_esc(meta["title"])))
    parts.append("</section>")
    return "".join(parts)


# --- CSS -------------------------------------------------------------------
def build_css(theme, running_head="", offline=False, deck=False):
    rtl = theme["direction"] == "rtl"
    mood = theme["mood_spec"]
    fam = theme["fonts"]
    page = theme["page"]

    faces = []
    emitted = set()

    def add_face(family_id, unicode_range=None, adjust=None):
        """Emit one family's @font-face once. Each face is an embedded base64
        woff2, so naming a family in two roles must not embed it twice."""
        if not family_id:
            return
        key = (family_id, unicode_range, adjust)
        if key in emitted:
            return
        emitted.add(key)
        rule = fonts.face_css(family_id, unicode_range=unicode_range,
                              adjust=adjust, offline=offline)
        if rule:
            faces.append(rule)

    p_text = fam["persian"]
    l_text = fam["latin"]
    p_disp = fam.get("persian_display") or p_text
    l_disp = fam.get("latin_display") or l_text
    p_lab = fam.get("persian_label") or p_text
    l_lab = fam.get("latin_label") or l_text

    if rtl:
        # Persian is primary and owns digits, punctuation and the shaping runs;
        # Latin is layered over it, letters only, x-height matched per pair.
        add_face(p_text)
        add_face(l_text, fonts.RANGE_LATIN_LETTERS, fonts.size_adjust(l_text, p_text))
        add_face(p_disp)
        add_face(l_disp, fonts.RANGE_LATIN_LETTERS, fonts.size_adjust(l_disp, p_disp))
        add_face(p_lab)
        add_face(l_lab, fonts.RANGE_LATIN_LETTERS, fonts.size_adjust(l_lab, p_lab))
        # The Arabic separators. The label face is the separator source by
        # default, so it already sits in the document and only has to tail the
        # text stack, where per-character fallback picks up the three
        # codepoints a text face may omit. A theme that moved the label role
        # elsewhere gets the old restricted face instead -- one more embed, but
        # the separators stay right.
        sep = ()
        if p_lab == fonts.SEPARATOR_SOURCE:
            sep_tail = (p_lab,)
        elif fonts.SEPARATOR_SOURCE not in (p_text, p_disp):
            add_face(fonts.SEPARATOR_SOURCE, fonts.RANGE_PERSIAN_SEPARATORS)
            sep = (fonts.SEPARATOR_SOURCE,)
            sep_tail = ()
        else:
            sep_tail = ()
        text_stack = fonts.stack(l_text, *sep, p_text, *sep_tail)
        # A display naskh often omits the Arabic separators, so the text face
        # tails the display stack and supplies them character by character.
        display_stack = fonts.stack(l_disp, p_disp, p_text) if p_disp != p_text \
            else fonts.stack(l_disp, *sep, p_text)
        label_stack = fonts.stack(l_lab, p_lab)
    else:
        add_face(l_text)
        add_face(p_text, fonts.RANGE_ARABIC)
        add_face(l_disp)
        add_face(p_disp, fonts.RANGE_ARABIC)
        add_face(l_lab)
        add_face(p_lab, fonts.RANGE_ARABIC)
        text_stack = fonts.stack(l_text, p_text)
        display_stack = fonts.stack(l_disp, p_disp)
        label_stack = fonts.stack(l_lab, p_lab)
    add_face(fam["mono"])
    mono_stack = fonts.stack(fam["mono"])

    base = theme["base_size_pt"]
    weights = theme["weights"]
    scale = mood["scale"]
    ink = theme["ink"]
    accent = theme["accent"]
    rule = theme_mod.mix_with_white(ink, 0.80)
    rule_strong = theme_mod.mix_with_white(ink, 0.55)
    ink2 = theme_mod.mix_with_white(ink, 0.32)
    ink3 = theme_mod.mix_with_white(ink, 0.55)

    # Page geometry: the outer margin is wider than the inner, the bottom deeper
    # than the top, and "inner" follows the reading direction.
    top, bottom = page["margin_top_mm"], page["margin_bottom_mm"]
    inner, outer = page["margin_inner_mm"], page["margin_outer_mm"]
    page_size = page["size"]
    # The cover is exactly one page tall, so the layout needs the paper's real
    # height in mm, not just the CSS keyword. An unrecognised size falls back
    # to the default paper rather than silently keeping A4's 297 mm.
    paper_h = (theme_mod.page_mm(page_size)
               or theme_mod.PAPER_MM[theme_mod.DEFAULT_PAGE["size"]])[1]
    if deck:
        # One slide per page: the slide is the page, so the margins move
        # inside the slide and the @page box carries no furniture.
        d = theme["deck"]
        page_size = "{}mm {}mm".format(d["width_mm"], d["height_mm"])
        paper_h = float(d["height_mm"])
        top = bottom = inner = outer = 0
        base = round(base * float(d.get("base_scale") or 1.5), 2)
    m_right, m_left = (inner, outer) if rtl else (outer, inner)
    head_box = "@top-right" if rtl else "@top-left"
    folio_box = "@bottom-left" if rtl else "@bottom-right"
    counter_style = ", persian" if theme["digits"] == "persian" else ""
    list_style = "persian" if theme["digits"] == "persian" else "decimal"
    # CSS Text 3: letter-spacing must not be applied between characters that are
    # shaped together, which is every Arabic-script run. Labels in an RTL
    # document therefore carry no tracking at all.
    track_label = "0" if rtl else "0.1em"
    track_eyebrow = "0" if rtl else "0.16em"
    track_micro = "0" if rtl else "0.08em"

    furniture = []
    if running_head and theme.get("running_header") and not deck:
        furniture.append("""  {box} {{
    content: "{text}";
    font-family: {label_stack};
    font-size: {size}pt;
    font-weight: 500;
    letter-spacing: {track};
    color: {ink3};
  }}""".format(box=head_box, text=running_head.replace('"', "'"),
               label_stack=label_stack, size=round(base * 0.72, 2), ink3=ink3,
               track="0" if rtl else "0.06em"))
    if theme.get("page_numbers") and not deck:
        furniture.append("""  {box} {{
    content: counter(page{cs});
    font-family: {label_stack};
    font-size: {size}pt;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    color: {ink3};
  }}""".format(box=folio_box, cs=counter_style, label_stack=label_stack,
               size=round(base * 0.78, 2), ink3=ink3))

    css = """
{faces}

:root {{
  --ink: {ink};
  --ink-2: {ink2};
  --ink-3: {ink3};
  --rule: {rule};
  --rule-strong: {rule_strong};
  --accent: {accent};
  --base: {base}pt;
  --lh: {lh};
  --text: {text_stack};
  --display: {display_stack};
  --label: {label_stack};
  --mono: {mono_stack};
  --w-display: {w_display};
  --w-heading: {w_heading};
  --w-body: {w_body};
  --w-emphasis: {w_emphasis};
  --w-label: {w_label};
  --table-size: {table_size}em;
  --s-h1: {s_h1}pt;
  --s-h2: {s_h2}pt;
  --s-h3: {s_h3}pt;
  --s-label: {s_label}pt;
  --s-small: {s_small}pt;
  --s-micro: {s_micro}pt;
  --s-display: {s_display}pt;
  --s-title: {s_title}pt;
  --gap: {gap}em;
}}

@page {{
  size: {size};
  margin: {top}mm {right}mm {bottom}mm {left}mm;
{furniture}
}}
/* The cover carries no furniture: no running head, no folio. */
@page :first {{
  {head_box} {{ content: ""; }}
  {folio_box} {{ content: ""; }}
}}

html {{ font-size: var(--base); }}
body {{
  margin: 0;
  direction: {direction};
  text-align: start;
  font-family: var(--text);
  font-size: var(--base);
  font-weight: var(--w-body);
  line-height: var(--lh);
  color: var(--ink);
  font-variant-numeric: proportional-nums;
  -webkit-font-feature-settings: "kern" 1, "liga" 1;
  font-kerning: normal;
  /* Justification in this script stretches word spaces only, which opens
     rivers; ragged is the honest setting. */
  text-align: start;
  hyphens: none;
}}

/* Measure: the text block itself, set by the page margins. An extra em-based
   cap inside the block subtracts from the same edge a second time, which is
   what leaves a page looking half-used; the margins are the one lever. The
   remaining cap is a guard for paper wider than Letter, not a design choice. */
p, ul, ol, blockquote {{ max-width: 52em; }}
p {{ margin: 0 0 var(--gap) 0; orphans: 3; widows: 3; }}
p + p {{ margin-top: 0; }}

h1, h2, h3, h4, h5, h6 {{
  break-after: avoid-page;
  page-break-after: avoid;
  color: var(--ink);
  font-weight: var(--w-heading);
  line-height: 1.3;
}}
h1 {{
  font-family: var(--display);
  font-size: var(--s-h1);
  letter-spacing: {tracking};
  margin: 2.1em 0 0.7em;
}}
h1:first-child {{ margin-top: 0; }}
h2 {{
  font-family: var(--display);
  font-size: var(--s-h2);
  margin: 1.9em 0 0.55em;
  padding-top: 0.75em;
  border-top: {rule_pt}pt solid var(--rule);
}}
h3 {{ font-size: var(--s-h3); font-weight: var(--w-heading); margin: 1.35em 0 0.35em; }}
h4, h5, h6 {{
  font-family: var(--label);
  font-size: var(--s-label);
  font-weight: var(--w-label);
  letter-spacing: {track_label};
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 1.3em 0 0.3em;
}}

/* Emphasis is one weight step above the body, not bold: on a page whose
   hierarchy is carried by weight, a 700 strong shouts over the headings. */
strong, b {{ font-weight: var(--w-emphasis); color: var(--ink); }}
sup {{ font-size: 0.72em; line-height: 0; vertical-align: super; font-weight: var(--w-body); }}
em, i {{ font-style: italic; }}
a {{ color: var(--ink); text-decoration: none; border-bottom: 0.5pt solid var(--accent); }}

ul, ol {{ margin: 0 0 var(--gap); padding-inline-start: 1.35em; padding-inline-end: 0; }}
ol {{ list-style-type: {list_style}; }}
li {{ margin: 0.18em 0; orphans: 2; widows: 2; }}
li::marker {{ color: var(--ink-3); font-size: 0.9em; }}
ul ul, ol ol, ul ol, ol ul {{ margin: 0.18em 0; }}

blockquote {{
  margin: 1.1em 0;
  padding-inline-start: 1.1em;
  border-inline-start: 1.5pt solid var(--rule-strong);
  color: var(--ink-2);
  font-size: 0.95em;
  orphans: 2;
  widows: 2;
}}
blockquote p:last-child {{ margin-bottom: 0; }}

code {{
  font-family: var(--mono);
  font-size: 0.86em;
  direction: ltr;
  unicode-bidi: isolate;
}}
pre {{
  font-family: var(--mono);
  font-size: 0.84em;
  line-height: 1.5;
  direction: ltr;
  unicode-bidi: plaintext;
  text-align: left;
  background: {code_bg};
  border: 0.5pt solid var(--rule);
  border-radius: 2pt;
  padding: 0.8em 1em;
  margin: 1.1em 0;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  break-inside: avoid;
}}
pre code {{ font-size: inherit; background: none; padding: 0; }}

/* Tables are a register of their own: type a step smaller than the prose,
   figures in tabular lining numerals aligned on the right, and rules only
   where they carry meaning -- under the column heads, above a total, a double
   rule under the final line. tables.py classifies each Markdown table:
   `numeric` tables draw no rule between ordinary rows (the eye reads down a
   column of figures without help), `text` tables keep a hairline between rows
   (long cells need it). A long table BREAKS across pages and repeats its head;
   what must not break is a row, and a total must not be stranded from the
   lines it sums. */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 0.9em 0 1.4em;
  font-size: var(--table-size);
  line-height: 1.35;
  break-inside: auto;
}}
table.keep {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}
tfoot {{ display: table-footer-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
thead tr {{ break-after: avoid; }}
tbody tr:first-child {{ break-before: avoid; }}
tr.tot, tr.fin, tr.gtot {{ break-before: avoid; }}
th, td {{
  padding: 0.3em 0 0.3em 0.9em;
  text-align: start;
  vertical-align: top;
  border: none;
}}
th {{
  font-family: var(--label);
  font-weight: var(--w-label);
  font-size: 0.82em;
  letter-spacing: {track_micro};
  text-transform: uppercase;
  color: var(--ink-3);
  vertical-align: bottom;
  padding-bottom: 0.5em;
  border-bottom: 0.8pt solid var(--ink);
}}
th:first-child, td:first-child {{ padding-inline-start: 0; }}
th:last-child, td:last-child {{ padding-inline-end: 0; }}
td.num, th.num {{
  text-align: right;
  font-variant-numeric: tabular-nums lining-nums;
}}
td.num {{ white-space: nowrap; }}
table.numeric td.num {{ white-space: normal; }}
table.numeric th:first-child, table.numeric td:first-child {{ min-width: 11em; }}
/* text register: a hairline between rows, a firmer rule to close */
td {{ border-bottom: 0.5pt solid var(--rule); }}
tbody tr:last-child td {{ border-bottom: 0.8pt solid var(--rule-strong); }}
/* numeric and statement registers: no rules between ordinary rows */
table.numeric td, table.fs td {{ border-bottom: none; }}
table.numeric tbody tr:last-child td, table.fs tbody tr:last-child td {{ border-bottom: none; }}
/* totals */
tr.tot td, tr.key td, tr.fin td {{
  font-weight: var(--w-emphasis);
  padding-top: 0.38em;
  padding-bottom: 0.38em;
}}
tr.tot td.num, tr.key td.num, tr.fin td.num,
tr.tot td:first-child, tr.key td:first-child, tr.fin td:first-child {{ border-top: 0.8pt solid var(--ink); }}
tr.fin td.num, tr.fin td:first-child {{ border-bottom: 2.4pt double var(--ink); }}
/* statements (statements.py): sections, groups, indented items, sub-totals */
table.fs {{ font-size: {statement_size}em; line-height: 1.3; }}
table.fs th, table.fs td {{ padding-top: 0.17em; padding-bottom: 0.17em; vertical-align: baseline; }}
table.fs th {{ padding-bottom: 0.5em; }}
table.fs tr.sec td {{
  padding-top: 1em; padding-bottom: 0.25em;
  font-family: var(--label); font-weight: var(--w-label); font-size: 0.85em;
  letter-spacing: {track_micro}; text-transform: uppercase; color: var(--ink-2);
}}
table.fs tr.grp td {{ padding-top: 0.5em; }}
table.fs tr.memo td {{ color: var(--ink-3); font-style: italic; }}
table.fs tr.d1 td:first-child {{ padding-inline-start: 1.4em; }}
table.fs tr.d2 td:first-child {{ padding-inline-start: 2.8em; }}
table.fs tr.d3 td:first-child {{ padding-inline-start: 4.2em; }}
table.fs tr.gtot td {{ padding-bottom: 0.35em; }}
table.fs tr.gtot td.num {{ border-top: 0.5pt solid var(--rule-strong); }}
table.fs tr.tot td, table.fs tr.key td, table.fs tr.fin td {{ padding-top: 0.32em; padding-bottom: 0.32em; }}
table.fs tr.tot td:first-child, table.fs tr.key td:first-child {{ border-top: none; }}
table.fs tr.fin td:first-child {{ border-top: none; border-bottom: none; }}
table.fs.kf {{ width: 72%; break-inside: avoid; }}

hr {{
  border: none;
  border-top: 0.5pt solid var(--rule);
  margin: 2em 0;
}}

img {{ max-width: 100%; }}
figure {{ margin: 1.2em 0; break-inside: avoid; }}
figcaption {{ font-size: var(--s-small); color: var(--ink-3); margin-top: 0.4em; }}

/* --- stationery --- */
.mark {{ color: var(--ink); }}
.mark svg {{ width: 100%; height: auto; display: block; }}
.wordmark {{
  font-family: var(--display);
  font-size: var(--s-h3);
  font-weight: var(--w-heading);
  letter-spacing: 0.01em;
  width: auto;
}}
.tagline {{
  font-family: var(--label);
  font-size: var(--s-small);
  color: var(--ink-3);
  margin-top: 0.35em;
}}
.contact {{
  font-family: var(--label);
  font-size: var(--s-micro);
  color: var(--ink-3);
  letter-spacing: 0.02em;
}}
.contact .sep {{ padding: 0 0.6em; color: var(--rule-strong); }}

.cover {{
  break-after: page;
  page-break-after: always;
  height: {cover_h}mm;
  display: flex;
  flex-direction: column;
}}
.cover-top {{ flex: 0 0 auto; }}
.cover-title {{ flex: 1 1 auto; display: flex; flex-direction: column;
  justify-content: flex-end; padding-bottom: 6mm; }}
.cover-foot {{ flex: 0 0 auto; display: flex; justify-content: space-between;
  align-items: baseline; border-top: 0.5pt solid var(--rule); padding-top: 3mm; }}
.eyebrow {{
  font-family: var(--label);
  font-size: var(--s-label);
  font-weight: var(--w-label);
  letter-spacing: {track_eyebrow};
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 1.1em;
}}
.display {{
  font-family: var(--display);
  font-size: var(--s-display);
  font-weight: var(--w-display);
  line-height: 1.12;
  letter-spacing: {tracking};
  margin: 0;
  border: none;
  padding: 0;
}}
.subtitle {{
  font-size: var(--s-h2);
  font-weight: 400;
  line-height: 1.35;
  color: var(--ink-2);
  margin: 0.55em 0 0;
  max-width: 34em;
}}
.cover-rule {{ border-top: 1pt solid var(--accent); margin: 8mm 0 0; }}
.cover-rule.short {{ width: 22mm; }}
.cover-rule.full {{ width: 100%; border-top-color: var(--rule-strong); }}
.meta {{
  margin: 7mm 0 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3.5mm 10mm;
  max-width: 120mm;
}}
.meta .row {{ break-inside: avoid; }}
.meta dt {{
  font-family: var(--label);
  font-size: var(--s-micro);
  font-weight: var(--w-label);
  letter-spacing: {track_label};
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 0.25em;
}}
.meta dd {{ margin: 0; font-size: var(--s-small); color: var(--ink); }}
.classification {{
  font-family: var(--label);
  font-size: var(--s-micro);
  font-weight: var(--w-label);
  letter-spacing: {track_label};
  text-transform: uppercase;
  color: var(--accent);
}}

.letterhead {{ margin-bottom: 10mm; }}
.lh-top {{ display: flex; justify-content: space-between; align-items: flex-start;
  gap: 10mm; }}
.lh-refs, .lh-address {{ margin: 0; font-size: var(--s-small); }}
.lh-refs > div, .lh-address > div {{ display: flex; gap: 0.6em; margin-bottom: 0.2em; }}
.lh-refs dt, .lh-address dt {{
  font-family: var(--label);
  font-size: var(--s-micro);
  font-weight: var(--w-label);
  letter-spacing: {track_micro};
  text-transform: uppercase;
  color: var(--ink-3);
  min-width: 6.5em;
}}
.lh-refs dd, .lh-address dd {{ margin: 0; }}
.lh-rule {{ border-top: 0.8pt solid var(--rule-strong); margin: 4mm 0 6mm; }}
.lh-address {{ margin-bottom: 6mm; }}
.letter-title {{
  font-family: var(--display);
  font-size: var(--s-title);
  font-weight: var(--w-display);
  line-height: 1.2;
  letter-spacing: {tracking};
  margin: 0 0 1.1em;
}}

@media print {{
  body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
""".format(
        faces="\n".join(f for f in faces if f),
        ink=ink, ink2=ink2, ink3=ink3, rule=rule, rule_strong=rule_strong, accent=accent,
        base=base, lh=theme["line_height"], text_stack=text_stack,
        display_stack=display_stack, label_stack=label_stack, mono_stack=mono_stack,
        w_display=weights["display"], w_heading=weights["heading"],
        w_body=weights["body"], w_emphasis=weights["emphasis"], w_label=weights["label"],
        table_size=theme["table"]["size_em"],
        s_h1=round(base * scale * scale, 2), s_h2=round(base * scale, 2),
        s_h3=round(base * 1.02, 2), s_label=round(base * 0.8, 2),
        s_small=round(base * 0.86, 2), s_micro=round(base * 0.74, 2),
        s_display=round(base * scale * scale * 1.62, 2),
        s_title=round(base * scale * scale * 1.15, 2),
        gap=round(0.62 * mood.get("density", 1.0), 2),
        size=page_size, top=top, right=m_right, bottom=bottom, left=m_left,
        furniture="\n".join(furniture), head_box=head_box, folio_box=folio_box,
        direction=theme["direction"], tracking=mood["tracking_display"],
        rule_pt=mood.get("rule_pt", 0.5), list_style=list_style,
        track_label=track_label, track_eyebrow=track_eyebrow, track_micro=track_micro,
        code_bg=theme_mod.mix_with_white(ink, 0.965),
        cover_h=round(paper_h - top - bottom, 2),
        statement_size=round(theme["table"]["size_em"] * 0.98, 3),
    )
    if deck:
        css += deck_css(theme)
    return css


def deck_css(theme):
    """The slide layer: one 16:9 page per slide, identity in the slide foot."""
    d = theme["deck"]
    m = float(d.get("margin_mm") or 16)
    rtl = theme["direction"] == "rtl"
    track = "0" if rtl else "0.14em"
    return """
/* --- deck --- */
.slide {{
  break-after: page; page-break-after: always;
  height: {h}mm; box-sizing: border-box;
  padding: {m}mm {m}mm {mb}mm;
  display: flex; flex-direction: column;
}}
.slide:last-child {{ break-after: auto; page-break-after: auto; }}
.slide .body {{ flex: 1 1 auto; min-height: 0; }}
.slide h6 {{
  font-family: var(--label); font-size: var(--s-label); font-weight: var(--w-label);
  letter-spacing: {track}; text-transform: uppercase; color: var(--accent);
  margin: 0 0 0.9em;
}}
.slide h1, .slide h2 {{
  font-family: var(--display); font-size: var(--s-h1); font-weight: var(--w-heading);
  line-height: 1.15; letter-spacing: var(--tracking, -0.01em);
  margin: 0 0 0.7em; padding: 0; border: none;
}}
.slide h3 {{ margin: 0.9em 0 0.3em; }}
.slide p, .slide li {{ font-size: 1em; }}
.slide table {{ margin: 0.4em 0 0.8em; }}
.slide .foot {{
  flex: 0 0 auto; display: flex; justify-content: space-between; align-items: baseline;
  font-family: var(--label); font-size: var(--s-micro); color: var(--ink-3);
  border-top: 0.5pt solid var(--rule); padding-top: 3mm; margin-top: 6mm;
  font-variant-numeric: tabular-nums;
}}
.slide.title {{ justify-content: flex-end; }}
.slide.title .body {{ flex: 1 1 auto; display: flex; flex-direction: column; justify-content: flex-end; }}
.slide.title h1 {{ font-size: var(--s-display); font-weight: var(--w-display); letter-spacing: {tracking}; }}
.slide.title .subtitle {{ max-width: none; }}
.slide.title .meta-line {{ margin-top: 1.4em; font-size: var(--s-small); color: var(--ink-2); }}
.slide.title .mark {{ margin-bottom: 12mm; }}
.cols-2, .cols-3, .cols-4 {{ display: grid; gap: 8mm; align-items: start; }}
.cols-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
.cols-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.cols-4 {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
.cols-2 > *, .cols-3 > *, .cols-4 > * {{ min-width: 0; }}
.tile {{ border-top: 0.5pt solid var(--rule-strong); padding-top: 0.6em; }}
.tile p {{ margin: 0.2em 0 0; }}
.label, .tile .k {{
  font-family: var(--label); font-size: var(--s-micro); font-weight: var(--w-label);
  letter-spacing: {track}; text-transform: uppercase; color: var(--ink-3);
}}
.slide .stat, .stat, .tile .v {{
  font-family: var(--display); font-size: var(--s-display); font-weight: var(--w-display);
  line-height: 1.05; letter-spacing: -0.02em; font-variant-numeric: tabular-nums lining-nums;
  margin: 0.15em 0;
}}
.slide .stat small, .stat small, .tile .v small {{ font-size: 0.42em; font-weight: var(--w-body); color: var(--ink-3); margin-inline-start: 0.2em; }}
.note {{ font-size: var(--s-small); color: var(--ink-3); }}
""".format(h=d["height_mm"], m=m, mb=round(m * 0.75, 2), track=track,
           tracking=theme["mood_spec"]["tracking_display"])


def deck_html(theme, body_html, meta, inline_svg=None):
    """Slides from a body split at horizontal rules, plus a title slide from the frontmatter."""
    chunks = [c for c in re.split(r"<hr\s*/?>", body_html) if c.strip()]
    identity = theme.get("name") or ""
    title = meta.get("title") or ""
    classification = meta.get("confidentiality") or theme.get("confidentiality")
    foot_text = " · ".join(_esc(x) for x in (identity, title, classification) if x)

    def foot(n):
        return '<footer class="foot"><span>{}</span><span class="n">{}</span></footer>'.format(
            foot_text, _local(theme, "{:02d}".format(n)))

    slides = []
    n = 0
    if title:
        n += 1
        bits = [_esc(_local(theme, meta[k])) for k in ("prepared_for", "author", "date", "version")
                if meta.get(k)]
        parts = ['<section class="slide title">', '<div class="body">', _mark(theme, inline_svg)]
        eyebrow = meta.get("type") or meta.get("kind")
        if eyebrow and str(eyebrow).lower() != "deck":
            parts.append('<h6>{}</h6>'.format(_esc(eyebrow)))
        parts.append('<h1 class="display">{}</h1>'.format(_esc(title)))
        if meta.get("subtitle"):
            parts.append('<p class="subtitle">{}</p>'.format(_esc(meta["subtitle"])))
        if bits:
            parts.append('<p class="meta-line">{}</p>'.format(" · ".join(bits)))
        parts.append("</div>")
        parts.append(foot(n))
        parts.append("</section>")
        slides.append("".join(parts))
    for chunk in chunks:
        n += 1
        slides.append('<section class="slide"><div class="body">{}</div>{}</section>'.format(chunk, foot(n)))
    return "\n".join(slides)


def build_html(theme, body_html, meta, running_head="", inline_svg=None, offline=False):
    head = ""
    kind = str(meta.get("kind") or meta.get("type") or "").strip().lower()
    deck = kind == "deck"
    if deck:
        body_html = deck_html(theme, body_html, meta, inline_svg)
    elif kind in ("letter", "memo", "memorandum"):
        head = letterhead_html(theme, meta, inline_svg)
    elif theme.get("cover") == "always" or (
            theme.get("cover", "auto") == "auto" and meta.get("title")):
        head = cover_html(theme, meta, inline_svg)

    css = build_css(theme, running_head=running_head, offline=offline, deck=deck)
    author = theme.get("name") or meta.get("author") or ""
    return """<!DOCTYPE html>
<html lang="{lang}" dir="{dir}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="author" content="{author}">
<style>{css}</style>
</head>
<body>
{head}
<main>
{body}
</main>
</body>
</html>
""".format(lang=_esc(theme["language"]), dir=theme["direction"],
           title=_esc(meta.get("title") or running_head or "Document"),
           author=_esc(author), css=css, head=head, body=body_html)
