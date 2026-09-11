#!/usr/bin/env python3
"""Theme model for typeset: the per-project stationery set.

A theme is what makes two projects' PDFs look like two different houses rather
than the same template twice. It carries the identity (name, tagline, contact
line, mark), the ink and the single accent, the typographic pairing implied by
a one-word mood, the page geometry, and the locale (direction, calendar,
digits). Everything has a defensible default, so a theme file may set one field
or twenty.

Nothing here is company-specific: the values come from a JSON file that lives
in the *host* project, never in this repo.
"""
import json
import os
import re
from datetime import date

import fonts as fonts_mod

# --- moods -----------------------------------------------------------------
# A mood maps a tone word onto a typographic register. The pairings follow the
# usual classification-to-tone mapping: garalde/transitional serif reads formal,
# humanist sans reads warm, neo-grotesque reads modern and neutral, and a
# monospaced companion signals technical.
#
# Each mood names FIVE roles, not one family, because a page that sets its title
# and its small print in the same face at two sizes looks converted rather than
# designed:
#
#   persian_display / latin_display  the cover title, the section heads
#   persian / latin                  running text, tables, everything read
#   latin_guest                      Latin *inside* a right-to-left sentence
#   persian_label / latin_label      small tracked labels, table heads, folio
#   mono                             code and identifiers
#
# Each mood also names a WEIGHT SET: display, heading, body, emphasis, label.
# Emphasis is what <strong> renders at, and it is deliberately one step above
# the body rather than bold: on a page whose hierarchy is carried by weight, a
# 700 strong shouts over the headings. A theme may override any weight.
#
# The guest role matters more than it sounds. In a Persian document the Latin
# words are company names and terms embedded mid-sentence; they must match the
# class of the Persian text face and then disappear. A garalde serif spliced
# into a Persian sans sentence draws the eye to "Ltd" instead of the clause, so
# a sans Persian text face takes a sans guest and a naskh takes a serif.
MOODS = {
    "modern": {
        "label": "Modern",
        "fonts": {"persian_display": "estedad", "persian": "vazirmatn",
                  "latin_display": "inter", "latin": "inter",
                  "latin_guest": "inter", "mono": "ibm-plex-mono"},
        "display_weight": 300, "heading_weight": 500, "body_weight": 400,
        "emphasis_weight": 500, "label_weight": 500,
        "tracking_display": "-0.015em", "scale": 1.26, "density": 1.0,
        "rule_pt": 0.5, "cover_rule": "short",
    },
    "formal": {
        "label": "Formal",
        "fonts": {"persian_display": "markazi-text", "persian": "ibm-plex-sans-arabic",
                  "latin_display": "eb-garamond", "latin": "eb-garamond",
                  "latin_guest": "ibm-plex-sans", "mono": "ibm-plex-mono"},
        "display_weight": 400, "heading_weight": 600, "body_weight": 400,
        "emphasis_weight": 600, "label_weight": 500,
        "tracking_display": "0", "scale": 1.2, "density": 1.05,
        "rule_pt": 0.5, "cover_rule": "full",
    },
    "editorial": {
        "label": "Editorial",
        "fonts": {"persian_display": "estedad", "persian": "vazirmatn",
                  "latin_display": "newsreader", "latin": "literata",
                  "latin_guest": "inter", "mono": "ibm-plex-mono"},
        "display_weight": 300, "heading_weight": 600, "body_weight": 400,
        "emphasis_weight": 600, "label_weight": 500,
        "tracking_display": "-0.015em", "scale": 1.33, "density": 1.08,
        "rule_pt": 0.5, "cover_rule": "none",
    },
    "technical": {
        "label": "Technical",
        "fonts": {"persian_display": "vazirmatn", "persian": "vazirmatn",
                  "latin_display": "ibm-plex-sans", "latin": "ibm-plex-sans",
                  "latin_guest": "ibm-plex-sans", "mono": "jetbrains-mono"},
        "display_weight": 300, "heading_weight": 600, "body_weight": 400,
        "emphasis_weight": 600, "label_weight": 500,
        "tracking_display": "-0.01em", "scale": 1.2, "density": 0.94,
        "rule_pt": 0.5, "cover_rule": "full",
    },
    "warm": {
        "label": "Warm",
        "fonts": {"persian_display": "vazirmatn", "persian": "vazirmatn",
                  "latin_display": "fraunces", "latin": "literata",
                  "latin_guest": "inter", "mono": "ibm-plex-mono"},
        "display_weight": 300, "heading_weight": 600, "body_weight": 400,
        "emphasis_weight": 600, "label_weight": 500,
        "tracking_display": "0", "scale": 1.25, "density": 1.05,
        "rule_pt": 0.5, "cover_rule": "short",
    },
    "classic": {
        "label": "Classic",
        "fonts": {"persian_display": "markazi-text", "persian": "noto-naskh-arabic",
                  "latin_display": "cormorant-garamond", "latin": "source-serif-4",
                  "latin_guest": "source-serif-4", "mono": "ibm-plex-mono"},
        "display_weight": 400, "heading_weight": 600, "body_weight": 400,
        "emphasis_weight": 600, "label_weight": 500,
        "tracking_display": "0", "scale": 1.2, "density": 1.08,
        "rule_pt": 0.5, "cover_rule": "full",
    },
}
WEIGHT_ROLES = ("display", "heading", "body", "emphasis", "label")

