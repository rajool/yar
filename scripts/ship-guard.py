#!/usr/bin/env python3
"""ship-guard -- make "ship" mean MERGED, mechanically.

One script, three Claude Code hook events (dispatched on ``hook_event_name``), plus a
small CLI. Hook mode reads the hook JSON on stdin and never crashes a session
(fail-open: any unexpected error -> exit 0, no output).

  UserPromptSubmit   The prompt says "ship" -> arm a per-session marker and hand Claude
                     the ship contract as additional context.
  PostToolUse(Bash)  While armed: remember every PR URL that ``gh pr create`` prints and
                     nudge, right there, that the job is not finished.
  Stop               While armed: check reality with git + gh. A recorded PR that is not
                     MERGED, a branch whose commits are in no merged PR, unpushed
                     commits, or a ship request that produced nothing at all -> refuse
                     to end the turn (``decision: block``) with the exact next commands.
                     At most MAX_BLOCKS times per ship request; then the turn may end.

  CLI  ship-guard.py release --marker PATH --reason TEXT   explicit, auditable escape hatch
       ship-guard.py release --session ID  --reason TEXT   (same, by session id)
       ship-guard.py status                                list markers

Why: "ship" is one command for the whole chain -- commit, push, PR, squash-merge -- yet
sessions kept stopping at ``gh pr create`` and reporting "shipped" with the PR still
open, with the written rule already in the skill. A rule the model reads is advice; a
Stop hook is a contract.

State: one JSON marker per session under $SHIP_GUARD_STATE_DIR, else
$XDG_STATE_HOME/yar/ship-guard, else ~/.local/state/yar/ship-guard. Markers older than
MARKER_TTL_DAYS are pruned. Bypass (rare): SHIP_GUARD=off (honored by the .sh wrapper).
Extra trigger words: SHIP_GUARD_WORDS="land it,merge it" (comma-separated), and any
alias in the user's table (yar_aliases.py) marked "ship": true.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import yar_aliases as ya
except Exception:            # pragma: no cover - fail-open, never trap a session
    ya = None

MAX_BLOCKS = 3
MARKER_TTL_DAYS = 3
GIT_TIMEOUT = 15
GH_TIMEOUT = 20
SHORT_PROMPT = 400   # a prompt this short is a command; "ship" anywhere in it counts
HEAD_WINDOW = 80     # in a longer prompt, "ship" counts near its start ...
TAIL_WINDOW = 200    # ... or near its end (where "then ship it" lives)

PR_URL_RE = re.compile(r"https://github\.com/[\w.\-]+/[\w.\-]+/pull/(\d+)")
CLAIM_RE = re.compile(r"\b(shipped|merged)\b", re.I)
GH_FIELDS = "state,number,url,headRefName,headRefOid,baseRefName,isDraft,autoMergeRequest"


# ---- trigger --------------------------------------------------------------------

def ship_words():
    """"ship", plus SHIP_GUARD_WORDS, plus every alias the user marked "ship": true --
    a personal word for shipping is bound by the same contract the word "ship" is."""
    words = ["ship"]
    extra = os.environ.get("SHIP_GUARD_WORDS", "").split(",")
    if ya is not None:
        try:
            extra += ya.ship_phrases()
        except Exception:
            pass             # no alias table, or an unreadable one: "ship" still works
    for w in extra:
        w = w.strip()
        if w and w.lower() not in [x.lower() for x in words]:
            words.append(w)
    return words


def _has_word(text, word):
    # Whole word only, so "shipping", "shipped", "relationship" never trigger, while
    # punctuation or another script ("ship!", "ship <Persian verb>") does. Boundaries
    # are script-aware -- a Persian trigger must not match inside a longer Persian
    # word, which [A-Za-z] lookarounds cannot see.
    if ya is not None:
        return ya.has_phrase(text, word)
    return re.search(r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])", text, re.I) is not None


def is_ship_prompt(text):
    """True when the prompt asks to ship: the word in a short prompt, or near the start
    or the end of a long one (a pasted document that merely mentions a ship does not)."""
    if not isinstance(text, str):
        return False
    t = text.strip()
    if not t:
        return False
    zones = [t] if len(t) <= SHORT_PROMPT else [t[:HEAD_WINDOW], t[-TAIL_WINDOW:]]
    return any(_has_word(z, w) for z in zones for w in ship_words())


def pr_urls(text):
    out = []
    if isinstance(text, str):
        for m in PR_URL_RE.finditer(text):
            if m.group(0) not in out:
                out.append(m.group(0))
    return out


def pr_number(url):
    m = PR_URL_RE.search(url or "")
    return int(m.group(1)) if m else None


def response_text(resp):
    """Flatten a tool_response (dict / str / list) into one searchable string."""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        return "\n".join(str(v) for v in resp.values() if isinstance(v, (str, int, float)))
    if isinstance(resp, list):
        return "\n".join(response_text(x) for x in resp)
    return ""


# ---- state ----------------------------------------------------------------------

def state_dir():
    d = os.environ.get("SHIP_GUARD_STATE_DIR")
    if not d:
        base = os.environ.get("XDG_STATE_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "state")
        d = os.path.join(base, "yar", "ship-guard")
    return d


def marker_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", str(session_id or ""))[:120] or "unknown"
    return os.path.join(state_dir(), safe + ".json")


def load_marker_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_marker(session_id):
    return load_marker_file(marker_path(session_id))


def save_marker_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def save_marker(session_id, data):
    save_marker_file(marker_path(session_id), data)


def prune_markers():
    try:
        cutoff = time.time() - MARKER_TTL_DAYS * 86400
        for name in os.listdir(state_dir()):
            p = os.path.join(state_dir(), name)
            if name.endswith(".json") and os.path.getmtime(p) < cutoff:
                os.remove(p)
    except Exception:
        pass


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def is_armed(marker):
    return bool(marker) and not marker.get("released")


def script_path():
    return os.path.realpath(__file__)


# ---- git / gh -------------------------------------------------------------------

def run(cmd, cwd=None, timeout=GIT_TIMEOUT):
    """Run a command; return (returncode, stdout, stderr). Never raises, never prompts."""
    if cwd and not os.path.isdir(cwd):
        return 1, "", "cwd missing"
    env = dict(os.environ)
    env.update({"GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1",
                "GIT_TERMINAL_PROMPT": "0"})
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # missing binary, timeout, ...
        return 1, "", str(e)


def git(cwd, *args):
    rc, out, _ = run(["git", "-C", cwd] + list(args))
    return out.strip() if rc == 0 else None


def repo_root(cwd):
    if not cwd or not os.path.isdir(cwd):
        return None
    return git(cwd, "rev-parse", "--show-toplevel")


def default_branch(root):
    ref = git(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if ref and "/" in ref:
        return ref.split("/", 1)[1]
    for cand in ("main", "master"):
        if git(root, "rev-parse", "--verify", "-q", "refs/remotes/origin/" + cand) is not None:
            return cand
    return "main"


def count_commits(root, rng):
    out = git(root, "rev-list", "--count", rng)
    try:
        return int(out)
    except (TypeError, ValueError):
        return None


def dirty_paths(root):
    out = git(root, "status", "--porcelain")
    return [ln for ln in (out or "").splitlines() if ln.strip()]


def gh_pr(cwd, ref=None):
    """PR facts for ``ref`` (URL / number / branch; None = the current branch).
    Returns the dict, {"state": "NONE"} when there is no PR, or None when unknown
    (no gh, offline, not a GitHub repo) -- unknown never blocks."""
    cmd = ["gh", "pr", "view"]
    if ref:
        cmd.append(str(ref))
    cmd += ["--json", GH_FIELDS]
    rc, out, err = run(cmd, cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
                       timeout=GH_TIMEOUT)
    if rc == 0:
        try:
            data = json.loads(out)
            return data if isinstance(data, dict) else None
        except ValueError:
            return None
    low = (err or "").lower()
    if "no pull requests found" in low or "could not resolve to a pullrequest" in low:
        return {"state": "NONE"}
    return None


# ---- assessment -----------------------------------------------------------------

def merge_commands(number, head_branch):
    n = str(number) if number else ""
    b = head_branch or "<branch>"
    return ("gh pr merge {n} --squash --delete-branch\n"
            "        inside a worktree: gh pr merge {n} --squash && git push origin --delete {b}\n"
            "        checks still running: gh pr merge {n} --squash --auto && gh pr checks {n} --watch\n"
            "        then verify: gh pr view {n} --json state   -> must print MERGED"
            ).format(n=n, b=b).replace("merge  --", "merge --").replace("checks  --", "checks --")


def open_issue(info):
    num = info.get("number")
    lines = ["PR #{} ({}) is OPEN -- not merged.".format(num, info.get("url"))]
    if info.get("isDraft"):
        lines.append("      -> it is a draft: gh pr ready {}".format(num))
    if info.get("autoMergeRequest"):
        lines.append("      -> auto-merge is armed; wait for it: gh pr checks {} --watch, "
                     "then re-check the state".format(num))
    lines.append("      -> " + merge_commands(num, info.get("headRefName")))
    return "\n".join(lines)


def closed_issue(info):
    num = info.get("number")
    return ("PR #{} ({}) was CLOSED without merging.\n      -> gh pr reopen {} && {}"
            .format(num, info.get("url"), num, merge_commands(num, info.get("headRefName"))))


def assess(cwd, marker):
    """Return (issues, notes, merged_any, unknown) for this ship request."""
    issues, notes = [], []
    merged_any = False
    unknown = False
    seen = set()

    # 1. PRs this session created (URLs captured from `gh pr create` output).
    for url in marker.get("prs") or []:
        info = gh_pr(cwd, url)
        if info is None:
            unknown = True
            continue
        st = info.get("state")
        if st == "NONE":
            continue
        num = info.get("number") or pr_number(url)
        seen.add(num)
        if st == "MERGED":
            merged_any = True
            notes.append("PR #{} is merged".format(num))
        elif st == "OPEN":
            issues.append(open_issue(info))
        elif st == "CLOSED":
            issues.append(closed_issue(info))

    # 2. The repository the session stands in (or stood in when "ship" was said).
    root = repo_root(cwd)
    if not root:
        remembered = marker.get("repo_root") or ""
        root = remembered if os.path.isdir(remembered) else None
    if root:
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD") or ""
        default = default_branch(root)
        dirty = dirty_paths(root)
        if branch in (default, "HEAD", ""):
            ahead = count_commits(root, "origin/{}..HEAD".format(default))
            if ahead:
                issues.append(
                    "{n} local commit(s) sit on {d} but not on origin/{d} -- work never goes "
                    "straight to {d}.\n      -> move them to a branch (git-workflow recipes), "
                    "then git push -u origin HEAD && gh pr create --fill && "
                    "gh pr merge --squash --delete-branch".format(n=ahead, d=default))
        else:
            info = gh_pr(root)
            if info is None:
                unknown = True
                notes.append("could not query GitHub for branch {} (gh unavailable?)".format(branch))
            elif info.get("state") == "NONE":
                base = "origin/" + default
                n = count_commits(root, base + "..HEAD")
                if n:
                    issues.append(
                        "branch {b} has {n} commit(s) beyond {base} and no pull request.\n"
                        "      -> git push -u origin HEAD && gh pr create --fill && "
                        "gh pr merge --squash --delete-branch\n"
                        "      then verify: gh pr view --json state   -> must print MERGED"
                        .format(b=branch, n=n, base=base))
            else:
                num = info.get("number")
                st = info.get("state")
                if st == "MERGED":
                    merged_any = True
                    if num not in seen:
                        notes.append("PR #{} for {} is merged".format(num, branch))
                    head = git(root, "rev-parse", "HEAD")
                    oid = info.get("headRefOid")
                    if head and oid and head != oid:
                        k = count_commits(root, "{}..HEAD".format(oid))
                        if k:
                            issues.append(
                                "{k} commit(s) on {b} were made AFTER PR #{p} merged -- they are "
                                "not on {d}.\n      -> git push -u origin HEAD && gh pr create --fill "
                                "&& gh pr merge --squash --delete-branch"
                                .format(k=k, b=branch, p=num, d=default))
                elif st == "OPEN":
                    if num not in seen:
                        issues.append(open_issue(info))
                    up = count_commits(root, "@{u}..HEAD")
                    if up:
                        issues.append("{} local commit(s) on {} are not pushed.\n      -> git push"
                                      .format(up, branch))
                elif st == "CLOSED" and num not in seen:
                    issues.append(closed_issue(info))
        if dirty:
            if merged_any or issues:
                notes.append("{} uncommitted path(s) remain in {} -- commit and ship them only "
                             "if they are this session's work".format(len(dirty), root))
            elif not unknown:
                issues.append(
                    "{n} uncommitted path(s) in {r} and nothing has been merged for this ship "
                    "request.\n      -> if they are this session's files: git add <paths> && "
                    "git commit -m \"type(scope): ...\" -- <paths>, then push -> PR -> merge\n"
                    "      -> if they belong to another session, leave them alone and release "
                    "the guard with that reason".format(n=len(dirty), r=root))
    return issues, notes, merged_any, unknown


def release_command(path):
    return "python3 \"{}\" release --marker \"{}\" --reason \"<why>\"".format(script_path(), path)


def block_message(marker, path, issues, notes, last_msg):
    armed_at = (marker.get("armed_at") or "")[11:16]
    if isinstance(last_msg, str) and CLAIM_RE.search(last_msg):
        head = ("ship-guard: your last message says it is shipped/merged, but the repository "
                "disagrees:")
    else:
        head = "ship-guard: \"ship\" was requested in this session{} and shipping is NOT complete:".format(
            " at " + armed_at if armed_at else "")
    lines = [head]
    for it in issues:
        lines.append("  * " + it)
    if notes:
        lines.append("  (also: " + "; ".join(notes) + ")")
    lines.append("Finish the chain now and verify MERGED before you report \"shipped\". The word "
                 "\"ship\" already authorized the merge -- never ask \"shall I merge?\".")
    lines.append("If shipping is genuinely impossible right now (a conflict that needs a human, a "
                 "change that needs review), tell the user why AND release the guard explicitly:")
    lines.append("  " + release_command(path))
    lines.append("(ship-guard block {}/{} -- after {} the turn may end regardless.)".format(
        marker.get("blocks"), MAX_BLOCKS, MAX_BLOCKS))
    return "\n".join(lines)


def contract_text(path):
    return (
        "ship-guard (yar): this prompt says \"ship\". Ship = the ENTIRE chain, ending in a MERGE:\n"
        "  1. commit this session's own files (explicit paths: git commit -m \"type(scope): ...\" -- <paths>)\n"
        "  2. git push -u origin HEAD\n"
        "  3. gh pr create --fill\n"
        "  4. gh pr merge --squash --delete-branch   (inside a worktree: gh pr merge --squash, then "
        "git push origin --delete <branch>; checks pending: add --auto, then gh pr checks --watch)\n"
        "  5. gh pr view --json state  -> MERGED. Only then say \"shipped\".\n"
        "\"PR opened\", \"ready to merge\", \"left for you to merge\" are NOT shipped -- that is the "
        "failure this guard exists for. The merge is pre-authorized by the word \"ship\": never ask "
        "\"shall I merge?\". A Stop hook will refuse to end this turn while a PR from this session is "
        "unmerged or commits are unpushed. If shipping is genuinely impossible (a conflict needing a "
        "human, a change needing review), say why AND release the guard: " + release_command(path)
    )


# ---- hook handlers --------------------------------------------------------------

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def handle_prompt(data):
    prompt = data.get("prompt") or data.get("user_input")
    if not is_ship_prompt(prompt):
        return
    sid = data.get("session_id") or ""
    cwd = data.get("cwd") or os.getcwd()
    prev = load_marker(sid) or {}
    marker = {
        "session_id": sid,
        "cwd": cwd,
        "repo_root": repo_root(cwd),
        "armed_at": now_iso(),
        "prompt": prompt.strip()[:200],
        "prs": list(prev.get("prs") or []),   # an earlier, still-open PR stays on the hook
        "blocks": 0,
        "released": None,
    }
    save_marker(sid, marker)
    prune_markers()
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                 "additionalContext": contract_text(marker_path(sid))}})


def handle_post_tool(data):
    if data.get("tool_name") != "Bash":
        return
    sid = data.get("session_id") or ""
    marker = load_marker(sid)
    if not is_armed(marker):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not isinstance(cmd, str):
        return
    created = re.search(r"\bgh\s+pr\s+create\b", cmd) is not None
    changed = False
    urls = pr_urls(response_text(data.get("tool_response"))) if created else []
    for u in urls:
        if u not in marker.setdefault("prs", []):
            marker["prs"].append(u)
            changed = True
    if re.search(r"\bgh\s+pr\s+merge\b", cmd):
        marker["merge_attempted_at"] = now_iso()
        changed = True
    if changed:
        save_marker(sid, marker)
    if created:
        n = str(pr_number(urls[0])) if urls else ""
        emit({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": (
            "ship-guard: PR {tag}created -- this is the MIDDLE of \"ship\", not the end. Next, in "
            "this same turn:\n"
            "  gh pr merge {n} --squash --delete-branch   (inside a worktree: gh pr merge {n} "
            "--squash, then git push origin --delete <branch>)\n"
            "  gh pr view {n} --json state               -> must print MERGED before you say "
            "\"shipped\".").format(tag="#" + n + " " if n else "", n=n).replace("merge  --", "merge --")
            .replace("view  --", "view --")}})


def handle_stop(data):
    sid = data.get("session_id") or ""
    marker = load_marker(sid)
    if not is_armed(marker):
        return
    if int(marker.get("blocks") or 0) >= MAX_BLOCKS:
        return
    cwd = data.get("cwd") or os.getcwd()
    issues, notes, merged_any, unknown = assess(cwd, marker)
    path = marker_path(sid)
    if not issues:
        if not unknown:
            marker["released"] = {"at": now_iso(), "by": "stop-hook",
                                  "reason": "verified: " + ("; ".join(notes) or "nothing left to ship")}
            save_marker(sid, marker)
        return   # allow the turn to end (unknown state is never held against the session)
    marker["blocks"] = int(marker.get("blocks") or 0) + 1
    marker["last_block_at"] = now_iso()
    save_marker(sid, marker)
    emit({"decision": "block",
          "reason": block_message(marker, path, issues, notes, data.get("last_assistant_message"))})


# ---- CLI ------------------------------------------------------------------------

def cli(argv):
    ap = argparse.ArgumentParser(
        prog="ship-guard.py",
        description="yar ship-guard: release the guard for a session (with a reason), or list markers.")
    sub = ap.add_subparsers(dest="cmd")
    rel = sub.add_parser("release", help="let the current turn end although the ship is unfinished")
    rel.add_argument("--marker", help="marker file path (printed in the block message)")
    rel.add_argument("--session", help="session id (alternative to --marker)")
    rel.add_argument("--reason", required=True,
                     help="why shipping cannot finish now -- repeat it to the user")
    sub.add_parser("status", help="list ship-guard markers and their state")
    args = ap.parse_args(argv)

    if args.cmd == "release":
        reason = (args.reason or "").strip()
        if len(reason) < 8:
            sys.stderr.write("ship-guard: --reason must say why (at least a short sentence).\n")
            return 2
        path = args.marker or (marker_path(args.session) if args.session else None)
        if not path:
            sys.stderr.write("ship-guard: pass --marker PATH or --session ID.\n")
            return 2
        marker = load_marker_file(path)
        if marker is None:
            sys.stderr.write("ship-guard: no marker at {}\n".format(path))
            return 1
        marker["released"] = {"at": now_iso(), "by": "release command", "reason": reason}
        save_marker_file(path, marker)
        print("ship-guard released for session {}.".format(marker.get("session_id")))
        print("  reason: " + reason)
        print("  A released ship is an UNFINISHED ship: state this reason to the user in your reply, "
              "with what remains to be done.")
        return 0

    if args.cmd == "status":
        d = state_dir()
        rows = []
        try:
            names = sorted(n for n in os.listdir(d) if n.endswith(".json"))
        except OSError:
            names = []
        for n in names:
            m = load_marker_file(os.path.join(d, n)) or {}
            rows.append("{}  armed {}  blocks {}  prs {}  {}".format(
                (m.get("session_id") or n)[:12], m.get("armed_at"), m.get("blocks"),
                len(m.get("prs") or []),
                "released: " + str((m.get("released") or {}).get("reason")) if m.get("released") else "ARMED"))
        print("\n".join(rows) if rows else "ship-guard: no markers in {}".format(d))
        return 0

    ap.print_help()
    return 0


def main():
    argv = sys.argv[1:]
    if argv:
        sys.exit(cli(argv))
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)
    event = data.get("hook_event_name")
    try:
        if event == "UserPromptSubmit":
            handle_prompt(data)
        elif event == "PostToolUse":
            handle_post_tool(data)
        elif event == "Stop":
            handle_stop(data)
    except Exception:
        pass   # fail-open: a guard bug must never trap a session
    sys.exit(0)


if __name__ == "__main__":
    main()
