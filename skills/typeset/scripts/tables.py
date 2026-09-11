#!/usr/bin/env python3
"""Table register for typeset: turn a plain Markdown table into a designed one.

Markdown can say "here is a table" and nothing more. A designed table needs to
know which columns hold numbers (so they align on the right in tabular
figures), which rows are totals (so they carry a rule above and a heavier
weight), whether the table is a numeric statement (no rules between ordinary
rows) or a text table (a hairline between rows, because the eye needs help
across long cells), and whether it is short enough to keep on one page.

`restyle()` infers all of that from the rendered HTML and writes it back as
classes the stylesheet in render.py understands:

    table.numeric | table.text      the register
    table.keep                      short enough to keep whole on a page
    th.num / td.num                 a numeric column (header included)
    tr.tot                          a total row: rule above, emphasis weight
    tr.fin                          the final total: rule above, double rule below
    tr.grp                          a group row (its cells span the table)

Author-supplied classes are preserved, and a table that already declares the
statement register (`class="fs"`, from statements.py) is left alone.
"""
import re
from html.parser import HTMLParser

# Digits with the usual furniture of a figure: separators, signs, brackets for
# negatives, percent, multiplication, ranges, currency codes and symbols.
_STRIP_RE = re.compile(r"<[^>]+>|&nbsp;|\b(?:CAD|USD|EUR|GBP|AUD|CHF|JPY|IRR|AED)\b|[$€£¥]")
_NUMERIC_RE = re.compile(
    "^[\\s\\d.,%+\\-–—()~:/×−*]*$"
)
_DASHES = ("—", "–", "-", "−")
_DIGIT_RE = re.compile("[0-9۰-۹]")
_STRONG_RE = re.compile(r"^\s*<(?:strong|b)\b[^>]*>.*</(?:strong|b)>\s*$", re.S)

KEEP_ROWS = 16          # a table this short is kept whole on a page
TOTAL_SHARE = 0.5       # emphasised rows are totals only when they are the minority


def is_numeric_text(cell_html):
    """True when a cell holds a figure (or a dash standing in for one)."""
    text = _STRIP_RE.sub("", cell_html).strip()
    if not text:
        return False
    if text in _DASHES:
        return True
    return bool(_DIGIT_RE.search(text)) and bool(_NUMERIC_RE.match(text))


def merge_class(attrs, *extra):
    """Return attrs with the extra classes merged into any existing class."""
    attrs = list(attrs)
    classes = []
    out = []
    for key, value in attrs:
        if key == "class":
            classes.extend((value or "").split())
        else:
            out.append((key, value))
    for token in extra:
        if token and token not in classes:
            classes.append(token)
    if classes:
        out.append(("class", " ".join(classes)))
    return out


def _render_attrs(attrs):
    parts = []
    for key, value in attrs:
        if value is None:
            parts.append(" " + key)
        else:
            parts.append(' {}="{}"'.format(key, value.replace('"', "&quot;")))
    return "".join(parts)


