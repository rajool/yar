#!/usr/bin/env bash
# sweep-scan.sh -- read-only audit for the yar:repo-sweep skill.
#
# Discovers every local git repo under the scan roots and prints a typed,
# tab-separated audit: per-checkout sync state (same table daily driving needs),
# plus the sweep-specific facts -- local/remote branch staleness (squash-merge
# aware), worktree containment, orphaned worktree directories, a primary
# checkout parked off the default branch, and plugin manifest version drift.
#
# Read-only by design: it never touches a working tree, branch, stash, or
# remote; --fetch only updates remote-tracking refs so ahead/behind/gone and
# merged-ness are judged against current remote state. All mutation decisions
# belong to the skill (see reference/playbook.md), never to this script.
# macOS bash 3.2 compatible (no mapfile, no associative arrays, no ${var,,}).
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: sweep-scan.sh [--fetch] [ROOT ...]

Print a typed, tab-separated audit of every git repo under the scan roots.

Roots, first source that yields anything wins:
  1. ROOT arguments
  2. $DAILY_REPO_ROOTS -- colon-separated directories (~ allowed)
  3. whichever of these exist:
     ~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer

Options:
  --fetch    run `git fetch --all --prune` per repo before reading state
             (network; required for trustworthy gone/behind/merged signals)
  -h|--help  this text

Scan depth below each root: $DAILY_SCAN_DEPTH (default 4).

Row types (first column):
  repo | worktree   one line per checkout:
                    KIND PATH BRANCH DIRTY AHEAD BEHIND UPSTREAM STASHES
                    (UPSTREAM: ok | gone | none; gone = deleted on the remote)
  WT       linked worktree sweep facts:
           WT REPO PATH HEAD CONTAINED DIRTY PRUNABLE
           (HEAD = branch name or DETACHED@sha; CONTAINED = HEAD is an
            ancestor of origin/DEFAULT; PRUNABLE = git already lost the dir)
  BRANCH   local branch classification:
           BRANCH REPO NAME STATE UPSTREAM CHECKEDOUT LASTCOMMIT
           STATE: DEFAULT(behind=N) | MERGED | EQUIV | UNIQUE(N)
           (MERGED = ancestor of origin/DEFAULT; EQUIV = every commit is
            patch-equivalent to one already there -- the squash-merge signal;
            UNIQUE = N commits whose content is nowhere on origin/DEFAULT)
  RBRANCH  remote branch staleness:
           RBRANCH REPO NAME UNIQUE LASTCOMMIT
  ORPHAN   directory under REPO/.claude/worktrees not registered as a
           worktree (typically left behind by a repo rename):
           ORPHAN REPO PATH GITDIR_TARGET REPAIRABLE SIZE_KB FILES
  PARKED   primary checkout is not on the default branch:
           PARKED REPO CURRENT_BRANCH STATE DEFAULT DEFAULT_BEHIND
  PLUGDEV  plugin dev clone manifest versions:
           PLUGDEV REPO NAME PLUGIN_JSON_VERSION MARKETPLACE_VERSION
  NOREMOTE repo has no origin default branch to judge against; only the
           checkout row is emitted.
  SUMMARY  totals, last line.
EOF
}

FETCH=0
arg_roots=""
for arg in "$@"; do
  case "$arg" in
    --fetch) FETCH=1 ;;
    -h|--help) usage; exit 0 ;;
    *) arg_roots="${arg_roots}${arg}"$'\n' ;;
  esac
done

expand_tilde() {
  # Replace a leading literal tilde with $HOME ("~" or "~/path"). We test the
  # first character with parameter expansion rather than a "~"-glob to avoid a
  # false SC2088 (the linter reads a quoted-tilde glob as an un-expanding tilde).
  arg="$1"
  if [ "$arg" = "~" ]; then
    printf '%s' "$HOME"
  elif [ "${arg#\~/}" != "$arg" ]; then   # starts with "~/"
    printf '%s/%s' "$HOME" "${arg#\~/}"
  else
    printf '%s' "$arg"
  fi
}

