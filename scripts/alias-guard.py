#!/usr/bin/env python3
"""alias-guard -- your own shorthand, run as the whole workflow it stands for.

A word you use every day for a routine ("wrap up", a nickname for the release
dance, the same phrase in your own language) has to survive the trip from prompt to
procedure. Left to memory it degrades: sometimes the skill runs, sometimes an
improvised half of it does, and the difference only shows up afterwards. So the
mapping lives in a file you own, and this hook reads it on every prompt.

  UserPromptSubmit   The prompt uses one of your alias words -> hand Claude the
                     mapping as additional context: which skill to invoke, what the
                     alias covers, and that it is to be finished, not approximated.

The alias table is yours (``~/.claude/yar-aliases.json`` or the project's
``.claude/yar-aliases.json``); yar ships none, so this hook is silent until you
write one. Format, precedence and matching rules: ``yar_aliases.py``.
An alias with ``"ship": true`` is additionally adopted by ship-guard, so a personal
word for shipping inherits the "not finished until it is MERGED" Stop contract.

  CLI  alias-guard.py list       the active table and the files it came from
       alias-guard.py example    a starter table to redirect into place

Mechanism: hook JSON on stdin, JSON on stdout, always exit 0. Fail-open: no table,
an unreadable one, or any unexpected error -> no output, session untouched.
Bypass (rare): ALIAS_GUARD=off (honored by the .sh wrapper).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import yar_aliases as ya
except Exception:            # pragma: no cover - fail-open, never trap a session
    ya = None

EXAMPLE = {
    "aliases": [
        {"words": ["nightly tidy", "wrap the day"],
         "run": "yar:repo-sweep",
         "note": "every repo reconciled, stale branches and worktrees pruned"},
        {"words": ["send it"],
         "run": "yar:git-workflow",
         "ship": True,
         "do": "run the whole chain: commit, push, open the PR, squash-merge it",
         "note": "not finished at `gh pr create` -- finished when main has the change"},
    ]
}


def context_text(matches):
    """What Claude is told when a prompt uses an alias: the mapping, and that the
    named procedure is to be run in full."""
    lines = ["yar alias -- this prompt uses one of the user's standing shorthands.",
             "It is an instruction, not a passing mention:"]
    for entry, word in matches:
        lines.append("")
        lines.append('  "%s"' % word)
        for skill in entry["run"]:
            lines.append("      -> invoke the `%s` skill (Skill tool) and carry it "
                         "through to the end." % skill)
        if entry["do"]:
            lines.append("      -> %s" % entry["do"])
        if entry["note"]:
            lines.append("      (%s)" % entry["note"])
    lines += ["",
              "Run the named procedure as the skill defines it -- not a shortened",
              "version reconstructed from memory, and not stopped half-way. If it",
              "cannot be run right now, say so plainly rather than quietly doing",
              "something else instead."]
    return "\n".join(lines)


def handle_prompt(data):
    prompt = data.get("prompt") or data.get("user_input")
    if not isinstance(prompt, str) or not prompt.strip():
        return
    matches = ya.match_aliases(prompt, cwd=data.get("cwd"))
    if not matches:
        return
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context_text(matches)}}) + "\n")
    sys.stdout.flush()


def cmd_list(args):
    files = ya.alias_files(args.cwd)
    if ya.disabled():
        print("aliases are disabled for this session (YAR_ALIASES=off)")
        return 0
    if not files:
        print("No alias table found. Looked for:")
        print("  $YAR_ALIASES (unset)" if not os.environ.get("YAR_ALIASES")
              else "  $YAR_ALIASES=%s" % os.environ["YAR_ALIASES"])
        print("  ~/.claude/%s" % ya.FILE_NAME)
        print("  <project>/.claude/%s" % ya.FILE_NAME)
        print("Write one:  alias-guard.py example > ~/.claude/%s" % ya.FILE_NAME)
        return 0
    entries = ya.load_aliases(args.cwd)
    print("Alias table (%d %s from %d file%s):"
          % (len(entries), "entry" if len(entries) == 1 else "entries",
             len(files), "" if len(files) == 1 else "s"))
    for path in files:
        print("  <- %s" % path)
    for e in entries:
        print("")
        print("  %s" % " | ".join(e["words"]))
        for skill in e["run"]:
            print("      run:  %s" % skill)
        if e["do"]:
            print("      do:   %s" % e["do"])
        if e["ship"]:
            print("      ship: yes (also arms ship-guard)")
        if e["note"]:
            print("      note: %s" % e["note"])
    return 0


def cmd_example(_args):
    print(json.dumps(EXAMPLE, indent=2, ensure_ascii=False))
    return 0


def cli(argv):
    ap = argparse.ArgumentParser(
        prog="alias-guard.py",
        description="Your own shorthand, mapped to the whole workflow it stands for.")
    sub = ap.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="show the active alias table and its sources")
    p_list.add_argument("--cwd", default=None, help="project directory to resolve")
    p_list.set_defaults(func=cmd_list)
    p_ex = sub.add_parser("example", help="print a starter alias table")
    p_ex.set_defaults(func=cmd_example)
    args = ap.parse_args(argv)
    if getattr(args, "func", None):
        return args.func(args)
    ap.print_help()
    return 0


def main():
    if ya is None:
        sys.exit(0)
    argv = sys.argv[1:]
    if argv:
        sys.exit(cli(argv))
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)
    try:
        if data.get("hook_event_name") == "UserPromptSubmit":
            handle_prompt(data)
    except Exception:
        pass    # fail-open: a guard bug must never trap a session
    sys.exit(0)


if __name__ == "__main__":
    main()