# Tables are a register of their own: smaller than the prose, numbers in
# tabular figures, rules only where they carry meaning (under the head, above
# a total). `size_em` is the table's type size relative to the body.
DEFAULT_TABLE = {"size_em": 0.86}

# A deck is the same design on a 16:9 page: one slide per page, no cover
# furniture, the identity in a slide foot. Sizes are in mm (13.33 x 7.5 in).
DEFAULT_DECK = {"width_mm": 338.67, "height_mm": 190.5, "margin_mm": 16,
                "base_scale": 1.55}
DEFAULT_MOOD = "modern"

# The type roles a theme may name. `persian`/`latin`/`mono` are the historical
# keys and still mean the text faces; the display and guest roles fall back to
# them when a theme names only the old three.
FONT_ROLES = ("persian_display", "persian", "latin_display", "latin",
              "latin_guest", "persian_label", "latin_label", "mono")

# Per-family typesetting: Arabic-script faces carry their ink far above and
# below the Latin x-height, so they need a larger nominal size and more leading
# than a Latin face at the same nominal size. Naskh (deep descenders, small
# x-height) needs more of both again. These are text sizes -- the size at which
# the face is *read* -- so they stay close to the Latin equivalent rather than
# inflating the document.
SCRIPT_METRICS = {
    "markazi-text": {"size_pt": 13.5, "line_height": 1.95},
    "noto-naskh-arabic": {"size_pt": 12.0, "line_height": 1.85},
    "noto-sans-arabic": {"size_pt": 10.8, "line_height": 1.74},
    "vazirmatn": {"size_pt": 10.6, "line_height": 1.72},
    "estedad": {"size_pt": 10.8, "line_height": 1.74},
    "ibm-plex-sans-arabic": {"size_pt": 10.4, "line_height": 1.7},
    "amiri": {"size_pt": 12.2, "line_height": 1.88},
}
LATIN_METRICS = {"size_pt": 10.5, "line_height": 1.52}

RTL_LANGUAGES = ("fa", "ar", "he", "ur", "ps", "ckb", "sd", "yi")

DEFAULTS = {
    "name": None,
    "legal_name": None,
    "tagline": None,
    "contact": [],
    "website": None,
    "logo": None,
    "logo_width_mm": 16,
    "ink": "#111111",
    "accent": None,             # None => a purely monochrome document
    "mood": DEFAULT_MOOD,
    "fonts": {},                # overrides the mood pairing
    "language": "en",
    "direction": None,          # derived from language
    "calendar": None,           # derived from language
    "digits": None,             # derived from language
    "page": {},
    "base_size_pt": None,
    "line_height": None,
    "weights": {},              # overrides the mood's weight set (display heading body emphasis label)
    "table": {},                # table register: size_em
    "deck": {},                 # 16:9 deck geometry: width_mm height_mm margin_mm base_scale
    "locales": {},              # per-language identity overrides: {"en": {"tagline": ...}, "fa": {...}}
    "cover": "auto",            # auto | always | never
    "running_header": True,
    "page_numbers": True,
    "footer_note": None,
    "confidentiality": None,
}

