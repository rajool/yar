"""install-rtl: manages a marked rule block in the global CLAUDE.md.

Covers: fresh install into an empty/missing file, idempotent re-run, in-place
upgrade of an outdated managed block, preservation of surrounding content, and
malformed marker pairs treated as absent (append, never rewrite outside a
well-formed block).
"""
import os
import re
import tempfile
import unittest

from _load import load

rtl = load("scripts/install-rtl.py", "install_rtl")


class TestApply(unittest.TestCase):
    def test_fresh_install_on_empty_text(self):
        text, action = rtl.apply("")
        self.assertEqual(action, "installed")
        self.assertEqual(text.count(rtl.BEGIN_MARK), 1)
        self.assertEqual(text.count(rtl.END_MARK), 1)
        self.assertIn(rtl.RULE, text)
        self.assertTrue(text.endswith("\n"))

    def test_reapply_is_unchanged(self):
        once, _ = rtl.apply("")
        twice, action = rtl.apply(once)
        self.assertEqual(action, "unchanged")
        self.assertEqual(once, twice)

    def test_outdated_block_is_updated_in_place(self):
        stale = "prefix stays\n\n{}\nOLD RULE\n{}\n\nsuffix stays\n".format(
            rtl.BEGIN_MARK, rtl.END_MARK
        )
        text, action = rtl.apply(stale)
        self.assertEqual(action, "updated")
        self.assertNotIn("OLD RULE", text)
        self.assertIn(rtl.RULE, text)
        self.assertTrue(text.startswith("prefix stays"))
        self.assertTrue(text.endswith("suffix stays\n"))
        self.assertEqual(text.count(rtl.BEGIN_MARK), 1)

    def test_existing_content_is_preserved_on_install(self):
        text, action = rtl.apply("# my global rules\n\nkeep me\n")
        self.assertEqual(action, "installed")
        self.assertTrue(text.startswith("# my global rules\n\nkeep me\n"))
        self.assertIn(rtl.BEGIN_MARK, text)

    def test_malformed_markers_treated_as_absent(self):
        end_before_begin = "{}\nnoise\n{}\n".format(rtl.END_MARK, rtl.BEGIN_MARK)
        text, action = rtl.apply(end_before_begin)
        self.assertEqual(action, "installed")
        self.assertTrue(text.startswith(end_before_begin.rstrip("\n")))
        self.assertIn(rtl.RULE, text)


class TestInstall(unittest.TestCase):
    def test_install_creates_missing_file_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".claude", "CLAUDE.md")
            self.assertEqual(rtl.install(path), "installed")
            with open(path, encoding="utf-8") as fh:
                first = fh.read()
            self.assertIn(rtl.RULE, first)
            self.assertEqual(rtl.install(path), "unchanged")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), first)

    def test_target_path_honors_claude_config_dir(self):
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = "/tmp/custom-claude"
        try:
            self.assertEqual(
                rtl.target_path(), os.path.join("/tmp/custom-claude", "CLAUDE.md")
            )
        finally:
            if old is None:
                del os.environ["CLAUDE_CONFIG_DIR"]
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old


class TestRuleKit(unittest.TestCase):
    """The v3 pay-per-use kit: base + snippets, and the v2 review invariants."""

    def test_no_svg_data_uris_remain(self):
        # The data URIs were the most mangling-prone bytes of the verbatim
        # copy; the kit must stay free of them (glyphs + accent borders now).
        self.assertNotIn("data:image/svg", rtl.RULE)

    def test_every_documented_component_has_a_snippet(self):
        for tag, selector in [
            ("TABLE", ".rc table{"), ("BADGE", ".rc .badge{"), ("KV", ".rc .kv{"),
            ("KPI", ".rc .kpi{"), ("BARS", ".rc .bars{"), ("DONUT", ".rc .donut{"),
            ("FLOW", ".rc .flow{"), ("TL", ".rc .tl{"), ("CTA", ".rc .cta{"),
        ]:
            self.assertIn("\n" + tag + " ", rtl.RULE)
            self.assertIn(selector, rtl.RULE)

    def test_base_keeps_inline_block_code_isolation(self):
        # Empirical v1 finding: bare isolate is not enough for neutral-edged
        # tokens; inline-block is what makes them atomic.
        self.assertIn("display:inline-block", rtl.RULE)

    def test_no_bare_sub_11px_font_sizes(self):
        # Every sub-1em size must be floored via max(...,11px); a bare
        # "font-size:.Nem" would render below the readable floor.
        self.assertEqual(re.findall(r"font-size:\.\d+em", rtl.RULE), [])

    def test_composition_stays_a_palette(self):
        self.assertIn("lightest structure", rtl.RULE)


if __name__ == "__main__":
    unittest.main()
