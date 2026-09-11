"""alias-guard: the user's own shorthand, mapped to the whole workflow it stands for.

Covers the three things that decide whether an alias is trustworthy: it fires on the
word and only on the word (script-aware boundaries, so a Persian trigger is not found
inside a longer Persian word), the table is read from the right files with the right
precedence and survives junk, and the hook says the same thing every time -- which
skill, run to the end. An alias marked ``"ship": true`` is checked end to end against
ship-guard, since that is what makes a personal word for shipping mean MERGED.

Arabic-script samples are written as \\u escapes so this file stays pure ASCII: KETAB
("book") and KETABI, a longer word that starts with it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import REPO, load  # noqa: E402

ya = load("scripts/yar_aliases.py", "yar_aliases")
SCRIPT = os.path.join(REPO, "scripts/alias-guard.py")

KETAB = "\u06a9\u062a\u0627\u0628"          # "book"
KETABI = KETAB + "\u06cc"                 # a longer word that starts with it
TWO_WORDS = KETAB + " \u062f\u0648\u0645"    # "second book": a spaced phrase


def write_table(directory, entries, name="yar-aliases.json"):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"aliases": entries}, fh, ensure_ascii=False)
    return path


def run_hook(prompt, env_extra, event="UserPromptSubmit"):
    """Run the hook the way Claude Code does and return (returncode, parsed stdout)."""
    env = dict(os.environ)
    env.pop("YAR_ALIASES", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(env_extra)
    payload = json.dumps({"hook_event_name": event, "prompt": prompt, "cwd": os.getcwd()})
    proc = subprocess.run([sys.executable, SCRIPT], input=payload, env=env,
                          capture_output=True, text=True)
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


def context_of(parsed):
    return parsed["hookSpecificOutput"]["additionalContext"]


class MatchesWholeWordsOnly(unittest.TestCase):
    def test_latin_word_not_matched_inside_another(self):
        self.assertTrue(ya.has_phrase("ok, ship it", "ship"))
        self.assertFalse(ya.has_phrase("a relationship", "ship"))

    def test_arabic_script_word_not_matched_inside_another(self):
        self.assertTrue(ya.has_phrase(KETAB + "!", KETAB))
        self.assertFalse(ya.has_phrase(KETABI, KETAB))

    def test_multi_word_phrase_tolerates_spacing(self):
        self.assertTrue(ya.has_phrase("... " + TWO_WORDS + " ...", TWO_WORDS))
        self.assertTrue(ya.has_phrase(TWO_WORDS.replace(" ", "   "), TWO_WORDS))
        self.assertTrue(ya.has_phrase("please DO the Nightly Tidy now", "nightly tidy"))

    def test_spelling_variants_fold_together(self):
        arabic_yeh = KETABI.replace("\u06cc", "\u064a")   # same word, Arabic keyboard
        self.assertTrue(ya.has_phrase(arabic_yeh, KETABI))
        self.assertTrue(ya.has_phrase("\u200c" + KETAB + "\u200c", KETAB))

    def test_empty_and_non_string_are_never_a_match(self):
        for text, phrase in (("", "ship"), ("ship", ""), (None, "ship"), ("ship", None)):
            self.assertFalse(ya.has_phrase(text, phrase))


class MatchesWhereThePhraseIsAnInstruction(unittest.TestCase):
    def test_short_prompt_counts_anywhere(self):
        self.assertTrue(ya.in_prompt("could you " + KETAB + " please", KETAB))

    def test_long_prompt_counts_at_the_edges_only(self):
        filler = "x" * 500
        self.assertTrue(ya.in_prompt(filler + " then " + KETAB, KETAB))
        self.assertTrue(ya.in_prompt(KETAB + " this: " + filler, KETAB))
        self.assertFalse(ya.in_prompt(filler + " " + KETAB + " " + filler, KETAB))


class ReadsTheTable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = {k: os.environ.get(k) for k in ("YAR_ALIASES", "CLAUDE_PROJECT_DIR")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_entries_are_normalized(self):
        os.environ["YAR_ALIASES"] = write_table(self.tmp, [
            {"words": "solo", "run": "yar:repo-sweep", "note": "n"},
            {"word": "pair", "skill": ["a:one", "a:two"], "ship": True},
            {"when": ["third"], "then": "do the thing"},
        ])
        entries = ya.load_aliases()
        self.assertEqual([e["words"] for e in entries], [["solo"], ["pair"], ["third"]])
        self.assertEqual(entries[1]["run"], ["a:one", "a:two"])
        self.assertTrue(entries[1]["ship"])
        self.assertEqual(entries[2]["do"], "do the thing")

    def test_a_trigger_with_nothing_to_run_is_not_an_alias(self):
        os.environ["YAR_ALIASES"] = write_table(self.tmp, [
            {"words": "orphan"}, {"run": "yar:repo-sweep"}, "junk", {"words": [], "do": "x"},
        ])
        self.assertEqual(ya.load_aliases(), [])

    def test_malformed_or_missing_files_yield_no_aliases(self):
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        os.environ["YAR_ALIASES"] = bad
        self.assertEqual(ya.load_aliases(), [])
        os.environ["YAR_ALIASES"] = os.path.join(self.tmp, "nope.json")
        self.assertEqual(ya.load_aliases(), [])
        self.assertEqual(ya.alias_files(), [])

    def test_a_bare_list_is_also_a_table(self):
        path = os.path.join(self.tmp, "list.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([{"words": "solo", "run": "yar:repo-sweep"}], fh)
        os.environ["YAR_ALIASES"] = path
        self.assertEqual(len(ya.load_aliases()), 1)

    def test_the_later_file_wins_on_the_same_word(self):
        first = write_table(self.tmp, [{"words": "go", "run": "a:first"}], "1.json")
        second = write_table(self.tmp, [{"words": "go", "run": "a:second"}], "2.json")
        os.environ["YAR_ALIASES"] = os.pathsep.join([first, second])
        matches = ya.match_aliases("go")
        self.assertEqual([e["run"] for e, _ in matches], [["a:second"]])

    def test_project_table_is_read_next_to_the_personal_one(self):
        project = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(project, ".claude"))
        write_table(os.path.join(project, ".claude"), [{"words": "go", "run": "a:proj"}])
        os.environ.pop("YAR_ALIASES", None)
        os.environ["CLAUDE_PROJECT_DIR"] = project
        self.assertIn(["a:proj"], [e["run"] for e in ya.load_aliases()])

    def test_off_disables_the_table(self):
        os.environ["YAR_ALIASES"] = "off"
        self.assertTrue(ya.disabled())
        self.assertEqual(ya.alias_files(), [])
        self.assertEqual(ya.load_aliases(), [])

    def test_one_entry_is_reported_once_however_many_words_hit(self):
        os.environ["YAR_ALIASES"] = write_table(self.tmp, [
            {"words": ["go", "run it"], "run": "a:one"}])
        self.assertEqual(len(ya.match_aliases("go, run it")), 1)


class TellsClaudeWhatToRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.table = write_table(self.tmp, [
            {"words": [KETAB, "nightly tidy"], "run": "yar:repo-sweep",
             "do": "start with the read-only scan", "note": "every repo, every plugin"}])

    def test_an_alias_prompt_names_the_skill_and_demands_the_whole_thing(self):
        code, parsed = run_hook("please " + KETAB, {"YAR_ALIASES": self.table})
        self.assertEqual(code, 0)
        ctx = context_of(parsed)
        self.assertIn("yar:repo-sweep", ctx)
        self.assertIn(KETAB, ctx)
        self.assertIn("start with the read-only scan", ctx)
        self.assertIn("every repo, every plugin", ctx)
        self.assertIn("not stopped half-way", ctx)

    def test_an_ordinary_prompt_is_left_alone(self):
        self.assertEqual(run_hook("what does this function do?",
                                  {"YAR_ALIASES": self.table}), (0, None))

    def test_the_word_inside_a_longer_word_is_not_an_alias(self):
        self.assertEqual(run_hook("about " + KETABI, {"YAR_ALIASES": self.table}), (0, None))

    def test_no_table_no_output(self):
        self.assertEqual(run_hook("please " + KETAB,
                                  {"YAR_ALIASES": os.path.join(self.tmp, "none.json")}),
                         (0, None))

    def test_disabled_by_env(self):
        self.assertEqual(run_hook("nightly tidy", {"YAR_ALIASES": "off"}), (0, None))

    def test_other_events_and_junk_never_produce_output(self):
        self.assertEqual(run_hook("nightly tidy", {"YAR_ALIASES": self.table},
                                  event="Stop"), (0, None))
        proc = subprocess.run([sys.executable, SCRIPT], input="{not json",
                              capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, ""))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def run_cli(self, args, env_extra):
        env = dict(os.environ)
        env.pop("YAR_ALIASES", None)
        env.update(env_extra)
        return subprocess.run([sys.executable, SCRIPT] + args, env=env,
                              capture_output=True, text=True)

    def test_list_shows_the_active_table_and_its_source(self):
        table = write_table(self.tmp, [{"words": "go", "run": "yar:repo-sweep",
                                        "ship": True, "note": "n"}])
        proc = self.run_cli(["list"], {"YAR_ALIASES": table})
        self.assertEqual(proc.returncode, 0)
        for expected in (table, "go", "yar:repo-sweep", "ship: yes", "note: n"):
            self.assertIn(expected, proc.stdout)

    def test_list_without_a_table_says_where_it_looked(self):
        proc = self.run_cli(["list"], {"YAR_ALIASES": os.path.join(self.tmp, "no.json")})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("No alias table found", proc.stdout)

    def test_the_example_is_a_valid_table(self):
        proc = self.run_cli(["example"], {})
        path = os.path.join(self.tmp, "yar-aliases.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(proc.stdout)
        os.environ["YAR_ALIASES"] = path
        try:
            entries = ya.load_aliases()
        finally:
            os.environ.pop("YAR_ALIASES", None)
        self.assertTrue(entries)
        self.assertTrue(any(e["ship"] for e in entries))


class ShipAliasesArmShipGuard(unittest.TestCase):
    """The point of ``"ship": true``: a personal word for shipping is bound by the same
    "not finished until MERGED" contract the word "ship" is."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = os.environ.get("YAR_ALIASES")

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("YAR_ALIASES", None)
        else:
            os.environ["YAR_ALIASES"] = self.saved

    def test_a_ship_alias_becomes_a_ship_word(self):
        sg = load("scripts/ship-guard.py", "ship_guard_alias")
        os.environ["YAR_ALIASES"] = write_table(self.tmp, [
            {"words": [KETAB], "run": "yar:git-workflow", "ship": True},
            {"words": ["nightly tidy"], "run": "yar:repo-sweep"}])
        self.assertIn(KETAB, sg.ship_words())
        self.assertTrue(sg.is_ship_prompt("ok " + KETAB))
        self.assertFalse(sg.is_ship_prompt(KETABI))          # not inside a longer word
        self.assertFalse(sg.is_ship_prompt("nightly tidy"))  # not a ship alias
        self.assertTrue(sg.is_ship_prompt("ship it"))        # the built-in still works


if __name__ == "__main__":
    unittest.main()