# Lowercase a path for comparisons: macOS filesystems are case-insensitive, so
# the same worktree can be registered under one letter case and visited under
# another (an uppercase vs lowercase home directory segment, for example).
lc() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# Resolve the root list (explicit=1 means the user named them, so warn on misses).
explicit=1
if [ -n "$arg_roots" ]; then
  src="$arg_roots"
elif [ -n "${DAILY_REPO_ROOTS:-}" ]; then
  src="$(printf '%s' "$DAILY_REPO_ROOTS" | tr ':' '\n')"$'\n'
else
  explicit=0
  src=""
  for d in "$HOME/Projects" "$HOME/Code" "$HOME/code" "$HOME/repos" \
           "$HOME/src" "$HOME/dev" "$HOME/Developer"; do
    src="${src}${d}"$'\n'
  done
fi

roots=""
while IFS= read -r r; do
  [ -z "$r" ] && continue
  r="$(expand_tilde "$r")"
  if [ -d "$r" ]; then
    roots="${roots}${r}"$'\n'
  elif [ "$explicit" = 1 ]; then
    printf 'sweep-scan: root not found, skipping: %s\n' "$r" >&2
  fi
done <<EOF
$src
EOF

if [ -z "$roots" ]; then
  {
    echo 'sweep-scan: no scan roots found.'
    echo 'Set DAILY_REPO_ROOTS to a colon-separated list of directories that'
    echo 'contain your git repos, e.g. DAILY_REPO_ROOTS=~/Projects:~/Clients'
  } >&2
  exit 1
fi

DEPTH="${DAILY_SCAN_DEPTH:-4}"
case "$DEPTH" in
  ''|*[!0-9]*) echo 'sweep-scan: DAILY_SCAN_DEPTH must be a positive integer' >&2; exit 1 ;;
esac

printf 'sweep-scan: scanning (depth %s):\n' "$DEPTH" >&2
printf '%s' "$roots" | sed 's/^/  /' >&2

# Discovery: a primary repo is a directory that CONTAINS a .git directory.
# Linked worktrees have a .git FILE, so find(1) skips them here and they are
# enumerated through their parent repo's `git worktree list` instead -- each
# checkout appears exactly once. Package/vendor trees are pruned for speed.
repos_raw=""
while IFS= read -r gitdir; do
  [ -z "$gitdir" ] && continue
  repo="${gitdir%/.git}"
  repo="$(cd "$repo" 2>/dev/null && pwd -P)" || continue
  repos_raw="${repos_raw}${repo}"$'\n'
done < <(
  while IFS= read -r root; do
    [ -z "$root" ] && continue
    find "$root" -maxdepth "$DEPTH" \
      \( -type d \( -name node_modules -o -name .venv -o -name venv \
         -o -name vendor -o -name Pods -o -name .Trash -o -name Library \
         -o -name .terraform -o -name .tox \) -prune \) \
      -o -type d -name .git -prune -print 2>/dev/null
  done <<EOF
$roots
EOF
)

repos="$(printf '%s' "$repos_raw" | sort -u)"
if [ -z "$repos" ]; then
  echo 'sweep-scan: no git repos found under the scanned roots.' >&2
  exit 1
fi

total_repos=0; total_wt=0; dirty_n=0; ahead_n=0; behind_n=0
gone_n=0; stash_n=0; fetch_fail=0
stale_local=0; stale_remote=0; orphan_n=0; parked_n=0; drift_n=0

