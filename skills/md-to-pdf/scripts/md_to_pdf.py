#!/usr/bin/env python3
"""
Convert Persian/Farsi (or any RTL) markdown to a print-ready RTL PDF using the
Vazirmatn font, via headless Chrome.

Usage:
    python3 md_to_pdf.py <input.md> <output.pdf>

Requires:
    - Python 3 with the `markdown` package (pip install markdown)
    - Google Chrome / Chromium (headless, for HTML -> PDF)
    - Network access on first run only: the three Vazirmatn woff2 weights are
      downloaded once into ~/.cache/yar/md-to-pdf/fonts/ and reused thereafter.
      Offline with an empty cache degrades gracefully to system fonts
      (SF Arabic / Geeza Pro / Tahoma) — the PDF still renders.

No fonts are bundled in the repo (binary-free); they are fetched on demand from
the canonical Vazirmatn release on jsDelivr.
"""
import sys
import subprocess
import tempfile
import base64
import urllib.request
import urllib.error
from pathlib import Path

try:
    import markdown
except ImportError:
    print("ERROR: install with: pip3 install markdown", file=sys.stderr)
    sys.exit(1)

# Pinned to a specific Vazirmatn release for reproducible output.
FONT_TAG = "v33.003"
FONT_BASE = f"https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@{FONT_TAG}/fonts/webfonts"
FONT_FILES = ("Vazirmatn-Regular.woff2", "Vazirmatn-Medium.woff2", "Vazirmatn-Bold.woff2")
CACHE_DIR = Path.home() / ".cache" / "yar" / "md-to-pdf" / "fonts"


def ensure_font(filename):
    """Return the cached path to a font, downloading it on first use.

    Returns None (and warns) if the font is neither cached nor downloadable, so
    the caller can fall back to system fonts rather than fail the whole render.
    """
    dest = CACHE_DIR / filename
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{FONT_BASE}/{filename}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
        if data:
            dest.write_bytes(data)
            return dest
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(
            f"WARNING: could not fetch {filename} ({exc}); falling back to system fonts",
            file=sys.stderr,
        )
    return None


def font_data_uri(filename: str) -> str:
    """Return a base64 data: URI for a font file (so the HTML is self-contained)."""
    path = ensure_font(filename)
    if not path:
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:font/woff2;base64,{data}"


