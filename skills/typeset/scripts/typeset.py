#!/usr/bin/env python3
"""Typeset a Markdown file as a designed, print-ready PDF in a project's own house style.

    typeset.py <input.md> <output.pdf> [options]

The look comes from a theme: a small JSON file in the *host* project
(`.claude/pdf-theme.json`) carrying that project's identity, ink, accent, mood,
weights and locale. Without one, a monochrome default applies. Fonts are
pinned, open-licence and fetched once into ~/.cache/yar/typeset/fonts/, so
nothing binary lands in any repo and a second run works offline.

Tables are classified and set in the table register (tables.py); `kind: deck`
sets the document as 16:9 slides, one per page, split at horizontal rules.

Options:
    --theme PATH     use this theme file instead of discovering one
    --mood NAME      override the mood (modern formal editorial technical warm classic)
    --lang CODE      override the document language (drives direction/calendar/digits)
    --accent HEX     override the accent colour
    --kind KIND      report | memo | letter | note | deck (letters get a letterhead, decks 16:9 slides)
    --page-size SIZE letter (default) | a4
    --no-cover       never render a cover page
    --offline        never reach the network; use cached fonts or system fallbacks
    --describe       print the resolved theme and exit without rendering
    --keep-html PATH also write the intermediate HTML (for debugging a layout)
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fonts          # noqa: E402
import render         # noqa: E402
import tables         # noqa: E402
import theme as theme_mod   # noqa: E402

CHROME_TIMEOUT = 90

MD_EXTENSIONS = ["tables", "fenced_code", "attr_list", "sane_lists", "footnotes", "md_in_html"]

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def find_chrome():
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    from shutil import which
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = which(name)
        if found:
            return found
    return None


def split_frontmatter(text):
    """Return (metadata dict, body). A leading YAML block is metadata, not content."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            block = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return parse_frontmatter(block), body
    return {}, text


def parse_frontmatter(block):
    """PyYAML when available, else a single-level key: value parser."""
    try:
        import yaml
        data = yaml.safe_load(block)
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}
    except Exception:
        pass
    data = {}
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", raw)
        if match:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            data[match.group(1)] = value
    return data


H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def lift_title(body):
    """Take the first H1 as the document title and remove it from the body.

    A cover already states the title in display type; repeating it as the first
    heading of page two is the classic generated-PDF tell.
    """
    match = H1_RE.search(body)
    if not match or body[:match.start()].strip():
        return None, body
    return match.group(1).strip(), body[:match.start()] + body[match.end():].lstrip("\n")


def load_logo(theme, base_dir):
    """Inline an SVG mark, or embed a raster one as a data URI.

    Inline SVG stays vector through Chrome's print pipeline; an <img> SVG can be
    rasterised at screen resolution, so it is only used for real rasters.
    """
    ref = theme.get("logo")
    if not ref:
        return None
    path = Path(ref)
    if not path.is_absolute():
        path = Path(base_dir) / ref
    if not path.is_file():
        print("WARNING: logo not found: {}".format(path), file=sys.stderr)
        return None
    if path.suffix.lower() == ".svg":
        svg = path.read_text(encoding="utf-8", errors="replace")
        svg = re.sub(r"<\?xml.*?\?>", "", svg, flags=re.S)
        svg = re.sub(r"<!DOCTYPE.*?>", "", svg, flags=re.S)
        svg = re.sub(r"<svg\b", '<svg preserveAspectRatio="xMinYMid meet"', svg, count=1)
        return svg.strip()
    import base64
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp"}.get(path.suffix.lower())
    if not mime:
        print("WARNING: unsupported logo format: {}".format(path.suffix), file=sys.stderr)
        return None
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return '<img alt="" src="data:{};base64,{}">'.format(mime, data)


