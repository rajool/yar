#!/usr/bin/env python3
"""
Package a skill folder into a <name>.skill file (a zip archive).

Usage:
    python3 package_skill.py <path-to-skill-dir> [-o OUTPUT_DIR]

First runs validate.py; if there was any error (FAIL) it is not packaged.
SKILL.md is placed at the root of the zip (the API upload requirement: SKILL.md at the top level).
The output is not committed to git — it's a temporary artifact for upload/distribution.

Items excluded from the archive: __pycache__/ , *.pyc , .DS_Store , evals/ (at the skill root),
and any pre-existing *.skill file.
"""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import validate_skill, split_frontmatter, parse_frontmatter  # noqa: E402

MAX_MB = 30  # Skills API upload ceiling


def skill_name(skill_dir):
    skill_md = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            block, _ = split_frontmatter(f.read())
        name = parse_frontmatter(block or "").get("name")
        if name:
            return str(name).strip()
    except Exception:
        pass
    return os.path.basename(os.path.abspath(skill_dir))


def should_skip(rel_parts, filename):
    if "__pycache__" in rel_parts:
        return True
    if filename in (".DS_Store",) or filename.endswith(".pyc") or filename.endswith(".skill"):
        return True
    # evals/ is only excluded at the skill root
    if rel_parts and rel_parts[0] == "evals":
        return True
    return False


def package(skill_dir, out_dir):
    skill_dir = os.path.abspath(skill_dir)
    errors, warnings = validate_skill(skill_dir)
    for w in warnings:
        print("  ⚠  %s" % w)
    if errors:
        for e in errors:
            print("  ✗  %s" % e)
        print("\nPackaging stopped — fix the validation errors first.")
        return None

    name = skill_name(skill_dir)
    out_dir = os.path.abspath(out_dir or os.getcwd())
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, name + ".skill")

    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(skill_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                abs_path = os.path.join(root, fn)
                rel = os.path.relpath(abs_path, skill_dir)
                rel_parts = rel.split(os.sep)
                if should_skip(rel_parts, fn):
                    continue
                zf.write(abs_path, rel)  # SKILL.md at the root of the zip
                count += 1

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print("\n✓ Created: %s" % out_path)
    print("  %d files, %.2f MB" % (count, size_mb))
    if size_mb > MAX_MB:
        print("  ⚠  Larger than %d MB — too big for a Skills API upload." % MAX_MB)
    return out_path


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    out_dir = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 < len(argv):
            out_dir = argv[i + 1]
            args = [a for a in args if a != out_dir]
    if len(args) != 1:
        print("Usage: python3 package_skill.py <path-to-skill-dir> [-o OUTPUT_DIR]")
        return 2
    if not os.path.isdir(args[0]):
        print("✗ Folder not found: %s" % args[0])
        return 2
    return 0 if package(args[0], out_dir) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