def build_css() -> str:
    regular = font_data_uri("Vazirmatn-Regular.woff2")
    medium = font_data_uri("Vazirmatn-Medium.woff2")
    bold = font_data_uri("Vazirmatn-Bold.woff2")

    return f"""
@font-face {{
    font-family: 'Vazirmatn';
    src: url('{regular}') format('woff2');
    font-weight: 400;
    font-style: normal;
    font-display: swap;
}}
@font-face {{
    font-family: 'Vazirmatn';
    src: url('{medium}') format('woff2');
    font-weight: 500;
    font-style: normal;
    font-display: swap;
}}
@font-face {{
    font-family: 'Vazirmatn';
    src: url('{bold}') format('woff2');
    font-weight: 700;
    font-style: normal;
    font-display: swap;
}}

@page {{
    size: A4;
    margin: 18mm 18mm 20mm 18mm;
}}

html, body {{
    direction: rtl;
    text-align: right;
    font-family: 'Vazirmatn', 'SF Arabic', 'Geeza Pro', 'Tahoma', sans-serif;
    font-size: 10.5pt;
    line-height: 1.7;
    color: #1a202c;
    margin: 0;
    padding: 0;
}}

h1 {{
    font-size: 18pt;
    font-weight: 700;
    color: #0b3a5b;
    border-bottom: 2px solid #0b3a5b;
    padding-bottom: 8px;
    margin: 0 0 16px 0;
}}

h2 {{
    font-size: 13pt;
    font-weight: 700;
    color: #0b3a5b;
    margin: 20px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid #cbd5e0;
    page-break-after: avoid;
}}

h3 {{
    font-size: 11.5pt;
    font-weight: 700;
    color: #2d3748;
    margin: 14px 0 6px 0;
    page-break-after: avoid;
}}

h4 {{
    font-size: 11pt;
    font-weight: 500;
    color: #4a5568;
    margin: 10px 0 4px 0;
}}

p {{
    margin: 6px 0;
}}

ul, ol {{
    margin: 6px 0;
    padding-right: 22px;
    padding-left: 0;
}}

li {{
    margin: 3px 0;
}}

strong, b {{
    font-weight: 700;
    color: #0b3a5b;
}}

em, i {{
    font-style: italic;
}}

code {{
    font-family: 'Menlo', 'Consolas', monospace;
    font-size: 9.5pt;
    background: #f1f5f9;
    padding: 1px 5px;
    border-radius: 3px;
    direction: ltr;
    unicode-bidi: embed;
}}

pre {{
    background: #f1f5f9;
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 9.5pt;
    direction: ltr;
    text-align: left;
    page-break-inside: avoid;
}}

blockquote {{
    border-right: 3px solid #4299e1;
    border-left: none;
    padding: 8px 14px;
    margin: 10px 0;
    background: #ebf8ff;
    color: #2c5282;
    font-size: 10pt;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 10pt;
    direction: rtl;
    page-break-inside: avoid;
}}

th, td {{
    border: 1px solid #cbd5e0;
    padding: 6px 9px;
    text-align: right;
    vertical-align: top;
}}

th {{
    background: #edf2f7;
    font-weight: 700;
    color: #2d3748;
}}

tr:nth-child(even) td {{
    background: #f7fafc;
}}

a {{
    color: #2b6cb0;
    text-decoration: none;
}}

hr {{
    border: none;
    border-top: 1px solid #cbd5e0;
    margin: 16px 0;
}}

.frontmatter {{
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 8.5pt;
    color: #718096;
    margin-bottom: 16px;
    direction: ltr;
    font-family: 'Menlo', monospace;
    white-space: pre-wrap;
}}

ul, ol, blockquote {{
    page-break-inside: avoid;
}}

@media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
"""


def strip_frontmatter(text: str):
    """Extract YAML frontmatter (if present) and return (frontmatter, body)."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[4:end], text[end + 5:]
    return None, text


def find_chrome():
    """Locate a Chrome/Chromium binary across common macOS + PATH locations."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    from shutil import which
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = which(name)
        if found:
            return found
    return None


def main():
    if len(sys.argv) != 3:
        print("Usage: md_to_pdf.py <input.md> <output.pdf>", file=sys.stderr)
        sys.exit(1)

    md_path = Path(sys.argv[1]).resolve()
    pdf_path = Path(sys.argv[2]).resolve()

    if not md_path.exists():
        print(f"ERROR: input not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    chrome = find_chrome()
    if not chrome:
        print(
            "ERROR: Google Chrome / Chromium not found (needed for HTML->PDF).",
            file=sys.stderr,
        )
        sys.exit(1)

    md_text = md_path.read_text(encoding="utf-8")
    fm, body = strip_frontmatter(md_text)

    md = markdown.Markdown(extensions=["tables", "fenced_code", "attr_list", "nl2br"])
    html_body = md.convert(body)

    fm_html = ""
    if fm:
        fm_html = f'<div class="frontmatter">{fm}</div>'

    html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{md_path.stem}</title>
<style>{build_css()}</style>
</head>
<body>
{fm_html}
{html_body}
</body>
</html>
"""

    # Write HTML to a temp file (Chrome headless reads from file://)
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        html_path = f.name
        f.write(html)

    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        f"file://{html_path}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Chrome headless error:", result.stderr, file=sys.stderr)
        sys.exit(1)

    Path(html_path).unlink(missing_ok=True)
    print(f"PDF created: {pdf_path}")


if __name__ == "__main__":
    main()
