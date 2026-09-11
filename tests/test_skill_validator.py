"""validate.py: frontmatter that does not parse is a hard error, never a silent pass.

The runtime loader drops *every* field of a skill whose YAML frontmatter fails to
parse -- name, description, the lot -- so the skill stops triggering while still
looking fine on disk. The validator used to hide exactly that: its PyYAML call sat
inside a bare ``except Exception``, so a parse error fell through to the lenient
key: value fallback, which read the broken frontmatter happily and reported PASS.
Four of yar's own skills shipped that way.

These tests pin the fix: a real YAML error fails, the fallback still covers a
missing PyYAML, and every skill and agent in the repo parses strictly.
"""
import glob
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO, load  # noqa: E402

v = load("skills/skill-builder/scripts/validate.py", "skill_validate")
SCRIPT = os.path.join(REPO, "skills/skill-builder/scripts/validate.py")

# An unquoted scalar carrying ": " -- YAML reads it as a nested mapping and gives up.
BROKEN = "name: demo\ndescription: Ships it. Not done at `gh pr create`: done at merge.\n"
FIXED = "name: demo\ndescription: 'Ships it. Not done at `gh pr create`: done at merge.'\n"


def write_skill(frontmatter, name="demo"):
    """A throwaway skill dir (named to match ``name``) whose SKILL.md carries ``frontmatter``."""
    d = os.path.join(tempfile.mkdtemp(), name)
    os.mkdir(d)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\n" + frontmatter + "---\n\n# demo\n\nBody.\n")
    return d


class ParseFrontmatter(unittest.TestCase):
    def test_unparseable_yaml_raises(self):
        with self.assertRaises(v.FrontmatterError):
            v.parse_frontmatter(BROKEN)

    def test_quoting_the_value_fixes_it(self):
        fm = v.parse_frontmatter(FIXED)
        self.assertEqual(fm["name"], "demo")
        self.assertIn("gh pr create", fm["description"])

    def test_fallback_still_covers_a_missing_pyyaml(self):
        """No PyYAML is a reason to fall back. A parse error is not."""
        import builtins

        real = builtins.__import__

        def no_yaml(name, *a, **kw):
            if name == "yaml":
                raise ImportError("no yaml")
            return real(name, *a, **kw)

        builtins.__import__ = no_yaml
        try:
            fm = v.parse_frontmatter("name: demo\ndescription: hi\n")
        finally:
            builtins.__import__ = real
        self.assertEqual(fm["name"], "demo")


class ValidateSkill(unittest.TestCase):
    def test_broken_frontmatter_is_reported_as_an_error(self):
        errors, _ = v.validate_skill(write_skill(BROKEN))
        self.assertTrue(errors, "a skill the runtime cannot read must not validate clean")
        self.assertIn("no metadata", errors[0])

    def test_broken_frontmatter_exits_nonzero(self):
        r = subprocess.run(
            [sys.executable, SCRIPT, write_skill(BROKEN)], capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FAIL", r.stdout)

    def test_a_good_skill_still_passes(self):
        errors, _ = v.validate_skill(write_skill(FIXED))
        self.assertEqual(errors, [])


class RepoIsClean(unittest.TestCase):
    def test_every_skill_and_agent_parses_strictly(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        paths = sorted(glob.glob(os.path.join(REPO, "skills/*/SKILL.md")))
        paths += sorted(glob.glob(os.path.join(REPO, "agents/*.md")))
        self.assertTrue(paths, "no skills or agents found")
        for p in paths:
            with self.subTest(path=os.path.relpath(p, REPO)):
                with open(p, encoding="utf-8") as f:
                    text = f.read()
                self.assertTrue(text.startswith("---\n"), "no frontmatter")
                data = yaml.safe_load(text[4:text.index("\n---", 4)])
                self.assertIsInstance(data, dict)
                self.assertTrue(data.get("name"), "name missing")
                self.assertTrue(data.get("description"), "description missing")


if __name__ == "__main__":
    unittest.main()
