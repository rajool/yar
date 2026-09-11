#!/usr/bin/env python3
"""Font catalog, on-demand fetching, and @font-face generation for typeset.

Every family is an open-licence (SIL OFL) variable font served from a *pinned*
Fontsource release on jsDelivr, so a given theme renders identically on every
machine. Files are cached under ~/.cache/yar/typeset/fonts/ and never
committed -- the repo stays binary-free.

The interesting part is mixed-script composition. In a right-to-left document
the Persian family is primary and owns digits, punctuation, spaces and the
zero-width non-joiner; the Latin family is layered on top with a unicode-range
restricted to *letters only*, plus a size-adjust that matches its x-height to
the Persian family's own Latin. That keeps one digit design per document and
stops a fallback from splitting an Arabic shaping run.

Families carry a role: a face may be fit for running text, for display sizes,
or for both. A document therefore composes a *pair* per script -- a display
face for the title and the section heads, a text face for everything that is
actually read -- which is what makes a page look designed rather than
converted. `TEXT_UNSAFE` names the faces that must never set body copy: low
x-height naskh and high-contrast garaldes look immaculate at 30pt and spidery
at 11pt.
"""
import base64
import sys
import urllib.error
import urllib.request
from pathlib import Path

FONTSOURCE_VERSION = "5.3.0"
CACHE_DIR = Path.home() / ".cache" / "yar" / "typeset" / "fonts"
# The skill was called md-to-pdf before 4.0; a cache filled under the old name
# is adopted rather than downloaded twice.
_LEGACY_CACHE_DIR = Path.home() / ".cache" / "yar" / "md-to-pdf" / "fonts"


def _adopt_legacy_cache():
    if CACHE_DIR.exists() or not _LEGACY_CACHE_DIR.is_dir():
        return
    try:
        CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
        _LEGACY_CACHE_DIR.rename(CACHE_DIR)
    except OSError:
        pass

# Latin *letters* only: digits, punctuation, spaces and ZWNJ stay with the
# primary (Persian) family so a mixed sentence keeps a single digit design.
RANGE_LATIN_LETTERS = (
    "U+0041-005A, U+0061-007A, U+00C0-024F, U+1E00-1EFF, U+2C60-2C7F, U+A720-A7FF"
)
# The Arabic percent, decimal and thousands separators. Several otherwise
# excellent Persian families omit these, and an unstyled system fallback draws
# them with wide Latin sidebearings -- which is what turns a clean 412,500 into
# a limping "412 , 500". A known-complete family supplies just these three.
RANGE_PERSIAN_SEPARATORS = "U+066A-066C"
SEPARATOR_SOURCE = "vazirmatn"

# Arabic script + ZWNJ/ZWJ + the hyphens Google's Arabic subset claims.
RANGE_ARABIC = (
    "U+0600-06FF, U+0750-077F, U+0870-088E, U+08A0-08FF, U+200C-200E, "
    "U+2010-2011, U+204F, U+2E41, U+FB50-FDFF, U+FE70-FEFF"
)

_VAR = "-variable"


def _url(pkg, filename, variable=True):
    scope = "@fontsource{}".format(_VAR if variable else "")
    return "https://cdn.jsdelivr.net/npm/{}/{}@{}/files/{}".format(
        scope, pkg, FONTSOURCE_VERSION, filename
    )


def _face(pkg, slug, subset, style="normal", variable=True, weight="100 900"):
    """One @font-face source descriptor."""
    fn = "{}-{}-{}-{}.woff2".format(slug, subset, "wght" if variable else weight, style)
    return {"file": fn, "url": _url(pkg, fn, variable), "style": style, "weight": weight}


def _static(pkg, slug, subset, weight):
    fn = "{}-{}-{}-normal.woff2".format(slug, subset, weight)
    return {"file": fn, "url": _url(pkg, fn, False), "style": "normal", "weight": str(weight)}


def _arabic_static(pkg, slug, css, latin_x, note, weights=(400, 700)):
    """An Arabic-script family shipped as separate weights rather than variable."""
    return {
        "css": css,
        "script": "arabic",
        "latin_x": latin_x,
        "note": note,
        "weights": "{} {}".format(weights[0], weights[-1]),
        "faces": [_static(pkg, slug, "arabic", w) for w in weights],
    }


def _arabic(pkg, slug, css, latin_x, note, weights="100 900"):
    return {
        "css": css,
        "script": "arabic",
        "latin_x": latin_x,
        "note": note,
        "weights": weights,
        "faces": [_face(pkg, slug, "arabic", weight=weights)],
    }


def _latin(pkg, slug, css, x_height, note, italic=True, weights="100 900"):
    faces = [_face(pkg, slug, "latin", weight=weights)]
    if italic:
        faces.append(_face(pkg, slug, "latin", style="italic", weight=weights))
    return {
        "css": css,
        "script": "latin",
        "x_height": x_height,
        "note": note,
        "weights": weights,
        "faces": faces,
    }


