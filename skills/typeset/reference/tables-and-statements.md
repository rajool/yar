# Tables and financial statements

Tables are where a converted document gives itself away: body-size figures in
proportional numerals, a rule under every row, a header in bold, a total that
looks like any other line. The register below is what `typeset` applies to
every table, and how to get a full statement out of it.

## 1. The register

Every table is set a step smaller than the prose (`table.size_em`, default
0.86), with the column heads as small tracked labels under a single rule, and
figures in tabular lining numerals so columns align down the page.

`scripts/tables.py` reads each Markdown table after conversion and classifies
it. Nothing is required of the author beyond ordinary Markdown:

| What it reads | What it does |
|---|---|
| A column whose filled cells are mostly figures (digits with separators, `%`, `×`, `(negatives)`, a dash for nil, a currency code) | Marks the column `num`: right-aligned, tabular figures, header included. |
| Mostly-numeric columns across the table | The table is `numeric`: no rule between ordinary rows, because the eye reads down a column of figures without help. |
| Mostly text columns | The table is `text`: a hairline between rows, a firmer rule to close, because long cells need the guide. |
| A **bold** label in the first cell of a `numeric` table, when such rows are the minority | A total: rule above, emphasis weight (`tr.tot`). The last bold row is the final total and takes the double rule (`tr.fin`). |
| A bold label in a `text` table | Just a label; text tables have no totals. |
| Sixteen rows or fewer | `keep`: the table stays whole on a page. Longer tables break and repeat their head; a total row never starts a page. |

Author-supplied classes are preserved (`<td class="mine">` becomes
`class="mine num"`), and a table that already declares the statement register
(`class="fs"`) is left alone.

Write totals bold and let the register rule them:

```markdown
| CAD                | FY2025        | FY2026        |
|--------------------|---------------|---------------|
| External revenue   | 8,961,560     | 12,219,070    |
| Cost of goods sold | 3,143,143     | 4,087,436     |
| **Gross profit**   | **5,818,418** | **8,131,634** |
```

## 2. Statements

A statement has more structure than a grid: sections, groups, indented items,
group sub-totals, key lines and a double-ruled last line. `scripts/statements.py`
holds that structure as rows and renders the `fs` table the stylesheet knows:

| Row kind | Meaning | Set as |
|---|---|---|
| `sec` | Section head (Income, Cost of goods sold, Assets) | Small tracked caps spanning the table, space above |
| `grp` | Group head (General and administrative) | A plain line spanning the table |
| `item` | A line item; `depth` 1 to 3 sets the indent | Figures right-aligned |
| `gtot` | A group sub-total | Hairline above the figures |
| `tot` | A section total (Total income) | Rule above, emphasis weight |
| `key` | A derived key line (Gross profit, Operating profit) | Rule above, emphasis weight |
| `fin` | The last line (Profit for the year, Total assets) | Rule above, double rule below |
| `memo` | A memorandum line | Muted italic |

```python
import sys; sys.path.insert(0, "<plugin>/skills/typeset/scripts")
from statements import Row, statement_table, key_figures_table, footnotes

rows = [
    Row("sec", "Income"),
    Row("item", "Sales of apps", [4720487, 7498583, 12219070, None, 12219070], depth=1),
    Row("item", "Sales of services (intercompany)", [1405682, 0, 1405682, -1405682, 0], depth=1, note=1),
    Row("tot", "Total income", [6126170, 7498583, 13624752, -1405682, 12219070]),
    Row("fin", "Profit for the year", [1820926, 3247298, 5068224, -2000000, 3068224]),
]
html = statement_table(rows, ["Entity A", "Entity B", "Combined", "Elimination", "Consolidated"],
                       first_header="CAD", blank_zero=[3])
notes = footnotes(["Intercompany charges, eliminated against operating expenses."])
```

Paste the returned HTML into the Markdown source (block-level HTML passes
through). Figures print whole with thousands separators, negatives in
parentheses, nil as an em dash; `blank_zero` names columns whose nil cells stay
empty, which is what an elimination column wants. `note=1` appends a footnote
marker to the label; `footnotes()` writes the matching numbered lines, and its
`start` argument lets a balance sheet continue the numbering of the profit and
loss above it.

`key_figures_table()` sets the short summary that usually follows a statement
(label, amount, ratio), indenting labels that start with "of which" and
setting Gross / Operating / Profit / Net / Total lines as key rows.

## 3. From a QuickBooks export

QuickBooks Online exports a report as an indented outline: a group's name, its
children one column in, and a "Total <name>" line that closes the group, with
one amount column per entity when the report was run by class or location.
`scripts/quickbooks_export.py` reads that outline into a tree:

```python
import openpyxl
from quickbooks_export import parse_sheet, build_tree, group_sum, find_item

ws = openpyxl.load_workbook("pl-export.xlsx", data_only=True)["Sheet1"]
tree = build_tree(parse_sheet(ws, entity_headers=("Entity A", "Entity B")))
income = next(n for n in tree if n["label"] == "INCOME")
totals = group_sum(income)   # per entity; raises if the children do not sum to the export's own total
ads = find_item(tree[2], "Digital Advertising")
```

Walk the tree to emit rows: a `group` becomes a `grp` row, its children
`item` rows one level deeper, its total a `gtot`; the top-level sections
become `sec` rows with `tot` lines; derived lines (gross profit, operating
profit, profit before tax) are `key` rows you compute; the last line is `fin`.
Groups whose detail is noise (bank sub-accounts, asset classes) can be
collapsed to a single item carrying the group total. Every export total is
checked against the sum of its children, so a mis-parsed outline fails loudly
rather than printing a wrong statement.

Two habits keep statements honest:

- **Reproduce the ledger's own totals, then show the corrections as
  columns** (an elimination column, a consolidated column) rather than editing
  the figures in place. A reader can tie each entity back to the export.
- **State the basis once** (which ledger, which period, audited or not, which
  consolidation adjustments) and footnote the individual lines that need it.

## 4. Consistency across a set

When a package carries several statements, generate them from one script with
one structure (the same column order, the same section names, the same
footnote style) and render them with the same theme. The sample in
[`assets/samples/statement.md`](../assets/samples/statement.md) shows the
target layout.