# Named paper in millimetres, for the layout maths that needs a real page and
# not just a CSS keyword: the cover is set to exactly one page tall, so it has
# to know how tall the page actually is.
PAPER_MM = {
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
}


def page_mm(size):
    """(width, height) in mm for a CSS page size, or None if not derivable."""
    key = str(size or "").strip().lower()
    if key in PAPER_MM:
        return PAPER_MM[key]
    # A theme (or the deck geometry) may state the pair outright.
    match = re.match(r"^([\d.]+)mm\s+([\d.]+)mm$", key)
    if match:
        return (float(match.group(1)), float(match.group(2)))
    return None


# The paper the CLI will name. A theme file may put any CSS page size in
# `page.size` (a keyword, or an explicit "210mm 297mm"), which is passed through
# untouched; these are only the two the `--page-size` flag accepts.
PAGE_SIZES = ("letter", "a4")

DEFAULT_PAGE = {
    # Letter, not A4: these documents are printed on North American office and
    # home printers, where A4 is the paper that is not in the tray. Letter is
    # 18 mm shorter and 6 mm wider, so a page laid out for A4 pushes its last
    # lines past the bottom edge here. Documents printed outside North America ask
    # for the other paper explicitly -- `--page-size a4`, or `page.size` in the
    # project's theme.
    "size": "letter",
    # The margins ARE the measure: prose fills the text block rather than being
    # capped again inside it. Two levers fighting each other is what leaves one
    # side of a page conspicuously empty -- a generous outer margin plus a
    # separate line-length cap subtract twice from the same edge. A business
    # document is also read single-sided on a screen, so the near-symmetry of a
    # letter is right where a bound book would want an asymmetric spread.
    "margin_top_mm": 24,
    "margin_bottom_mm": 28,
    "margin_inner_mm": 30,
    "margin_outer_mm": 30,
}

THEME_FILENAMES = (
    ".claude/pdf-theme.json",
    ".pdf-theme.json",
    "docs/pdf-theme.json",
)

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# --- colour ----------------------------------------------------------------
def _hex_to_rgb(value):
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def _luminance(rgb):
    def chan(c):
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_on_white(value):
    """WCAG contrast ratio of a colour against white."""
    return 1.05 / (_luminance(_hex_to_rgb(value)) + 0.05)


def print_accent(value, target=4.5):
    """Darken a brand colour until it is safe as small print on white.

    A brand's screen colour is usually too light to carry a hairline rule or a
    folio on paper. Scaling it toward black keeps the hue and reaches the
    contrast floor; the original stays available for the mark itself.
    """
    if not value or not _HEX_RE.match(value):
        return None
    rgb = _hex_to_rgb(value)
    for step in range(0, 101):
        factor = 1.0 - step / 100.0
        candidate = tuple(c * factor for c in rgb)
        if 1.05 / (_luminance(candidate) + 0.05) >= target:
            return _rgb_to_hex(candidate)
    return "#000000"


def mix_with_white(value, amount):
    """Blend a colour toward white by `amount` (0..1) -- for faint rules and washes."""
    r, g, b = _hex_to_rgb(value)
    return _rgb_to_hex((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))


# --- digits & dates --------------------------------------------------------
# Persian-Indic digits U+06F0-06F9, the Arabic decimal separator U+066B and the
# Arabic thousands separator U+066C. Written as escapes so this file stays ASCII.
PERSIAN_DIGITS = "".join(chr(0x06F0 + i) for i in range(10))
PERSIAN_DECIMAL = "\u066b"
PERSIAN_THOUSANDS = "\u066c"

