"""typeset: theme resolution, locale handling, HTML transformation, tables and decks.

These cover the pure logic only -- no Chrome, no network. The renderer's
font fetching is exercised by asking for CSS in offline mode, which must
degrade to system fallbacks rather than raise.
"""
import os
import re
import sys
import unittest

from _load import REPO

SCRIPTS = os.path.join(REPO, "skills", "typeset", "scripts")
sys.path.insert(0, SCRIPTS)

import fonts          # noqa: E402
import render         # noqa: E402
import statements     # noqa: E402
import tables         # noqa: E402
import theme as theme_mod   # noqa: E402
import typeset as md_to_pdf   # noqa: E402

PERSIAN_ZERO = chr(0x06F0)
PERSIAN_FOUR = chr(0x06F4)
ARABIC_DECIMAL = chr(0x066B)
ARABIC_THOUSANDS = chr(0x066C)


class TestThemeResolution(unittest.TestCase):
    def test_defaults_are_monochrome_and_ltr(self):
        theme = theme_mod.resolve({})
        self.assertEqual(theme["direction"], "ltr")
        self.assertEqual(theme["digits"], "latin")
        self.assertEqual(theme["calendar"], "gregorian")
        self.assertTrue(theme["monochrome"])
        self.assertEqual(theme["accent"], theme["ink"])

    def test_persian_language_implies_rtl_jalali_persian_digits(self):
        theme = theme_mod.resolve({"language": "fa"})
        self.assertEqual(theme["direction"], "rtl")
        self.assertEqual(theme["calendar"], "jalali")
        self.assertEqual(theme["digits"], "persian")

    def test_explicit_locale_fields_win_over_derivation(self):
        theme = theme_mod.resolve({"language": "fa", "direction": "ltr",
                                   "digits": "latin", "calendar": "gregorian"})
        self.assertEqual(theme["direction"], "ltr")
        self.assertEqual(theme["digits"], "latin")
        self.assertEqual(theme["calendar"], "gregorian")

    def test_mood_selects_a_font_pairing(self):
        # theme["fonts"] is a superset of the mood's own table: resolve() adds
        # the derived label roles (persian_label/latin_label) that a mood need
        # not spell out itself.
        for mood, spec in theme_mod.MOODS.items():
            theme = theme_mod.resolve({"mood": mood})
            for role, family in spec["fonts"].items():
                self.assertEqual(theme["fonts"][role], family, "{}/{}".format(mood, role))
            for role, family in theme["fonts"].items():
                self.assertIn(family, fonts.FAMILIES, "{}/{}".format(mood, role))

    def test_unknown_mood_falls_back_to_the_default(self):
        theme = theme_mod.resolve({"mood": "chartreuse"})
        self.assertEqual(theme["mood"], theme_mod.DEFAULT_MOOD)

    def test_font_override_beats_the_mood_pairing(self):
        theme = theme_mod.resolve({"mood": "formal", "fonts": {"latin": "inter"}})
        self.assertEqual(theme["fonts"]["latin"], "inter")
        self.assertEqual(theme["fonts"]["persian"],
                         theme_mod.MOODS["formal"]["fonts"]["persian"])

    def test_overrides_beat_the_theme_file(self):
        theme = theme_mod.resolve({"mood": "formal"}, {"mood": "technical"})
        self.assertEqual(theme["mood"], "technical")

    def test_none_valued_overrides_are_ignored(self):
        theme = theme_mod.resolve({"mood": "formal"}, {"mood": None})
        self.assertEqual(theme["mood"], "formal")

    def test_naskh_family_gets_a_larger_size_and_more_leading(self):
        # "formal" no longer sets naskh as its TEXT face (that was the whole
        # point of the formal-register fix: a book naskh is a display face,
        # not a body one) -- "classic" is the mood that still reads its prose
        # in a naskh.
        naskh = theme_mod.resolve({"language": "fa", "mood": "classic"})
        sans = theme_mod.resolve({"language": "fa", "mood": "technical"})
        self.assertGreater(naskh["base_size_pt"], sans["base_size_pt"])
        self.assertGreater(naskh["line_height"], sans["line_height"])

    def test_rtl_body_is_larger_than_ltr_body(self):
        self.assertGreater(theme_mod.resolve({"language": "fa"})["base_size_pt"],
                           theme_mod.resolve({"language": "en"})["base_size_pt"])

    def test_contact_string_is_accepted_as_a_single_entry(self):
        self.assertEqual(theme_mod.resolve({"contact": "hello@example.com"})["contact"],
                         ["hello@example.com"])

    def test_page_margins_default_to_near_symmetric(self):
        # The margins are the measure now, so a wide default outer margin
        # would be the same double-subtraction this design fixed: a business
        # letter read single-sided on a screen has no binding edge to spare
        # room for. Bottom stays deeper than top for optical balance.
        page = theme_mod.resolve({})["page"]
        self.assertEqual(page["margin_outer_mm"], page["margin_inner_mm"])
        self.assertGreater(page["margin_bottom_mm"], page["margin_top_mm"])

    def test_page_margins_can_be_set_asymmetric(self):
        page = theme_mod.resolve(
            {"page": {"margin_inner_mm": 20, "margin_outer_mm": 40}})["page"]
        self.assertGreater(page["margin_outer_mm"], page["margin_inner_mm"])


