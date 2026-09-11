#!/usr/bin/env python3
"""Financial statements for typeset: rows in, a designed statement table out.

A statement is a table with more structure than a grid: sections (INCOME),
groups (General and administrative), indented line items, group sub-totals,
section totals, key lines (Gross profit) and a final line under a double rule.
This module holds that structure as `Row` objects and renders it as an HTML
table carrying the `fs` register that render.py styles:

    tr.sec    a section head, spanning the table          INCOME
    tr.grp    a group head, spanning the table            General and administrative
    tr.item   a line item; .d1 .d2 .d3 set the indent     Bank charges
    tr.gtot   a group sub-total: hairline above           Total general and administrative
    tr.tot    a section total: rule above, emphasis        Total income
    tr.key    a derived key line: rule above, emphasis     Gross profit
    tr.fin    the last line: rule above, double rule below Profit for the year

Figures are rendered whole, with thousands separators, negatives in
parentheses and nil as an em dash -- the conventions of a printed statement.
A column may be marked `blank_zero` (an elimination column, say) so that its
empty cells stay empty instead of showing a dash.

    from statements import Row, statement_table
    rows = [Row("sec", "Income"),
            Row("item", "Sales", [4720487, 7498583], depth=1),
            Row("tot", "Total income", [4720487, 7498583])]
    html = statement_table(rows, ["Entity A", "Entity B"])

Nothing here is specific to any company or ledger; quickbooks_export.py shows
how to feed it from an accounting export.
"""
import html as html_mod

KINDS = ("sec", "grp", "item", "gtot", "tot", "key", "fin", "memo")


def fmt(value, dash_zero=True):
    """A figure the way a statement prints it: whole, grouped, (negative), nil as a dash."""
    if value is None:
        return ""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return html_mod.escape(str(value), quote=False)
    if abs(value) < 0.5:
        return "—" if dash_zero else ""
    text = "{:,.0f}".format(abs(value))
    return "({})".format(text) if value < 0 else text


class Row:
    """One line of a statement. `values` align with the table's columns."""

    def __init__(self, kind, label, values=None, depth=0, note=None):
        if kind not in KINDS:
            raise ValueError("unknown row kind: {}".format(kind))
        self.kind = kind
        self.label = label
        self.values = list(values) if values is not None else []
        self.depth = depth
        self.note = note      # a footnote marker, e.g. 1 or "a"


def statement_table(rows, columns, first_header="", blank_zero=(), cls="fs"):
    """Render rows as an HTML table in the statement register.

    columns      the column headings, in order
    first_header the heading over the label column (often the currency)
    blank_zero   indexes of columns whose nil cells stay empty (elimination columns)
    cls          the table class; `fs` is what the stylesheet expects
    """
    blank_zero = set(blank_zero)
    ncol = len(columns) + 1
    out = ['<table class="{}">'.format(html_mod.escape(cls, quote=True)), "<thead><tr>",
           "<th>{}</th>".format(html_mod.escape(str(first_header), quote=False))]
    for head in columns:
        out.append('<th class="num">{}</th>'.format(html_mod.escape(str(head), quote=False)))
    out.append("</tr></thead><tbody>")
    for row in rows:
        label = html_mod.escape(str(row.label), quote=False)
        if row.note is not None:
            label += "<sup>{}</sup>".format(html_mod.escape(str(row.note), quote=False))
        classes = row.kind + (" d{}".format(row.depth) if row.depth else "")
        if row.kind in ("sec", "grp"):
            out.append('<tr class="{}"><td colspan="{}">{}</td></tr>'.format(classes, ncol, label))
            continue
        cells = []
        for i, head in enumerate(columns):
            value = row.values[i] if i < len(row.values) else None
            cells.append('<td class="num">{}</td>'.format(fmt(value, dash_zero=i not in blank_zero)))
        out.append('<tr class="{}"><td>{}</td>{}</tr>'.format(classes, label, "".join(cells)))
    out.append("</tbody></table>")
    return "\n".join(out)


def key_figures_table(lines, first_header="", cls="fs kf"):
    """A short summary table: (label, amount, ratio) triples, ratio optional.

    Labels that start with "of which" are indented; a label that starts with a
    key word (Gross, Operating, Profit, Net, Total) is set as a key line.
    """
    out = ['<table class="{}">'.format(cls), "<thead><tr><th>{}</th>".format(
        html_mod.escape(str(first_header), quote=False)),
        '<th class="num">Amount</th><th class="num">% of revenue</th></tr></thead><tbody>']
    for label, amount, ratio in lines:
        text = html_mod.escape(str(label), quote=False)
        classes = "item"
        if str(label).lower().startswith("of which"):
            classes = "item d1"
        elif str(label).split(" ")[0] in ("Gross", "Operating", "Profit", "Net", "Total"):
            classes = "key"
        pct = "" if ratio is None else "{:.1f}%".format(float(ratio) * 100)
        out.append('<tr class="{}"><td>{}</td><td class="num">{}</td><td class="num">{}</td></tr>'.format(
            classes, text, fmt(amount), pct))
    out.append("</tbody></table>")
    return "\n".join(out)


def footnotes(notes, start=1):
    """Numbered footnotes as Markdown paragraphs, continuing from `start`."""
    return "\n\n".join("<sup>{}</sup> {}".format(i, text) for i, text in enumerate(notes, start=start))