# Solar Hijri month names, as escapes for the same reason.
JALALI_MONTHS = tuple(
    "".join(chr(c) for c in cps)
    for cps in (
        (0x0641, 0x0631, 0x0648, 0x0631, 0x062F, 0x06CC, 0x0646),
        (0x0627, 0x0631, 0x062F, 0x06CC, 0x0628, 0x0647, 0x0634, 0x062A),
        (0x062E, 0x0631, 0x062F, 0x0627, 0x062F),
        (0x062A, 0x06CC, 0x0631),
        (0x0645, 0x0631, 0x062F, 0x0627, 0x062F),
        (0x0634, 0x0647, 0x0631, 0x06CC, 0x0648, 0x0631),
        (0x0645, 0x0647, 0x0631),
        (0x0622, 0x0628, 0x0627, 0x0646),
        (0x0622, 0x0630, 0x0631),
        (0x062F, 0x06CC),
        (0x0628, 0x0647, 0x0645, 0x0646),
        (0x0627, 0x0633, 0x0641, 0x0646, 0x062F),
    )
)

# A token that must keep ASCII digits: anything carrying Latin letters or the
# shape of a URL, path, email, version or identifier.
LATIN_CONTEXT_RE = re.compile(r"[A-Za-z]|://|[@/\\]")


def to_persian_digits(text):
    """ASCII digits to Persian, with the Persian decimal/thousands separators.

    Separators are converted only between two digits, so a full stop ending a
    sentence survives. Whole tokens carrying Latin letters, a scheme, a slash or
    an at-sign keep ASCII digits: version strings, URLs, paths, emails and
    identifiers are Latin context and must read as such.
    """
    def convert(chunk):
        out = []
        for i, ch in enumerate(chunk):
            if ch in "0123456789":
                out.append(PERSIAN_DIGITS[int(ch)])
            elif ch in ".," and 0 < i < len(chunk) - 1 \
                    and chunk[i - 1] in "0123456789" and chunk[i + 1] in "0123456789":
                out.append(PERSIAN_DECIMAL if ch == "." else PERSIAN_THOUSANDS)
            else:
                out.append(ch)
        return "".join(out)

    return "".join(
        token if LATIN_CONTEXT_RE.search(token) else convert(token)
        for token in re.split(r"(\S+)", text)
    )



def to_jalali(g_year, g_month, g_day):
    """Gregorian to Solar Hijri (Jalali), via the day-count algorithm."""
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy, gm, gd = g_year - 1600, g_month - 1, g_day - 1
    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    g_day_no += g_d_m[gm] + gd
    if gm > 1 and ((gy + 1600) % 4 == 0 and (gy + 1600) % 100 != 0
                   or (gy + 1600) % 400 == 0):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np, j_day_no = j_day_no // 12053, j_day_no % 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    for i in range(11):
        span = 31 if i < 6 else 30
        if j_day_no < span:
            return jy, i + 1, j_day_no + 1
        j_day_no -= span
    return jy, 12, j_day_no + 1


def format_date(when=None, calendar="gregorian", digits="latin", style="long"):
    """A document date in the theme's calendar and digit system."""
    when = when or date.today()
    if calendar == "jalali":
        jy, jm, jd = to_jalali(when.year, when.month, when.day)
        text = "{} {} {}".format(jd, JALALI_MONTHS[jm - 1], jy) if style == "long" \
            else "{}/{:02d}/{:02d}".format(jy, jm, jd)
    else:
        text = when.strftime("%-d %B %Y") if style == "long" else when.strftime("%Y-%m-%d")
    return to_persian_digits(text) if digits == "persian" else text


# --- theme assembly --------------------------------------------------------
def find_theme_file(start_dir):
    """Walk up from a directory looking for a project's theme file."""
    here = os.path.abspath(start_dir)
    while True:
        for rel in THEME_FILENAMES:
            candidate = os.path.join(here, rel)
            if os.path.isfile(candidate):
                return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def load_theme_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("theme file must contain a JSON object")
    return data