class TestAccent(unittest.TestCase):
    def test_a_light_brand_colour_is_darkened_until_it_is_printable(self):
        theme = theme_mod.resolve({"accent": "#4da3ff"})
        self.assertFalse(theme["monochrome"])
        self.assertLess(theme_mod.contrast_on_white("#4da3ff"), 4.5)
        self.assertGreaterEqual(theme_mod.contrast_on_white(theme["accent"]), 4.5)

    def test_an_already_dark_accent_is_left_alone(self):
        self.assertEqual(theme_mod.print_accent("#000000"), "#000000")

    def test_an_invalid_accent_is_discarded_rather_than_raising(self):
        theme = theme_mod.resolve({"accent": "not-a-colour"})
        self.assertTrue(theme["monochrome"])

    def test_mixing_toward_white_lightens(self):
        self.assertGreater(theme_mod.contrast_on_white("#111111"),
                           theme_mod.contrast_on_white(theme_mod.mix_with_white("#111111", 0.8)))


class TestDigits(unittest.TestCase):
    def test_plain_numbers_become_persian(self):
        self.assertEqual(theme_mod.to_persian_digits("40"), PERSIAN_FOUR + PERSIAN_ZERO)

    def test_separators_between_digits_become_arabic_forms(self):
        converted = theme_mod.to_persian_digits("12,500.75")
        self.assertIn(ARABIC_THOUSANDS, converted)
        self.assertIn(ARABIC_DECIMAL, converted)
        self.assertNotIn(",", converted)

    def test_sentence_punctuation_is_untouched(self):
        self.assertTrue(theme_mod.to_persian_digits("cost 5. next").endswith(". next"))

    def test_latin_context_tokens_keep_ascii_digits(self):
        for token in ("v3.11.0", "https://example.com/a1", "user2@example.com",
                      "docs/2026/report.md", "SHA256"):
            self.assertEqual(theme_mod.to_persian_digits(token), token, token)

    def test_conversion_is_idempotent(self):
        once = theme_mod.to_persian_digits("2026 items")
        self.assertEqual(theme_mod.to_persian_digits(once), once)


class TestJalali(unittest.TestCase):
    def test_nowruz_is_the_first_of_the_first_month(self):
        self.assertEqual(theme_mod.to_jalali(2026, 3, 21), (1405, 1, 1))

    def test_day_before_nowruz_ends_the_previous_year(self):
        self.assertEqual(theme_mod.to_jalali(2026, 3, 20), (1404, 12, 29))

    def test_a_known_mid_year_date(self):
        self.assertEqual(theme_mod.to_jalali(2026, 9, 1), (1405, 6, 10))

    def test_formatting_applies_the_digit_system(self):
        import datetime
        text = theme_mod.format_date(datetime.date(2026, 9, 1), "jalali", "persian")
        self.assertNotIn("1", text)
        self.assertIn(PERSIAN_FOUR, text)

    def test_gregorian_iso_style(self):
        import datetime
        self.assertEqual(
            theme_mod.format_date(datetime.date(2026, 9, 1), "gregorian", "latin", "short"),
            "2026-09-01")