# --- Persian / Arabic-script families -------------------------------------
# latin_x = x-height of the family's OWN Latin, measured from the pinned file;
# it is the target a paired Latin face is size-adjusted to.
ARABIC_FAMILIES = {
    "vazirmatn": _arabic(
        "vazirmatn", "vazirmatn", "Vazirmatn", 0.53,
        "Modern low-contrast Persian sans, the most complete glyph set -- it alone "
        "carries the Arabic separators. The default text face.",
    ),
    "estedad": _arabic(
        "estedad", "estedad", "Estedad", 0.49,
        "Compact, quiet Persian sans; elegant as a light display face and steady "
        "as text.",
    ),
    "markazi-text": _arabic(
        "markazi-text", "markazi-text", "Markazi Text", 0.36,
        "Contemporary Persian book naskh. Display only: at text sizes its "
        "x-height collapses and the stems go thin.",
        weights="400 700",
    ),
    "noto-naskh-arabic": _arabic(
        "noto-naskh-arabic", "noto-naskh-arabic", "Noto Naskh Arabic", 0.54,
        "Modulated naskh built to sit beside a serif; the robust fallback.",
        weights="400 700",
    ),
    "noto-sans-arabic": _arabic(
        "noto-sans-arabic", "noto-sans-arabic", "Noto Sans Arabic", 0.54,
        "Unmodulated Arabic sans with the widest coverage.",
    ),
    # The formal text register. A geometric Persian sans reads friendly, which
    # is wrong on a contract; these two are the sober alternatives -- one
    # institutional, one classical -- and both are drawn for running text.
    "ibm-plex-sans-arabic": _arabic_static(
        "ibm-plex-sans-arabic", "ibm-plex-sans-arabic", "IBM Plex Sans Arabic", 0.52,
        "Institutional Arabic sans, the companion of IBM Plex Sans. Sober and "
        "corporate rather than friendly: the formal text face.",
        weights=(400, 600, 700),
    ),
    "amiri": _arabic_static(
        "amiri", "amiri", "Amiri", 0.42,
        "Classical naskh revival drawn for body text -- the traditional formal "
        "register. Arabic-first: it mirrors parentheses and draws kaf and heh "
        "the Arabic way, which a Persian reader reads as foreign. Prefer it for "
        "Arabic, not for Persian.",
    ),
}

# --- Latin families --------------------------------------------------------
LATIN_FAMILIES = {
    "inter": _latin("inter", "inter", "Inter Variable", 0.55,
                    "Neutral grotesque; disappears, which is the point."),
    "geist": _latin("geist", "geist", "Geist Variable", 0.53,
                    "Contemporary grotesque, slightly warmer than Inter."),
    "ibm-plex-sans": _latin("ibm-plex-sans", "ibm-plex-sans", "IBM Plex Sans Variable", 0.52,
                            "Engineered humanist sans; the technical register.",
                            weights="100 700"),
    "manrope": _latin("manrope", "manrope", "Manrope Variable", 0.54,
                      "Geometric sans with open counters.", italic=False, weights="200 800"),
    "source-serif-4": _latin("source-serif-4", "source-serif-4", "Source Serif 4 Variable", 0.49,
                             "Transitional serif drawn for screens and print alike.",
                             weights="200 900"),
    "literata": _latin("literata", "literata", "Literata Variable", 0.51,
                       "Sturdy reading serif; comfortable over long documents.",
                       weights="200 900"),
    "newsreader": _latin("newsreader", "newsreader", "Newsreader Variable", 0.44,
                         "Editorial serif with real voice in the display weights.",
                         weights="200 800"),
    "eb-garamond": _latin("eb-garamond", "eb-garamond", "EB Garamond Variable", 0.41,
                          "Old-style garalde; the classical, formal register.",
                          weights="400 800"),
    "cormorant-garamond": _latin("cormorant-garamond", "cormorant-garamond",
                                 "Cormorant Garamond Variable", 0.39,
                                 "High-contrast display garalde. Titles only, never body.",
                                 weights="300 700"),
    "fraunces": _latin("fraunces", "fraunces", "Fraunces Variable", 0.47,
                       "Soft-serif display with character; pairs with a quiet body face.",
                       weights="100 900"),
}