def resolve(raw=None, overrides=None):
    """Merge a raw theme dict over the defaults and derive everything implied.

    Returns a fully populated theme: every field the renderer reads is present,
    and locale-dependent fields (direction, calendar, digits, type sizes) are
    filled in from the language unless explicitly set.
    """
    theme = {}
    for key, value in DEFAULTS.items():
        theme[key] = list(value) if isinstance(value, list) else \
            dict(value) if isinstance(value, dict) else value
    for source in (raw or {}, overrides or {}):
        for key, value in source.items():
            if value is None:
                continue
            if key in ("fonts", "page", "weights", "table", "deck", "locales") and isinstance(value, dict):
                theme[key] = dict(theme.get(key) or {})
                theme[key].update(value)
            else:
                theme[key] = value

    # Per-language layer: a theme may carry a second identity (tagline, contact
    # line, classification) and a second typographic register (mood, fonts,
    # weights, table size) for documents written in another language, and let
    # the document's own language pick. A project that writes formal Persian
    # and light, modern English keeps both in one file.
    lang_key = str(theme.get("language") or "en").lower()
    locales = theme.get("locales") or {}
    for candidate in (lang_key, lang_key.split("-")[0]):
        local = locales.get(candidate)
        if isinstance(local, dict):
            for key, value in local.items():
                if value is None:
                    continue
                if key in ("fonts", "weights", "table", "page") and isinstance(value, dict):
                    theme[key] = dict(theme.get(key) or {})
                    theme[key].update(value)
                elif key in ("name", "legal_name", "tagline", "contact", "website",
                             "confidentiality", "footer_note", "mood", "base_size_pt",
                             "line_height", "ink", "accent"):
                    theme[key] = value
            break

    mood_key = str(theme.get("mood") or DEFAULT_MOOD).lower()
    mood = MOODS.get(mood_key) or MOODS[DEFAULT_MOOD]
    theme["mood"] = mood_key if mood_key in MOODS else DEFAULT_MOOD
    theme["mood_spec"] = mood

    # The weight set: the mood's, with any role the theme overrides. Values are
    # clamped to the variable-font range so a typo cannot ask for weight 5000.
    weights = {role: mood["{}_weight".format(role)] for role in WEIGHT_ROLES}
    for role, value in (theme.get("weights") or {}).items():
        if role in weights:
            try:
                weights[role] = max(100, min(900, int(value)))
            except (TypeError, ValueError):
                pass
    theme["weights"] = weights

    table = dict(DEFAULT_TABLE)
    table.update({k: v for k, v in (theme.get("table") or {}).items() if v is not None})
    try:
        table["size_em"] = max(0.6, min(1.0, float(table["size_em"])))
    except (TypeError, ValueError):
        table["size_em"] = DEFAULT_TABLE["size_em"]
    theme["table"] = table

    deck = dict(DEFAULT_DECK)
    deck.update({k: v for k, v in (theme.get("deck") or {}).items() if v is not None})
    theme["deck"] = deck

    lang = str(theme.get("language") or "en").lower()
    theme["language"] = lang
    base_lang = lang.split("-")[0]
    if not theme.get("direction"):
        theme["direction"] = "rtl" if base_lang in RTL_LANGUAGES else "ltr"
    if not theme.get("calendar"):
        theme["calendar"] = "jalali" if base_lang == "fa" else "gregorian"
    if not theme.get("digits"):
        theme["digits"] = "persian" if base_lang == "fa" else "latin"

    user_fonts = {k: v for k, v in (theme.get("fonts") or {}).items() if v}
    roles = dict(mood["fonts"])
    roles.update(user_fonts)
    # A theme naming only persian/latin/mono still gets the newer roles.
    if not roles.get("persian_display"):
        roles["persian_display"] = roles.get("persian")
    if not roles.get("latin_display"):
        roles["latin_display"] = roles.get("latin")
    if not roles.get("latin_guest"):
        roles["latin_guest"] = roles.get("latin")
    # Labels and folios are set small and tracked, where a naskh or a garalde
    # muddies. They take the face with the largest x-height and the most
    # complete numeral and separator set -- which is the family already loaded
    # to supply the Arabic separators, so the label role costs no extra font.
    if not roles.get("persian_label"):
        roles["persian_label"] = fonts_mod.SEPARATOR_SOURCE
    if not roles.get("latin_label"):
        roles["latin_label"] = roles.get("latin_guest") or roles.get("latin")
    # Right-to-left: the Latin is a guest inside Persian sentences. Unless the
    # theme insisted on a Latin text face, take the mood's guest face -- chosen
    # to match the class of the Persian text face and then get out of the way.
    if theme["direction"] == "rtl" and "latin" not in user_fonts:
        roles["latin"] = roles.get("latin_guest") or roles.get("latin")
    # A display-only face may head a page; it may never set body copy.
    corrections = []
    for role in ("persian", "latin", "latin_guest",
                 "persian_label", "latin_label"):
        wanted = roles.get(role)
        safe = fonts_mod.text_safe(wanted) if wanted else None
        if safe and safe != wanted:
            corrections.append((role, wanted, safe))
            roles[role] = safe
    theme["fonts"] = roles
    theme["font_corrections"] = corrections

    page = dict(DEFAULT_PAGE)
    page.update(theme.get("page") or {})
    theme["page"] = page

    rtl = theme["direction"] == "rtl"
    metrics = SCRIPT_METRICS.get(roles.get("persian"), LATIN_METRICS) if rtl else LATIN_METRICS
    density = mood.get("density", 1.0)
    if not theme.get("base_size_pt"):
        theme["base_size_pt"] = round(metrics["size_pt"] * (0.5 + density / 2.0), 2)
    if not theme.get("line_height"):
        theme["line_height"] = metrics["line_height"]

    ink = theme.get("ink") or "#111111"
    theme["ink"] = ink if _HEX_RE.match(str(ink)) else "#111111"
    accent_raw = theme.get("accent")
    theme["accent_raw"] = accent_raw if accent_raw and _HEX_RE.match(str(accent_raw)) else None
    # A monochrome document is the default: with no brand colour the accent is
    # simply the ink, so nothing on the page is coloured for its own sake.
    theme["accent"] = print_accent(theme["accent_raw"]) or theme["ink"]
    theme["monochrome"] = theme["accent_raw"] is None

    if isinstance(theme.get("contact"), str):
        theme["contact"] = [theme["contact"]]
    theme["contact"] = [str(c) for c in (theme.get("contact") or []) if c]
    return theme