class TestFonts(unittest.TestCase):
    def test_every_catalogue_family_declares_at_least_one_face(self):
        for family_id, family in fonts.FAMILIES.items():
            self.assertTrue(family["faces"], family_id)
            for face in family["faces"]:
                self.assertTrue(face["url"].startswith("https://cdn.jsdelivr.net/npm/"))
                self.assertIn(fonts.FONTSOURCE_VERSION, face["url"])

    def test_every_mood_pairing_points_at_a_real_family(self):
        for mood, spec in theme_mod.MOODS.items():
            self.assertIn(spec["fonts"]["persian"], fonts.ARABIC_FAMILIES, mood)
            self.assertIn(spec["fonts"]["latin"], fonts.LATIN_FAMILIES, mood)
            self.assertIn(spec["fonts"]["mono"], fonts.MONO_FAMILIES, mood)

    def test_size_adjust_matches_x_heights(self):
        adjust = fonts.size_adjust("eb-garamond", "markazi-text")
        self.assertIsNotNone(adjust)
        self.assertLess(adjust, 100)

    def test_size_adjust_is_omitted_when_x_heights_already_agree(self):
        self.assertIsNone(fonts.size_adjust("geist", "noto-sans-arabic"))

    def test_size_adjust_is_none_for_an_unknown_family(self):
        self.assertIsNone(fonts.size_adjust("nonesuch", "vazirmatn"))

    def test_stack_ends_in_a_system_fallback(self):
        self.assertTrue(fonts.stack("geist", "vazirmatn").endswith("sans-serif"))

    def test_offline_face_css_degrades_instead_of_raising(self):
        self.assertIsInstance(fonts.face_css("nonesuch", offline=True), str)


class TestTransform(unittest.TestCase):
    def test_inline_code_keeps_ascii_digits_and_gains_a_direction(self):
        out = render.transform("<p>v <code>x = 42</code></p>", digits="persian")
        self.assertIn("x = 42", out)
        self.assertIn('dir="auto"', out)

    def test_code_blocks_are_left_exactly_as_written(self):
        out = render.transform("<pre><code>steps: [1, 10, 50]</code></pre>", digits="persian")
        self.assertIn("[1, 10, 50]", out)

    def test_prose_digits_are_converted(self):
        out = render.transform("<p>total 250 units</p>", digits="persian")
        self.assertNotIn("250", out)

    def test_latin_digits_are_left_alone_for_a_latin_document(self):
        out = render.transform("<p>total 250 units</p>", digits="latin")
        self.assertIn("250", out)

    def test_numeric_cells_are_marked_for_tabular_figures(self):
        out = render.transform("<table><tr><td>412,500</td><td>Revenue</td></tr></table>",
                               digits="latin")
        self.assertIn('<td class="num">412,500</td>', out)
        self.assertIn("<td>Revenue</td>", out)

    def test_attributes_and_entities_survive_the_round_trip(self):
        out = render.transform('<a href="https://example.com/a?x=1&amp;y=2">link</a>',
                               digits="persian")
        self.assertIn('href="https://example.com/a?x=1&amp;y=2"', out)

    def test_void_elements_are_not_given_a_closing_tag(self):
        self.assertNotIn("</br>", render.transform("<p>a<br>b</p>", digits="latin"))