def page_count(pdf_path):
    try:
        data = Path(pdf_path).read_bytes()
    except OSError:
        return None
    counts = [int(n) for n in re.findall(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else None


def build_parser():
    parser = argparse.ArgumentParser(
        prog="typeset.py", description="Markdown to a designed, print-ready, themed PDF.")
    parser.add_argument("input", nargs="?", help="the Markdown source")
    parser.add_argument("output", nargs="?", help="the PDF to write")
    parser.add_argument("--theme")
    parser.add_argument("--mood", choices=sorted(theme_mod.MOODS))
    parser.add_argument("--lang")
    parser.add_argument("--accent")
    parser.add_argument("--kind", choices=("report", "memo", "letter", "note", "deck"))
    parser.add_argument("--page-size", type=str.lower, choices=theme_mod.PAGE_SIZES,
                        help="paper size; default letter")
    parser.add_argument("--no-cover", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--keep-html")
    parser.add_argument("--list-moods", action="store_true")
    parser.add_argument("--list-fonts", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_moods:
        for key in sorted(theme_mod.MOODS):
            spec = theme_mod.MOODS[key]
            f = spec["fonts"]
            print("{:<10} {:<10} display {}/{}  text {}/{}  guest {}  mono {}".format(
                key, spec["label"], f["persian_display"], f["latin_display"],
                f["persian"], f["latin"], f["latin_guest"], f["mono"]))
        return 0
    if args.list_fonts:
        for key in sorted(fonts.FAMILIES):
            fam = fonts.FAMILIES[key]
            print("{:<20} {:<8} {}".format(key, fam["script"], fam["note"]))
        return 0

    if not args.input:
        build_parser().print_usage(sys.stderr)
        return 2

    md_path = Path(args.input).resolve()
    if not md_path.is_file():
        print("ERROR: input not found: {}".format(md_path), file=sys.stderr)
        return 1

    theme_path = args.theme or theme_mod.find_theme_file(md_path.parent)
    raw_theme = {}
    if theme_path:
        try:
            raw_theme = theme_mod.load_theme_file(theme_path)
        except (OSError, ValueError) as exc:
            print("ERROR: could not read theme {}: {}".format(theme_path, exc), file=sys.stderr)
            return 1

    md_text = md_path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(md_text)

    overrides = {}
    if args.mood:
        overrides["mood"] = args.mood
    if args.lang:
        overrides["language"] = args.lang
    elif meta.get("lang") or meta.get("language"):
        overrides["language"] = meta.get("lang") or meta.get("language")
    if args.accent:
        overrides["accent"] = args.accent
    if args.no_cover:
        overrides["cover"] = "never"
    if args.page_size:
        # Merged over the theme's own page block, so the margins survive.
        overrides["page"] = {"size": args.page_size}
    if meta.get("mood"):
        overrides.setdefault("mood", meta["mood"])

    theme = theme_mod.resolve(raw_theme, overrides)

    if args.describe:
        print(theme_mod.describe(theme))
        print("theme file {}".format(theme_path or "(none -- defaults)"))
        return 0

    if not args.output:
        print("ERROR: an output path is required", file=sys.stderr)
        return 2
    pdf_path = Path(args.output).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    chrome = find_chrome()
    if not chrome:
        print("ERROR: Google Chrome / Chromium not found (needed for HTML to PDF).",
              file=sys.stderr)
        return 1

    if args.kind:
        meta["kind"] = args.kind
    kind = str(meta.get("kind") or meta.get("type") or "").lower()
    wants_head = kind in ("letter", "memo", "memorandum", "deck") or \
        theme.get("cover") == "always" or theme.get("cover", "auto") == "auto"

    if not meta.get("title") and wants_head:
        lifted, body = lift_title(body)
        if lifted:
            meta["title"] = lifted
    elif meta.get("title"):
        lifted, stripped = lift_title(body)
        if lifted and lifted == meta["title"]:
            body = stripped

    if not meta.get("date") and (meta.get("title") or kind in ("letter", "memo")):
        meta["date"] = theme_mod.format_date(
            date.today(), calendar=theme["calendar"], digits=theme["digits"])

    # Imported here, not at module scope: the pure helpers above are useful
    # (and unit-testable) on a host that has no markdown package installed.
    try:
        import markdown
    except ImportError:
        print("ERROR: the markdown package is required: pip3 install markdown",
              file=sys.stderr)
        return 1

    html_body = markdown.Markdown(extensions=MD_EXTENSIONS).convert(body)
    html_body = tables.restyle(html_body)
    html_body = render.transform(html_body, digits=theme["digits"],
                                 isolate_latin=theme["direction"] == "rtl")

    running_head = meta.get("title") or theme.get("name") or md_path.stem
    inline_svg = load_logo(theme, md_path.parent if not theme_path
                           else Path(theme_path).parent)

    document = render.build_html(theme, html_body, meta, running_head=running_head,
                                 inline_svg=inline_svg, offline=args.offline)

    if args.keep_html:
        Path(args.keep_html).write_text(document, encoding="utf-8")

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w",
                                     encoding="utf-8") as handle:
        html_path = handle.name
        handle.write(document)
    # No --user-data-dir here: headless Chrome writes the PDF but then keeps the
    # named profile alive and never exits. The default ephemeral profile is both
    # cleaner and the only one that terminates.
    cmd = [
        chrome, "--headless", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=10000",
        "--print-to-pdf={}".format(pdf_path),
        "file://{}".format(html_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CHROME_TIMEOUT)
        failed, detail = result.returncode != 0, result.stderr
    except subprocess.TimeoutExpired:
        failed, detail = True, "Chrome did not exit within {}s".format(CHROME_TIMEOUT)
    Path(html_path).unlink(missing_ok=True)

    if failed or not pdf_path.exists():
        print("Chrome headless error:\n{}".format(detail), file=sys.stderr)
        return 1

    pages = page_count(pdf_path)
    print("PDF created: {}".format(pdf_path))
    print("  theme  {}".format(theme_path or "(defaults)"))
    print("  mood   {} / {} / {}".format(
        theme["mood"], theme["fonts"]["latin"], theme["fonts"]["persian"]))
    print("  kind   {}".format(kind or "report"))
    print("  pages  {}".format(pages if pages else "unknown"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