def describe(theme):
    """A short human summary of a resolved theme, for confirming before render."""
    mood = theme["mood_spec"]
    faces = theme["fonts"]
    rtl = theme["direction"] == "rtl"
    lines = [
        "identity   {}".format(theme.get("name") or "(unnamed)"),
        "mood       {} ({})".format(mood["label"], theme["mood"]),
        "display    persian={} latin={}".format(
            faces.get("persian_display"), faces.get("latin_display")),
        "text       persian={} latin={}{} mono={}".format(
            faces.get("persian"), faces.get("latin"),
            " (guest)" if rtl else "", faces.get("mono")),
        "labels     persian={} latin={}".format(
            faces.get("persian_label"), faces.get("latin_label")),
        "size       {} pt / {} leading; tables at {}em".format(
            theme["base_size_pt"], theme["line_height"], theme["table"]["size_em"]),
        "paper      {}  margins {}/{}/{}/{} mm (top/bottom/inner/outer)".format(
            theme["page"]["size"], theme["page"]["margin_top_mm"],
            theme["page"]["margin_bottom_mm"], theme["page"]["margin_inner_mm"],
            theme["page"]["margin_outer_mm"]),
        "weights    display {} heading {} body {} emphasis {} label {}".format(
            *(theme["weights"][r] for r in WEIGHT_ROLES)),
        "locale     {} {} {} digits, {} calendar".format(
            theme["language"], theme["direction"], theme["digits"], theme["calendar"]),
        "ink        {}{}".format(
            theme["ink"],
            "  (monochrome)" if theme["monochrome"]
            else "  accent {} -> {} for print".format(theme["accent_raw"], theme["accent"])),
    ]
    for role, wanted, safe in theme.get("font_corrections") or []:
        lines.append("note       {} is display-only; {} set to {} for text".format(
            wanted, role, safe))
    return "\n".join(lines)