class _TableCollector(HTMLParser):
    """Collect every top-level <table> as (start, end, attrs, head rows, body rows)."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tables = []
        self._depth = 0
        self._current = None
        self._cell = None
        self._row = None
        self._section = "body"
        self._chunks = []
        self._pos_stack = []

    def _emit(self, text):
        if self._cell is not None:
            self._cell["html"].append(text)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._current = {"attrs": list(attrs), "head": [], "body": [],
                                 "start": self.getpos(), "tag": self.get_starttag_text()}
                self._section = "body"
                return
        if self._current is None:
            return
        if self._depth > 1:
            self._emit(self.get_starttag_text())
            return
        if tag == "thead":
            self._section = "head"
        elif tag in ("tbody", "tfoot"):
            self._section = "body"
        elif tag == "tr":
            self._row = {"attrs": list(attrs), "cells": []}
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"tag": tag, "attrs": list(attrs), "html": []}
        else:
            self._emit(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if self._current is not None and self._depth >= 1:
            self._emit(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self._current is None:
            return
        if tag == "table":
            if self._depth == 1:
                self._current["end"] = self.getpos()
                self.tables.append(self._current)
                self._current = None
            else:
                self._emit("</table>")
            self._depth -= 1
            return
        if self._depth > 1:
            self._emit("</{}>".format(tag))
            return
        if tag in ("td", "th") and self._cell is not None:
            self._row["cells"].append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            target = self._current["head"] if self._section == "head" else self._current["body"]
            target.append(self._row)
            self._row = None
        elif tag in ("thead", "tbody", "tfoot"):
            self._section = "body"
        else:
            self._emit("</{}>".format(tag))

    def handle_data(self, data):
        self._emit(data)

    def handle_entityref(self, name):
        self._emit("&{};".format(name))

    def handle_charref(self, name):
        self._emit("&#{};".format(name))

    def handle_comment(self, data):
        self._emit("<!--{}-->".format(data))


def _offsets(html):
    """Line starts, so parser (line, col) positions map to string offsets."""
    starts = [0]
    for i, ch in enumerate(html):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def classify(head, body):
    """Decide the register of one table from its cell HTML.

    Returns (numeric_columns, is_numeric_table, total_rows) where total_rows is
    the set of body row indexes that read as totals.
    """
    ncol = max([len(r["cells"]) for r in head + body] or [0])
    numeric_columns = []
    for c in range(ncol):
        cells = [r["cells"][c] for r in body if c < len(r["cells"])]
        filled = ["".join(x["html"]) for x in cells if "".join(x["html"]).strip()]
        numeric_columns.append(bool(filled) and sum(is_numeric_text(h) for h in filled) >= 0.5 * len(filled))
    numeric_count = sum(numeric_columns)
    is_numeric_table = numeric_count >= 1 and numeric_count >= (ncol - 1) / 2.0
    totals = set()
    if is_numeric_table and body:
        bold = [i for i, r in enumerate(body)
                if r["cells"] and _STRONG_RE.match("".join(r["cells"][0]["html"]) or "")]
        if 0 < len(bold) <= max(1, int(len(body) * TOTAL_SHARE)):
            totals = set(bold)
    return numeric_columns, is_numeric_table, totals


def _rebuild(table):
    head, body = table["head"], table["body"]
    classes = " ".join(v for k, v in table["attrs"] if k == "class")
    if "fs" in classes.split():
        return None  # a statement table already carries its own register
    numeric_columns, is_numeric_table, totals = classify(head, body)
    register = "numeric" if is_numeric_table else "text"
    extra = [register]
    if len(body) <= KEEP_ROWS:
        extra.append("keep")
    attrs = merge_class(table["attrs"], *extra)
    out = ["<table{}>".format(_render_attrs(attrs))]

    def cell_html(cell, col):
        cattrs = cell["attrs"]
        if col < len(numeric_columns) and numeric_columns[col]:
            cattrs = merge_class(cattrs, "num")
        return "<{t}{a}>{h}</{t}>".format(t=cell["tag"], a=_render_attrs(cattrs), h="".join(cell["html"]))

    if head:
        out.append("<thead>")
        for row in head:
            out.append("<tr{}>{}</tr>".format(
                _render_attrs(row["attrs"]),
                "".join(cell_html(c, i) for i, c in enumerate(row["cells"]))))
        out.append("</thead>")
    out.append("<tbody>")
    last = len(body) - 1
    for i, row in enumerate(body):
        rattrs = row["attrs"]
        if i in totals:
            rattrs = merge_class(rattrs, "fin" if i == last else "tot")
        out.append("<tr{}>{}</tr>".format(
            _render_attrs(rattrs),
            "".join(cell_html(c, k) for k, c in enumerate(row["cells"]))))
    out.append("</tbody></table>")
    return "".join(out)


def restyle(html):
    """Rewrite every plain table in an HTML fragment into the table register."""
    if "<table" not in html:
        return html
    collector = _TableCollector()
    collector.feed(html)
    collector.close()
    if not collector.tables:
        return html
    starts = _offsets(html)
    pieces = []
    cursor = 0
    for table in collector.tables:
        (l0, c0), (l1, c1) = table["start"], table["end"]
        begin = starts[l0 - 1] + c0
        end = starts[l1 - 1] + c1 + len("</table>")
        rebuilt = _rebuild(table)
        if rebuilt is None:
            continue
        pieces.append(html[cursor:begin])
        pieces.append(rebuilt)
        cursor = end
    pieces.append(html[cursor:])
    return "".join(pieces)