# Print one status line for a checkout and update the summary counters.
# One `git status --porcelain=v2 --branch` call gives branch, upstream state,
# ahead/behind, and the dirty count; `gone` = upstream configured but its
# remote-tracking ref vanished (the branch.ab line disappears).
emit_checkout() {
  kind="$1"; path="$2"
  branch="?"; upstream="none"; ahead="-"; behind="-"; dirty=0
  while IFS= read -r line; do
    case "$line" in
      '# branch.head '*) branch="${line#\# branch.head }" ;;
      '# branch.upstream '*) upstream="gone" ;;
      '# branch.ab '*)
        upstream="ok"
        rest="${line#\# branch.ab +}"
        ahead="${rest%% *}"
        behind="${rest#* -}"
        ;;
      '#'*) : ;;
      *) [ -n "$line" ] && dirty=$((dirty + 1)) ;;
    esac
  done < <(git -C "$path" status --porcelain=v2 --branch 2>/dev/null)
  [ "$branch" = "(detached)" ] && branch="DETACHED"
  stashes="$(git -C "$path" stash list 2>/dev/null | grep -c . || true)"
  [ "$dirty" -gt 0 ] && dirty_n=$((dirty_n + 1))
  if [ "$upstream" = "ok" ]; then
    [ "$ahead" != "-" ] && [ "$ahead" -gt 0 ] && ahead_n=$((ahead_n + 1))
    [ "$behind" != "-" ] && [ "$behind" -gt 0 ] && behind_n=$((behind_n + 1))
  fi
  [ "$upstream" = "gone" ] && gone_n=$((gone_n + 1))
  [ "${stashes:-0}" -gt 0 ] && stash_n=$((stash_n + 1))
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$kind" "$path" "$branch" "$dirty" "$ahead" "$behind" "$upstream" "$stashes"
}

# Classify one local branch against origin/<default>: MERGED (ancestor),
# EQUIV (every commit patch-equivalent to one upstream -- how a squash-merged
# or re-landed branch looks), or UNIQUE(N) (N commits whose content is nowhere
# on the default branch). Sets $state.
classify_branch() {
  _repo="$1"; _branch="$2"; _def="$3"
  if git -C "$_repo" merge-base --is-ancestor "$_branch" "origin/$_def" 2>/dev/null; then
    state="MERGED"
    return
  fi
  uniq_ct="$(git -C "$_repo" cherry "origin/$_def" "$_branch" 2>/dev/null | grep -c '^+' || true)"
  if [ "${uniq_ct:-0}" -eq 0 ]; then
    state="EQUIV"
  else
    state="UNIQUE(${uniq_ct})"
  fi
}