class TestFrontmatter(unittest.TestCase):
    def test_metadata_is_split_from_the_body(self):
        meta, body = md_to_pdf.split_frontmatter("---\ntitle: Hello\n---\n# Body\n")
        self.assertEqual(meta["title"], "Hello")
        self.assertNotIn("title:", body)

    def test_a_document_without_frontmatter_is_all_body(self):
        meta, body = md_to_pdf.split_frontmatter("# Body\n")
        self.assertEqual(meta, {})
        self.assertEqual(body, "# Body\n")

    def test_an_unterminated_block_is_treated_as_content(self):
        text = "---\ntitle: Hello\n# Body\n"
        meta, body = md_to_pdf.split_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_quoted_values_are_unquoted(self):
        self.assertEqual(md_to_pdf.parse_frontmatter('version: "2.1"')["version"], "2.1")

    def test_the_leading_heading_is_lifted_as_the_title(self):
        title, body = md_to_pdf.lift_title("# The Title\n\nBody text.\n")
        self.assertEqual(title, "The Title")
        self.assertNotIn("# The Title", body)

    def test_a_heading_after_content_is_not_lifted(self):
        title, body = md_to_pdf.lift_title("Intro.\n\n# Later\n")
        self.assertIsNone(title)
        self.assertIn("# Later", body)


class TestDocumentAssembly(unittest.TestCase):
    """The stationery layer, built offline so no font is fetched."""

    def _css(self, theme):
        return render.build_css(theme, running_head="Head", offline=True)

    def test_rtl_puts_the_folio_on_the_outer_edge(self):
        css = self._css(theme_mod.resolve({"language": "fa"}))
        self.assertIn("@bottom-left", css)
        self.assertIn("@top-right", css)

    def test_ltr_mirrors_the_furniture(self):
        css = self._css(theme_mod.resolve({"language": "en"}))
        self.assertIn("@bottom-right", css)
        self.assertIn("@top-left", css)

    def test_the_first_page_carries_no_furniture(self):
        self.assertIn("@page :first", self._css(theme_mod.resolve({})))

    def test_the_inner_margin_follows_the_reading_direction(self):
        # Top/bottom pinned explicitly so this test does not depend on
        # whatever the default top/bottom margins happen to be.
        page = {"margin_top_mm": 26, "margin_bottom_mm": 32,
                "margin_inner_mm": 20, "margin_outer_mm": 50}
        rtl = self._css(theme_mod.resolve({"language": "fa", "page": page}))
        ltr = self._css(theme_mod.resolve({"language": "en", "page": page}))
        self.assertIn("margin: 26mm 20mm 32mm 50mm", rtl)
        self.assertIn("margin: 26mm 50mm 32mm 20mm", ltr)

    def test_arabic_script_labels_carry_no_tracking(self):
        css = self._css(theme_mod.resolve({"language": "fa"}))
        self.assertIn("letter-spacing: 0;", css)

    def test_latin_labels_keep_their_tracking(self):
        self.assertIn("letter-spacing: 0.16em",
                      self._css(theme_mod.resolve({"language": "en"})))

    def test_persian_documents_number_lists_in_persian(self):
        self.assertIn("list-style-type: persian",
                      self._css(theme_mod.resolve({"language": "fa"})))
        self.assertIn("counter(page, persian)",
                      self._css(theme_mod.resolve({"language": "fa"})))

    def test_page_numbers_can_be_switched_off(self):
        css = self._css(theme_mod.resolve({"page_numbers": False, "running_header": False}))
        self.assertNotIn("counter(page", css)

    def test_tables_have_no_vertical_rules_or_stripes(self):
        css = self._css(theme_mod.resolve({}))
        self.assertIn("border: none;", css)
        self.assertNotIn("nth-child(even)", css)

    def test_a_cover_is_built_when_the_document_has_a_title(self):
        theme = theme_mod.resolve({"name": "Acme"})
        html = render.build_html(theme, "<p>Body</p>", {"title": "Report"}, offline=True)
        self.assertIn('class="cover"', html)
        self.assertIn("Report", html)

    def test_a_letter_gets_a_letterhead_instead_of_a_cover(self):
        theme = theme_mod.resolve({"name": "Acme"})
        html = render.build_html(theme, "<p>Body</p>",
                                 {"title": "Notice", "kind": "letter"}, offline=True)
        self.assertIn('class="letterhead"', html)
        self.assertNotIn('class="cover"', html)

    def test_cover_never_suppresses_the_cover(self):
        theme = theme_mod.resolve({"cover": "never"})
        html = render.build_html(theme, "<p>Body</p>", {"title": "Report"}, offline=True)
        self.assertNotIn('class="cover"', html)

    def test_an_untitled_note_gets_neither(self):
        html = render.build_html(theme_mod.resolve({}), "<p>Body</p>", {}, offline=True)
        self.assertNotIn('class="cover"', html)
        self.assertNotIn('class="letterhead"', html)

    def test_the_document_declares_its_language_and_direction(self):
        html = render.build_html(theme_mod.resolve({"language": "fa"}),
                                 "<p>Body</p>", {}, offline=True)
        self.assertIn('lang="fa"', html)
        self.assertIn('dir="rtl"', html)

    def test_the_identity_becomes_the_pdf_author(self):
        html = render.build_html(theme_mod.resolve({"name": "Acme"}),
                                 "<p>Body</p>", {}, offline=True)
        self.assertIn('name="author" content="Acme"', html)

    def test_a_title_is_escaped_rather_than_injected(self):
        html = render.build_html(theme_mod.resolve({}), "<p>Body</p>",
                                 {"title": "<script>x</script>"}, offline=True)
        self.assertNotIn("<script>x</script>", html)


