#!/usr/bin/env python3
"""
A lightweight Agent Skills validator.

Checks a skill folder against the current Agent Skills standard.
The rules come from reference/standards.md (source: agentskills.io/specification +
platform.claude.com + the official skill-creator skill).

Usage:
    python3 validate.py <path-to-skill-dir>

Output: a list of ✓ / ⚠ / ✗ and PASS or FAIL at the end.
Exit code: 0 if there was no error (FAIL), 1 if there was. Warnings (⚠) don't change the exit code.

No external dependency; if PyYAML is installed it uses it, otherwise a simple
internal parser for single-line frontmatter is used (enough for typical skills).
"""
import os
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\]\(([^)]+)\)")

NAME_MAX = 64
DESC_MAX = 1024
DESC_MIN_RECOMMENDED = 100
BODY_MAX_LINES = 500


def split_frontmatter(text):
    """Splits the text into (frontmatter_block, body). If there was no frontmatter, (None, text)."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    # The first line is ---; look for the closing ---.
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            block = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return block, body
    return None, text


def parse_frontmatter(block):
    """First with PyYAML; if not available, a simple single-line key: value parser."""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(block)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    data = {}
    key = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t")):
            key = m.group(1)
            val = m.group(2).strip()
            if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
                val = val[1:-1]
            data[key] = val
        elif key is not None and raw.startswith((" ", "\t")):
            # continuation of a multi-line (folded) value
            data[key] = (str(data.get(key, "")) + " " + raw.strip()).strip()
    return data


def find_local_md_links(text):
    """Returns local relative links (not http/anchor)."""
    out = []
    for target in LINK_RE.findall(text):
        t = target.strip()
        if t.startswith(("http://", "https://", "mailto:", "#")) or "://" in t:
            continue
        t = t.split("#", 1)[0].split(" ", 1)[0].strip()
        if t:
            out.append(t)
    return out


def validate_skill(skill_dir):
    """Returns (errors, warnings). errors means FAIL."""
    errors, warnings = [], []
    skill_dir = os.path.abspath(skill_dir)
    dirname = os.path.basename(skill_dir)

    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        errors.append("SKILL.md not found (every skill must have a SKILL.md).")
        return errors, warnings

    with open(skill_md, "r", encoding="utf-8") as f:
        text = f.read()

    block, body = split_frontmatter(text)
    if block is None:
        errors.append("YAML frontmatter (the block between two --- lines) is not at the start of SKILL.md.")
        return errors, warnings

    fm = parse_frontmatter(block)
    name = fm.get("name")
    desc = fm.get("description")

    # name
    if not name:
        errors.append("The name field is not in the frontmatter.")
    else:
        name = str(name).strip()
        if not NAME_RE.match(name):
            errors.append("name must be kebab-case (a-z, 0-9, hyphen; no \"--\", no leading/trailing hyphen): %r" % name)
        if len(name) > NAME_MAX:
            errors.append("name is longer than %d characters (%d)." % (NAME_MAX, len(name)))
        if name != dirname:
            errors.append("name (%r) does not match the folder name (%r)." % (name, dirname))

    # description
    if not desc:
        errors.append("The description field is not in the frontmatter.")
    else:
        desc = str(desc).strip()
        n = len(desc)
        if n == 0:
            errors.append("description is empty.")
        if n > DESC_MAX:
            errors.append("description is longer than %d characters (%d)." % (DESC_MAX, n))
        if "<" in desc or ">" in desc:
            errors.append("description must not contain \"<\" or \">\" (an XML tag).")
        if 0 < n < DESC_MIN_RECOMMENDED:
            warnings.append("description is short (%d characters); for good recommended triggering it should be ~%d+ characters and include \"what + when\"." % (n, DESC_MIN_RECOMMENDED))

    # body length
    body_lines = len(body.splitlines())
    if body_lines > BODY_MAX_LINES:
        warnings.append("The SKILL.md body is %d lines (> %d); it's better to move detailed content to reference/." % (body_lines, BODY_MAX_LINES))

    # broken links in SKILL.md
    for target in find_local_md_links(body):
        if not os.path.exists(os.path.join(skill_dir, target)):
            warnings.append("Broken local link in SKILL.md: %s" % target)

    # reference depth: files in reference/ should not link to another file inside reference/ (one level deep).
    ref_dir = os.path.join(skill_dir, "reference")
    if os.path.isdir(ref_dir):
        for fn in os.listdir(ref_dir):
            if not fn.endswith(".md"):
                continue
            with open(os.path.join(ref_dir, fn), "r", encoding="utf-8") as f:
                rtext = f.read()
            for target in find_local_md_links(rtext):
                resolved = os.path.normpath(os.path.join(ref_dir, target))
                if resolved.startswith(ref_dir + os.sep) and os.path.abspath(resolved) != os.path.abspath(os.path.join(ref_dir, fn)):
                    warnings.append("Nested reference: reference/%s links to %s — keep references one level from SKILL.md." % (fn, target))

    return errors, warnings


def main(argv):
    if len(argv) != 2:
        print("Usage: python3 validate.py <path-to-skill-dir>")
        return 2
    skill_dir = argv[1]
    if not os.path.isdir(skill_dir):
        print("✗ Folder not found: %s" % skill_dir)
        return 2

    errors, warnings = validate_skill(skill_dir)
    print("Skill validation: %s\n" % os.path.abspath(skill_dir))
    for w in warnings:
        print("  ⚠  %s" % w)
    for e in errors:
        print("  ✗  %s" % e)
    if not errors and not warnings:
        print("  ✓  All checks passed with no issues.")
    print()
    if errors:
        print("Result: FAIL (%d errors, %d warnings)" % (len(errors), len(warnings)))
        return 1
    print("Result: PASS (%d warnings)" % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