# --- Monospace -------------------------------------------------------------
MONO_FAMILIES = {
    "ibm-plex-mono": {
        "css": "IBM Plex Mono", "script": "mono", "x_height": 0.52,
        "note": "The default code face; calm and unshowy.", "weights": "400 600",
        "faces": [_static("ibm-plex-mono", "ibm-plex-mono", "latin", 400),
                  _static("ibm-plex-mono", "ibm-plex-mono", "latin", 600)],
    },
    "jetbrains-mono": {
        "css": "JetBrains Mono Variable", "script": "mono", "x_height": 0.55,
        "note": "Taller x-height, very legible at small sizes.", "weights": "100 800",
        "faces": [_face("jetbrains-mono", "jetbrains-mono", "latin", weight="100 800")],
    },
    "geist-mono": {
        "css": "Geist Mono Variable", "script": "mono", "x_height": 0.53,
        "note": "Matches Geist; use when Geist is the Latin family.", "weights": "100 900",
        "faces": [_face("geist-mono", "geist-mono", "latin")],
    },
}

FAMILIES = {}
FAMILIES.update(ARABIC_FAMILIES)
FAMILIES.update(LATIN_FAMILIES)
FAMILIES.update(MONO_FAMILIES)

# Faces that are beautiful large and unreadable small: a naskh whose x-height is
# barely a third of its em, and the two high-contrast display garaldes. They may
# set a cover title or a section head; they may never set body copy. A theme that
# names one as its text face is corrected to the safe default for its script.
TEXT_UNSAFE = frozenset(("markazi-text", "cormorant-garamond", "fraunces"))
SAFE_TEXT = {"arabic": "vazirmatn", "latin": "inter", "mono": "ibm-plex-mono"}


def text_safe(family_id):
    """Return family_id if it can set running text, else the safe face for its script."""
    fam = FAMILIES.get(family_id)
    if not fam:
        return None
    if family_id not in TEXT_UNSAFE:
        return family_id
    return SAFE_TEXT.get(fam["script"], SAFE_TEXT["latin"])

# System fallbacks, used verbatim when a download fails so a PDF still renders.
FALLBACK_ARABIC = "'SF Arabic', 'Geeza Pro', 'Tahoma', sans-serif"
FALLBACK_SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"
FALLBACK_SERIF = "Georgia, 'Times New Roman', serif"
FALLBACK_MONO = "'SF Mono', Menlo, Consolas, monospace"


def fallback_for(family_id):
    fam = FAMILIES.get(family_id)
    if not fam:
        return FALLBACK_SANS
    if fam["script"] == "arabic":
        return FALLBACK_ARABIC
    if fam["script"] == "mono":
        return FALLBACK_MONO
    return FALLBACK_SERIF if "Serif" in fam["css"] or "Garamond" in fam["css"] \
        or fam["css"].startswith(("Literata", "Newsreader", "Fraunces")) else FALLBACK_SANS


def size_adjust(latin_id, arabic_id):
    """Percentage that matches a Latin face's x-height to the Persian family's own Latin.

    Returns None when no adjustment is warranted (within 2%), so the descriptor
    is simply omitted rather than emitted as a no-op.
    """
    lat = LATIN_FAMILIES.get(latin_id)
    ara = ARABIC_FAMILIES.get(arabic_id)
    if not lat or not ara:
        return None
    pct = round(ara["latin_x"] / lat["x_height"] * 100, 1)
    pct = max(80.0, min(125.0, pct))
    return None if abs(pct - 100.0) < 2.0 else pct


def fetch(face, offline=False):
    """Return the cached path for one face, downloading it once. None on failure."""
    _adopt_legacy_cache()
    dest = CACHE_DIR / face["file"]
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    if offline:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(face["url"], timeout=25) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("WARNING: could not fetch {} ({}); falling back to system fonts"
              .format(face["file"], exc), file=sys.stderr)
        return None
    if not data:
        return None
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def face_css(family_id, unicode_range=None, adjust=None, offline=False):
    """@font-face rules for one family. Empty string if nothing could be fetched."""
    fam = FAMILIES.get(family_id)
    if not fam:
        return ""
    out = []
    for face in fam["faces"]:
        path = fetch(face, offline=offline)
        if not path:
            continue
        uri = "data:font/woff2;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        rule = [
            "@font-face {",
            "  font-family: '{}';".format(fam["css"]),
            "  src: url({}) format('woff2');".format(uri),
            "  font-weight: {};".format(face["weight"]),
            "  font-style: {};".format(face["style"]),
            "  font-display: block;",
        ]
        if unicode_range:
            rule.append("  unicode-range: {};".format(unicode_range))
        if adjust:
            rule.append("  size-adjust: {}%;".format(adjust))
        rule.append("}")
        out.append("\n".join(rule))
    return "\n".join(out)


def stack(*family_ids):
    """A CSS font-family stack from family ids, ending in a system fallback."""
    names = []
    for fid in family_ids:
        fam = FAMILIES.get(fid)
        if fam:
            names.append("'{}'".format(fam["css"]))
    tail = fallback_for(family_ids[-1]) if family_ids else FALLBACK_SANS
    names.append(tail)
    return ", ".join(names)