# Emit the sweep-specific rows for one repo (assumes fetch already happened).
sweep_repo() {
  repo="$1"

  # Default branch: origin/HEAD if the clone knows it, else origin/main|master.
  def="$(git -C "$repo" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)"
  def="${def#origin/}"
  if [ -z "$def" ]; then
    for cand in main master; do
      if git -C "$repo" rev-parse -q --verify "refs/remotes/origin/$cand" >/dev/null 2>&1; then
        def="$cand"; break
      fi
    done
  fi
  if [ -z "$def" ]; then
    printf 'NOREMOTE\t%s\n' "$repo"
    return
  fi

  # Walk `worktree list --porcelain`: collect registered paths (lowercased,
  # for the orphan diff below) and which branches are checked out anywhere,
  # and emit one WT row per LINKED worktree. The primary checkout is the
  # first entry; it gets a PARKED row instead of a WT row.
  reg_lc=""; checked_out=" "
  entry_i=0; wt_path=""; wt_head=""; wt_branch=""; wt_prunable="no"
  flush_wt() {
    [ -z "$wt_path" ] && return
    entry_i=$((entry_i + 1))
    wt_real="$(cd "$wt_path" 2>/dev/null && pwd -P)" || wt_real="$wt_path"
    reg_lc="${reg_lc}$(lc "$wt_real")"$'\n'
    [ -n "$wt_branch" ] && checked_out="${checked_out}${wt_branch} "
    if [ "$entry_i" -gt 1 ]; then
      if [ -n "$wt_branch" ]; then
        head_desc="$wt_branch"
      else
        head_desc="DETACHED@$(printf '%.7s' "$wt_head")"
      fi
      if git -C "$repo" merge-base --is-ancestor "$wt_head" "origin/$def" 2>/dev/null; then
        contained="yes"
      else
        contained="no"
      fi
      wt_dirty="$(git -C "$wt_path" status --porcelain 2>/dev/null | grep -c . || true)"
      printf 'WT\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$repo" "$wt_path" "$head_desc" "$contained" "${wt_dirty:-0}" "$wt_prunable"
    fi
    wt_path=""; wt_head=""; wt_branch=""; wt_prunable="no"
  }
  while IFS= read -r line; do
    case "$line" in
      'worktree '*) wt_path="${line#worktree }" ;;
      'HEAD '*) wt_head="${line#HEAD }" ;;
      'branch '*) wt_branch="${line#branch refs/heads/}" ;;
      prunable*) wt_prunable="yes" ;;
      '') flush_wt ;;
    esac
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null; printf '\n')
  flush_wt

  # Local branches vs origin/<default>. Split on tabs by hand: `read` with a
  # whitespace IFS collapses runs of tabs, so empty fields (no upstream, no
  # track) would shift the later columns into the wrong variables.
  while IFS= read -r bline; do
    [ -z "$bline" ] && continue
    b="${bline%%$'\t'*}"; brest="${bline#*$'\t'}"
    up="${brest%%$'\t'*}"; brest="${brest#*$'\t'}"
    track="${brest%%$'\t'*}"; date="${brest#*$'\t'}"
    if [ -z "$up" ]; then
      upstate="none"
    elif printf '%s' "$track" | grep -q 'gone'; then
      upstate="gone"
    else
      upstate="ok"
    fi
    case "$checked_out" in
      *" $b "*) co="yes" ;;
      *) co="no" ;;
    esac
    if [ "$b" = "$def" ]; then
      def_behind="$(git -C "$repo" rev-list --count "$b..origin/$def" 2>/dev/null || echo '?')"
      state="DEFAULT(behind=${def_behind})"
    else
      classify_branch "$repo" "$b" "$def"
      case "$state" in MERGED|EQUIV) stale_local=$((stale_local + 1)) ;; esac
    fi
    printf 'BRANCH\t%s\t%s\t%s\t%s\t%s\t%s\n' "$repo" "$b" "$state" "$upstate" "$co" "$date"
  done < <(git -C "$repo" for-each-ref refs/heads \
             --format='%(refname:short)%09%(upstream:short)%09%(upstream:track)%09%(committerdate:short)' 2>/dev/null)

  # Remote branches other than the default: UNIQUE=0 means nothing on them
  # that origin/<default> does not already have (deletion candidates -- the
  # skill still checks for an open PR before proposing deletion).
  while IFS= read -r rline; do
    [ -z "$rline" ] && continue
    ref="${rline%%$'\t'*}"; date="${rline#*$'\t'}"
    rb="${ref#refs/remotes/origin/}"
    [ "$rb" = "HEAD" ] && continue
    [ "$rb" = "$def" ] && continue
    r_uniq="$(git -C "$repo" cherry "origin/$def" "$ref" 2>/dev/null | grep -c '^+' || true)"
    [ "${r_uniq:-0}" -eq 0 ] && stale_remote=$((stale_remote + 1))
    printf 'RBRANCH\t%s\t%s\t%s\t%s\n' "$repo" "$rb" "${r_uniq:-0}" "$date"
  done < <(git -C "$repo" for-each-ref refs/remotes/origin \
             --format='%(refname)%09%(committerdate:short)' 2>/dev/null)

  # Orphaned worktree directories: dirs under .claude/worktrees (where the
  # Claude Code harness parks per-session worktrees) that git no longer lists.
  # The classic cause is a renamed parent repo: the dir's .git FILE points at
  # <old-repo-path>/.git/worktrees/<id>, so every git command inside fails and
  # `worktree list` cannot see it. REPAIRABLE=yes means the admin dir still
  # exists (a `git worktree repair` candidate); no means it is a dead plain
  # directory (trash candidate -- after a human look, since git cannot say
  # whether it holds unsaved work).
  wtroot="$repo/.claude/worktrees"
  if [ -d "$wtroot" ]; then
    for d in "$wtroot"/*/; do
      [ -d "$d" ] || continue
      d="${d%/}"
      d_real="$(cd "$d" 2>/dev/null && pwd -P)" || d_real="$d"
      case "$reg_lc" in
        *"$(lc "$d_real")"$'\n'*) continue ;;
      esac
      orphan_n=$((orphan_n + 1))
      target="$(sed -n 's/^gitdir: //p' "$d/.git" 2>/dev/null | head -1)"
      [ -z "$target" ] && target="(no .git file)"
      if [ -d "$target" ]; then repairable="yes"; else repairable="no"; fi
      size_kb="$(du -sk "$d" 2>/dev/null | cut -f1)"
      files="$(find "$d" -type f 2>/dev/null | grep -c . || true)"
      printf 'ORPHAN\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$repo" "$d" "$target" "$repairable" "${size_kb:-?}" "${files:-?}"
    done
  fi

  # Primary checkout parked off the default branch.
  cur="$(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null || echo DETACHED)"
  if [ "$cur" != "$def" ]; then
    parked_n=$((parked_n + 1))
    if [ "$cur" = "DETACHED" ]; then
      state="DETACHED"
    else
      classify_branch "$repo" "$cur" "$def"
    fi
    def_behind="$(git -C "$repo" rev-list --count "$def..origin/$def" 2>/dev/null || echo '?')"
    printf 'PARKED\t%s\t%s\t%s\t%s\t%s\n' "$repo" "$cur" "$state" "$def" "$def_behind"
  fi

  # Plugin dev clone: compare plugin.json's version with the matching entry in
  # marketplace.json (if present) -- drift here means a release was cut without
  # updating the marketplace manifest, so installs serve a stale version.
  if [ -f "$repo/.claude-plugin/plugin.json" ] && command -v python3 >/dev/null 2>&1; then
    plug_row="$(python3 - "$repo" <<'PY' 2>/dev/null
import json, os, sys
repo = sys.argv[1]
p = os.path.join(repo, ".claude-plugin", "plugin.json")
m = os.path.join(repo, ".claude-plugin", "marketplace.json")
try:
    d = json.load(open(p))
except Exception:
    sys.exit(0)
name = d.get("name", "?")
pv = d.get("version", "?")
mv = "-"
if os.path.exists(m):
    try:
        md = json.load(open(m))
        for e in md.get("plugins", []):
            if e.get("name") == name:
                # No version field on the entry is legitimate (plugin.json is
                # then the only source of truth) -- "-" = nothing to compare.
                mv = e.get("version", "-")
    except Exception:
        mv = "?"
print(f"{name}\t{pv}\t{mv}")
PY
)"
    if [ -n "$plug_row" ]; then
      pv="$(printf '%s' "$plug_row" | cut -f2)"
      mv="$(printf '%s' "$plug_row" | cut -f3)"
      if [ "$mv" != "-" ] && [ "$pv" != "$mv" ]; then drift_n=$((drift_n + 1)); fi
      printf 'PLUGDEV\t%s\t%s\n' "$repo" "$plug_row"
    fi
  fi
}

printf 'KIND\tPATH\tBRANCH\tDIRTY\tAHEAD\tBEHIND\tUPSTREAM\tSTASHES\n'

while IFS= read -r repo; do
  [ -z "$repo" ] && continue
  [ "$(git -C "$repo" rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] || continue
  total_repos=$((total_repos + 1))
  if [ "$FETCH" = 1 ]; then
    if ! git -C "$repo" fetch --all --prune --quiet 2>/dev/null; then
      fetch_fail=$((fetch_fail + 1))
      printf 'sweep-scan: fetch failed (offline? no remote?): %s\n' "$repo" >&2
    fi
  fi
  emit_checkout "repo" "$repo"
  # Linked worktrees: `worktree list --porcelain` lists the main checkout
  # first -- skip it, we just printed it.
  first=1
  while IFS= read -r wt; do
    [ -z "$wt" ] && continue
    if [ "$first" = 1 ]; then first=0; continue; fi
    total_wt=$((total_wt + 1))
    emit_checkout "worktree" "$wt"
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
  sweep_repo "$repo"
done <<EOF
$repos
EOF

printf 'SUMMARY\trepos=%s\tworktrees=%s\tdirty=%s\tahead=%s\tbehind=%s\tgone=%s\twith-stashes=%s\tfetch-failures=%s\tstale-local-branches=%s\tstale-remote-branches=%s\torphan-dirs=%s\tparked=%s\tmanifest-drift=%s\n' \
  "$total_repos" "$total_wt" "$dirty_n" "$ahead_n" "$behind_n" "$gone_n" "$stash_n" "$fetch_fail" \
  "$stale_local" "$stale_remote" "$orphan_n" "$parked_n" "$drift_n"
