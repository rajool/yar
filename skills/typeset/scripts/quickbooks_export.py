#!/usr/bin/env python3
"""Read a QuickBooks Online report export (profit and loss, balance sheet) into
a tree that statements.py can render.

A QuickBooks export lays a report out as an indented outline: an account
group's name sits in one column, its children one column further in, and the
group closes with a "Total <name>" line at the group's own indent. Amount
columns follow, one per entity when the report was run by class or location,
plus a "Total" column. This module turns that outline into nested groups with
their amounts per entity, checks every group against the export's own total,
and hands back plain dicts:

    {"kind": "group", "label": "General and Administrative",
     "children": [...], "total": {"label": ..., "values": [...]}}
    {"kind": "item",  "label": "Bank charges", "values": [2255.08, 1889.30]}

Usage:

    import openpyxl
    from quickbooks_export import parse_sheet, build_tree, group_sum
    ws = openpyxl.load_workbook("export.xlsx", data_only=True)["Sheet1"]
    entities, tree = build_tree(parse_sheet(ws, entity_headers=("Company A", "Company B")))

`parse_sheet` needs to know which header cells name the entity columns; pass
the header texts as they appear in the export. Nothing here knows any
particular company's chart of accounts.
"""


def parse_sheet(ws, entity_headers):
    """Flatten an export sheet into entries: level, label, values, kind.

    `ws` is an openpyxl worksheet read with data_only=True. `entity_headers`
    are the column headings of the entities to keep, in the order wanted.
    """
    rows = list(ws.iter_rows(values_only=True))
    cols = {}
    start = None
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            if isinstance(v, str) and v.strip() in entity_headers:
                cols[v.strip()] = j
        if len(cols) == len(entity_headers):
            start = i + 1
            break
    if start is None:
        raise ValueError("entity headers not found: {}".format(entity_headers))
    value_cols = [cols[h] for h in entity_headers]
    label_limit = min(value_cols)
    # skip a possible period line under the headers
    while start < len(rows) and not any(
            isinstance(v, str) and v.strip() for v in rows[start][:label_limit]):
        start += 1
    out = []
    for r in rows[start:]:
        labels = [(j, v.strip()) for j, v in enumerate(r[:label_limit]) if isinstance(v, str) and v.strip()]
        if not labels:
            continue
        level, label = labels[0]
        values = [float(r[c]) if isinstance(r[c], (int, float)) else 0.0 for c in value_cols]
        out.append({"level": level, "label": label, "values": values})
    for k, e in enumerate(out):
        nxt = out[k + 1] if k + 1 < len(out) else None
        if e["label"].lower().startswith("total "):
            e["kind"] = "total"
        elif nxt and nxt["level"] > e["level"]:
            e["kind"] = "header"
        else:
            e["kind"] = "item"
    return out


def build_tree(entries):
    """Nest flat entries into groups closed by their own "Total" line.

    An amount booked directly to a parent account (the group row carries a
    value of its own) becomes a child item labelled "<group> (parent account)"
    so that the children still sum to the group's total.
    """
    def parse_level(i, level):
        nodes = []
        while i < len(entries):
            e = entries[i]
            if e["level"] < level or e["kind"] == "total":
                break
            if e["level"] > level:
                raise ValueError("unexpected indentation at {}".format(e["label"]))
            if e["kind"] == "header":
                children, i = parse_level(i + 1, level + 1)
                total = None
                if i < len(entries) and entries[i]["kind"] == "total" and entries[i]["level"] == level:
                    total = {"label": entries[i]["label"], "values": entries[i]["values"]}
                    i += 1
                if any(abs(v) > 0.005 for v in e["values"]):
                    children.append({"kind": "item", "label": e["label"] + " (parent account)",
                                     "values": list(e["values"])})
                nodes.append({"kind": "group", "label": e["label"], "children": children, "total": total})
            else:
                nodes.append({"kind": "item", "label": e["label"], "values": list(e["values"])})
                i += 1
        return nodes, i

    nodes, i = parse_level(0, 0)
    if i != len(entries):
        raise ValueError("unparsed rows from {}".format(entries[i]["label"]))
    return nodes


def group_sum(node, check=True, tolerance=0.02):
    """Sum a group's items per entity, checking against the export's own total."""
    n = len(node["children"][0]["values"]) if node.get("children") else 0
    for child in node.get("children", []):
        n = max(n, len(child.get("values", [])) if child["kind"] == "item" else n)
    totals = [0.0] * n
    for child in node["children"]:
        values = child["values"] if child["kind"] == "item" else group_sum(child, check, tolerance)
        for k, v in enumerate(values):
            totals[k] += v
    if check and node.get("total"):
        for k, v in enumerate(node["total"]["values"]):
            if k < len(totals) and abs(totals[k] - v) > tolerance:
                raise ValueError("{}: children sum to {:,.2f}, export total is {:,.2f}".format(
                    node["label"], totals[k], v))
    return totals


def find_item(node, label_prefix):
    """Sum of every item under `node` whose label starts with `label_prefix`."""
    n = 0
    total = None
    for child in node.get("children", []):
        if child["kind"] == "item":
            if child["label"].startswith(label_prefix):
                total = [a + b for a, b in zip(total, child["values"])] if total else list(child["values"])
            n = len(child["values"])
        else:
            sub = find_item(child, label_prefix)
            if sub is not None:
                total = [a + b for a, b in zip(total, sub)] if total else sub
    return total if total is not None else ([0.0] * n if n else None)