class TestThemeDiscovery(unittest.TestCase):
    def test_a_theme_is_found_by_walking_up_from_the_document(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".claude"))
            os.makedirs(os.path.join(root, "docs", "deep"))
            path = os.path.join(root, ".claude", "pdf-theme.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"name": "Found"}, handle)
            found = theme_mod.find_theme_file(os.path.join(root, "docs", "deep"))
            self.assertEqual(os.path.realpath(found), os.path.realpath(path))

    def test_no_theme_anywhere_returns_none_rather_than_raising(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            deep = os.path.join(root, "a", "b")
            os.makedirs(deep)
            found = theme_mod.find_theme_file(deep)
            self.assertTrue(found is None or os.path.isfile(found))


if __name__ == "__main__":
    unittest.main()


class TestWeightsAndLocales(unittest.TestCase):
    def test_mood_supplies_a_full_weight_set(self):
        theme = theme_mod.resolve({"mood": "modern"})
        self.assertEqual(set(theme["weights"]), set(theme_mod.WEIGHT_ROLES))
        # emphasis is a step above the body, never bold by default
        self.assertLess(theme["weights"]["emphasis"], 700)
        self.assertGreater(theme["weights"]["emphasis"], theme["weights"]["body"])

    def test_theme_overrides_one_weight_and_clamps_it(self):
        theme = theme_mod.resolve({"weights": {"body": 300, "emphasis": 5000}})
        self.assertEqual(theme["weights"]["body"], 300)
        self.assertEqual(theme["weights"]["emphasis"], 900)

    def test_css_carries_the_weights_and_the_table_size(self):
        theme = theme_mod.resolve({"weights": {"heading": 500}, "table": {"size_em": 0.8}})
        css = render.build_css(theme, offline=True)
        self.assertIn("--w-heading: 500;", css)
        self.assertIn("--w-emphasis:", css)
        self.assertIn("--table-size: 0.8em;", css)

    def test_locale_block_overrides_identity_per_language(self):
        raw = {"tagline": "Default line",
               "locales": {"fa": {"tagline": "Persian line"}, "en": {"tagline": "English line"}}}
        self.assertEqual(theme_mod.resolve(raw, {"language": "fa"})["tagline"], "Persian line")
        self.assertEqual(theme_mod.resolve(raw, {"language": "en-CA"})["tagline"], "English line")
        self.assertEqual(theme_mod.resolve(raw, {"language": "de"})["tagline"], "Default line")

    def test_locale_block_can_carry_a_second_register(self):
        raw = {"mood": "formal",
               "locales": {"en": {"mood": "modern", "weights": {"body": 300, "emphasis": 500},
                                  "fonts": {"latin": "inter"}, "table": {"size_em": 0.84}}}}
        en = theme_mod.resolve(raw, {"language": "en"})
        fa = theme_mod.resolve(raw, {"language": "fa"})
        self.assertEqual(en["mood"], "modern")
        self.assertEqual(en["weights"]["body"], 300)
        self.assertEqual(en["fonts"]["latin"], "inter")
        self.assertEqual(en["table"]["size_em"], 0.84)
        self.assertEqual(fa["mood"], "formal")
        self.assertEqual(fa["weights"]["body"], theme_mod.MOODS["formal"]["body_weight"])

    def test_table_size_is_clamped_to_a_sane_range(self):
        self.assertEqual(theme_mod.resolve({"table": {"size_em": 3}})["table"]["size_em"], 1.0)


class TestTableRegister(unittest.TestCase):
    NUMERIC = ('<table><thead><tr><th>Line</th><th>2025</th><th>2026</th></tr></thead><tbody>'
               '<tr><td>Revenue</td><td>8,961,560</td><td>12,219,070</td></tr>'
               '<tr><td>Costs</td><td>(3,143,143)</td><td>(4,087,436)</td></tr>'
               '<tr><td><strong>Profit</strong></td><td><strong>1,306,710</strong></td><td>3,068,224</td></tr>'
               '</tbody></table>')
    TEXT = ('<table><thead><tr><th>Item</th><th>Proposal</th></tr></thead><tbody>'
            '<tr><td><strong>Price</strong></td><td>Cash at closing</td></tr>'
            '<tr><td><strong>Term</strong></td><td>Two years</td></tr></tbody></table>')

    def test_numeric_columns_are_right_aligned_and_totals_ruled(self):
        out = tables.restyle(self.NUMERIC)
        self.assertIn('<table class="numeric keep">', out)
        self.assertIn('<th class="num">2025</th>', out)
        self.assertIn('<td class="num">8,961,560</td>', out)
        self.assertIn('<tr class="fin">', out)          # the bold last row is the final total
        self.assertEqual(out.count('class="tot"'), 0)

    def test_text_tables_keep_bold_labels_without_totals(self):
        out = tables.restyle(self.TEXT)
        self.assertIn('<table class="text keep">', out)
        self.assertNotIn('class="tot"', out)
        self.assertNotIn('class="fin"', out)
        self.assertNotIn('class="num"', out)

    def test_statement_tables_are_left_alone(self):
        html = '<table class="fs"><tbody><tr><td>x</td><td>1</td></tr></tbody></table>'
        self.assertEqual(tables.restyle(html), html)

    def test_author_classes_survive_and_numeric_marking_merges(self):
        html = '<table class="wide"><tbody><tr><td class="a">Total</td><td class="b">1,000</td></tr></tbody></table>'
        out = tables.restyle(html)
        self.assertIn('class="wide numeric keep"', out)
        self.assertIn('class="b num"', out)
        # the bidi/digit walker must merge too, never emit a second class attribute
        walked = render.transform(out)
        self.assertNotIn('class="num" class=', walked)
        self.assertEqual(walked.count('class="b num"'), 1)

    def test_long_tables_are_allowed_to_break(self):
        rows = "".join("<tr><td>r{}</td><td>{}</td></tr>".format(i, i) for i in range(40))
        out = tables.restyle("<table><tbody>{}</tbody></table>".format(rows))
        self.assertNotIn("keep", out)

    def test_dash_counts_as_a_figure(self):
        self.assertTrue(tables.is_numeric_text("—"))
        self.assertTrue(tables.is_numeric_text("(1,405,682)"))
        self.assertTrue(tables.is_numeric_text("CAD 8,808,648"))
        self.assertTrue(tables.is_numeric_text("1.6×"))
        self.assertFalse(tables.is_numeric_text("Total income"))
        self.assertFalse(tables.is_numeric_text("Q2 2026"))


class TestStatements(unittest.TestCase):
    def test_figures_print_like_a_statement(self):
        self.assertEqual(statements.fmt(1234567.4), "1,234,567")
        self.assertEqual(statements.fmt(-250.6), "(251)")
        self.assertEqual(statements.fmt(0.2), "—")
        self.assertEqual(statements.fmt(0.2, dash_zero=False), "")
        self.assertEqual(statements.fmt(None), "")

    def test_statement_table_carries_the_register(self):
        rows = [statements.Row("sec", "Income"),
                statements.Row("item", "Sales", [100.0, 200.0], depth=1, note=1),
                statements.Row("tot", "Total income", [100.0, 200.0]),
                statements.Row("fin", "Profit", [40.0, 0.0])]
        html = statements.statement_table(rows, ["A", "B"], first_header="CAD", blank_zero=[1])
        self.assertIn('<table class="fs">', html)
        self.assertIn('<tr class="sec"><td colspan="3">Income</td></tr>', html)
        self.assertIn('<tr class="item d1"><td>Sales<sup>1</sup></td>', html)
        self.assertIn('<tr class="fin"><td>Profit</td><td class="num">40</td><td class="num"></td></tr>', html)

    def test_unknown_row_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            statements.Row("bogus", "x")


class TestDeck(unittest.TestCase):
    def test_body_is_split_into_slides_at_rules_with_a_title_slide(self):
        theme = theme_mod.resolve({"name": "Northwind"})
        body = "<h2>One</h2><p>a</p><hr /><h2>Two</h2><p>b</p>"
        html = render.deck_html(theme, body, {"title": "Quarterly review", "date": "1 September 2026"})
        self.assertEqual(html.count('<section class="slide'), 3)
        self.assertIn('class="slide title"', html)
        self.assertIn("Northwind · Quarterly review", html)
        self.assertIn('<span class="n">03</span>', html)

class TestPageSize(unittest.TestCase):
    def test_page_is_letter_by_default(self):
        # The paper in a North American tray. Asserted on the @page block, not
        # on the theme dict, because the CSS is what Chrome actually prints.
        css = render.build_css(theme_mod.resolve({}), running_head="R", offline=True)
        self.assertIn("size: letter;", css)

    def test_page_size_is_overridable_to_a4(self):
        theme = theme_mod.resolve({}, {"page": {"size": "a4"}})
        self.assertIn("size: a4;",
                      render.build_css(theme, running_head="R", offline=True))
        # the override must not take the margins with it
        self.assertEqual(theme["page"]["margin_inner_mm"],
                         theme_mod.DEFAULT_PAGE["margin_inner_mm"])

    def test_cover_height_follows_the_paper(self):
        # The cover is one page tall; on the shorter paper it must be shorter,
        # or its foot breaks onto a near-blank second page.
        def cover_mm(size):
            css = render.build_css(theme_mod.resolve({}, {"page": {"size": size}}),
                                   running_head="R", offline=True)
            return float(re.search(r"\.cover \{[^}]*?height: ([\d.]+)mm", css,
                                   re.S).group(1))
        page = theme_mod.DEFAULT_PAGE
        chrome = page["margin_top_mm"] + page["margin_bottom_mm"]
        self.assertAlmostEqual(cover_mm("letter"),
                               theme_mod.PAPER_MM["letter"][1] - chrome, places=2)
        self.assertAlmostEqual(cover_mm("a4"),
                               theme_mod.PAPER_MM["a4"][1] - chrome, places=2)
        self.assertLess(cover_mm("letter"), cover_mm("a4"))

    def test_page_mm_reads_keywords_and_explicit_pairs(self):
        self.assertEqual(theme_mod.page_mm("Letter"), (215.9, 279.4))
        self.assertEqual(theme_mod.page_mm("A4"), (210.0, 297.0))
        self.assertEqual(theme_mod.page_mm("338.67mm 190.5mm"), (338.67, 190.5))
        self.assertIsNone(theme_mod.page_mm("nonesuch"))

    def test_page_size_flag_lowercases_and_reaches_the_theme(self):
        args = md_to_pdf.build_parser().parse_args(["in.md", "out.pdf",
                                                    "--page-size", "A4"])
        self.assertEqual(args.page_size, "a4")

class TestDeckPage(unittest.TestCase):
    def test_deck_css_sets_a_wide_page_and_no_folio(self):
        theme = theme_mod.resolve({})
        css = render.build_css(theme, running_head="Deck", offline=True, deck=True)
        self.assertIn("size: 338.67mm 190.5mm;", css)
        self.assertNotIn("counter(page", css)
        self.assertIn(".slide {", css)

