#!/usr/bin/env bash
# sweep-scan.sh -- read-only audit for the yar:repo-sweep skill.
#
# Discovers every local git repo under the scan roots and prints a typed,
# tab-separated audit: per-checkout sync state (same table daily driving needs),
# plus the sweep-specific facts -- local/remote branch staleness (squash-merge
# aware, and backed by merged pull requests wherever `gh` can see them),
# worktree containment, which checkouts a live process is standing in (one
# lsof snapshot), orphaned worktree directories, a primary checkout parked off
# the default branch, and plugin manifest version drift.
#
# Read-only by design: it never touches a working tree, branch, stash, or
# remote; --fetch only updates remote-tracking refs so ahead/behind/gone and
# merged-ness are judged against current remote state, the merged-PR lookup
# is a read (`gh pr list`), and so is the in-use probe (`lsof -a -d cwd`). All
# mutation decisions belong to the skill (see reference/playbook.md), never to
# this script.
# macOS bash 3.2 compatible (no mapfile, no associative arrays, no ${var,,}).
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: sweep-scan.sh [--fetch] [--no-pr] [ROOT ...]

Print a typed, tab-separated audit of every git repo under the scan roots.

Roots, first source that yields anything wins:
  1. ROOT arguments
  2. $DAILY_REPO_ROOTS -- colon-separated directories (~ allowed)
  3. whichever of these exist:
     ~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer

Options:
  --fetch    run `git fetch --all --prune` per repo before reading state
             (network; required for trustworthy gone/behind/merged signals)
  --no-pr    skip the merged-PR lookup: no `gh` calls, and a branch whose only
             proof is a merged pull request reads UNIQUE, as it did before
  -h|--help  this text

Scan depth below each root: $DAILY_SCAN_DEPTH (default 4).

Merged-PR proof (read-only, best-effort): for each repo whose origin is a
GitHub-style remote (HOST/OWNER/NAME) on a host `gh` holds a token for, ONE
`gh pr list --state merged --base DEFAULT --limit 500` call per repo fetches
the merged pull requests; a branch git alone cannot prove merged is then
PRMERGED(#N) -- see BRANCH below. No gh, no token, a non-GitHub remote, or a
failed call leaves that repo classified from git alone (never worse than
before). Only the 500 most recently merged PRs are seen; a branch whose PR is
older stays UNIQUE (conservative). Stale remote-tracking refs can only make
the proof more conservative, never less: the PR's merge commit must already
be an ancestor of the local origin/DEFAULT.

In-use probe (read-only, best-effort): ONE `lsof +c 0 -a -d cwd -Fpcn`
snapshot per run lists every process the caller may inspect with its current
working directory. A checkout some process is standing in -- another Claude
Code session's shell and MCP servers, an editor, a terminal -- must never be
removed or switched out from under it, so WT, ORPHAN and PARKED rows carry
INUSE: yes = a process has its cwd at or below the path (compared
case-insensitively; one INUSE row per such process follows the row), no =
none in the snapshot, ? = no snapshot (lsof missing or failed) -- unknown,
never "no".

Row types (first column):
  repo | worktree   one line per checkout:
                    KIND PATH BRANCH DIRTY AHEAD BEHIND UPSTREAM STASHES
                    (UPSTREAM: ok | gone | none; gone = deleted on the remote)
  WT       linked worktree sweep facts:
           WT REPO PATH HEAD CONTAINED DIRTY PRUNABLE INUSE
           (HEAD = branch name or DETACHED@sha; CONTAINED = proof that HEAD's
            content is on origin/DEFAULT: yes = ancestor, EQUIV and
            PRMERGED(#N) as for BRANCH (a detached HEAD matches a PR by
            commit), no = unproven; PRUNABLE = git already lost the dir;
            INUSE = yes | no | ? -- a live process stands in it, see above)
  INUSE    one live process standing in the WT / ORPHAN / PARKED path just
           printed (only after INUSE=yes; CWD is its working directory):
           INUSE REPO PATH PID COMMAND CWD
  BRANCH   local branch classification:
           BRANCH REPO NAME STATE UPSTREAM CHECKEDOUT LASTCOMMIT
           STATE: DEFAULT(behind=N) | MERGED | EQUIV | PRMERGED(#N) | UNIQUE(N)
           (MERGED = ancestor of origin/DEFAULT; EQUIV = every commit is
            patch-equivalent to one already there -- the single-commit
            squash-merge signal; PRMERGED(#N) = pull request #N into DEFAULT
            is merged, its merge commit is on origin/DEFAULT, and every
            non-merge commit on the branch is inside that PR's head -- the tip
            is the PR head, is behind it, or only merges from DEFAULT follow
            it -- the multi-commit squash-merge signal `git cherry` cannot see;
            UNIQUE = N commits whose content is nowhere on origin/DEFAULT and
            that no merged PR vouches for; UNIQUE(?) = the rev did not resolve)
  RBRANCH  remote branch classification, same STATE vocabulary minus DEFAULT:
           RBRANCH REPO NAME STATE LASTCOMMIT
           (MERGED / EQUIV / PRMERGED(#N) = nothing on it that origin/DEFAULT
            lacks -- deletion candidates the skill still checks for open PRs
            and confirms one by one)
  ORPHAN   directory under REPO/.claude/worktrees not registered as a
           worktree (typically left behind by a repo rename):
           ORPHAN REPO PATH GITDIR_TARGET REPAIRABLE SIZE_KB FILES INUSE
  PARKED   primary checkout is not on the default branch:
           PARKED REPO CURRENT_BRANCH STATE DEFAULT DEFAULT_BEHIND INUSE
  PLUGDEV  plugin dev clone manifest versions:
           PLUGDEV REPO NAME PLUGIN_JSON_VERSION MARKETPLACE_VERSION
  NOREMOTE repo has no origin default branch to judge against; only the
           checkout row is emitted.
  SUMMARY  totals, last line. stale-local-branches / stale-remote-branches
           count MERGED + EQUIV + PRMERGED; pr-merged-local / pr-merged-remote
           count the PRMERGED share of those; pr-proof = off, or
           QUERIED/GITHUB-REPOS (repos whose merged PRs were fetched, out of
           the repos with a GitHub-style origin); in-use counts the WT /
           ORPHAN / PARKED rows with INUSE=yes, or ? without a snapshot.
EOF
}

FETCH=0
NO_PR=0
arg_roots=""
for arg in "$@"; do
  case "$arg" in
    --fetch) FETCH=1 ;;
    --no-pr) NO_PR=1 ;;
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

# Merged-PR proof: on when gh is installed and not opted out. Whether gh can
# actually answer is probed per host (a token) and per repo (the list call
# itself); every failure degrades that repo to git-only classification. gh is
# told never to prompt or advertise updates -- this is a non-interactive scan.
PR_LIMIT=500
export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1
if [ "$NO_PR" = 1 ]; then
  PR_MODE="off (--no-pr)"
elif ! command -v gh >/dev/null 2>&1; then
  PR_MODE="off (gh not installed)"
else
  PR_MODE="on"
fi
printf 'sweep-scan: merged-PR proof via gh: %s\n' "$PR_MODE" >&2

# In-use probe: one `lsof -a -d cwd` snapshot per run -- every process the
# caller may inspect, with its current working directory -- flattened to one
# record per process: PID<TAB>COMMAND<TAB>CWD/. The cwd always ends in exactly
# one slash, so a fixed-string search for "<TAB><path>/" finds a process
# standing at the path or anywhere below it, and /foo never matches /foobar.
# Taken once, here, before any `git -C <checkout>` child of this script could
# itself stand in a checkout. `+c 0` keeps full command names. No lsof, a
# failure, or an empty listing (impossible while this very shell runs) leaves
# the probe off and every INUSE column "?" -- unknown is not "no".
INUSE_MODE="off"; cwd_snapshot=""
if ! command -v lsof >/dev/null 2>&1; then
  inuse_note="off (lsof not installed)"
elif ! lsof_out="$(lsof +c 0 -a -d cwd -Fpcn 2>/dev/null)" || [ -z "$lsof_out" ]; then
  inuse_note="off (lsof failed)"
else
  INUSE_MODE="on"; inuse_note="on"
  ls_pid=""; ls_cmd=""
  while IFS= read -r fl; do
    case "$fl" in
      p*) ls_pid="${fl#p}"; ls_cmd="" ;;
      c*) ls_cmd="${fl#c}" ;;
      n*) ls_cwd="${fl#n}"; ls_cwd="${ls_cwd%/}/"
          cwd_snapshot="${cwd_snapshot}${ls_pid}"$'\t'"${ls_cmd:-?}"$'\t'"${ls_cwd}"$'\n' ;;
    esac
  done <<EOF
$lsof_out
EOF
fi
printf 'sweep-scan: in-use probe via lsof: %s\n' "$inuse_note" >&2

# INUSE for one checkout, given every spelling of its path (the registered
# path and its resolved one): yes when the snapshot holds a process whose cwd
# is one of them or below it -- compared case-insensitively, as every path in
# this script -- no when it holds none, ? when there is no snapshot. Sets
# $inuse and $inuse_hits (the matching PID<TAB>COMMAND<TAB>CWD/ records).
in_use() {
  inuse="?"; inuse_hits=""
  [ "$INUSE_MODE" = "on" ] || return 0
  inuse="no"
  pats=""
  for _p in "$@"; do
    _p="${_p%/}"
    [ -n "$_p" ] || continue        # "/" would claim every process
    pats="${pats}"$'\t'"${_p}/"$'\n'
  done
  [ -n "$pats" ] || return 0
  inuse_hits="$(printf '%s' "$cwd_snapshot" | grep -i -F -f <(printf '%s' "$pats"))" || inuse_hits=""
  if [ -n "$inuse_hits" ]; then inuse="yes"; fi
}

# One INUSE row per process in $inuse_hits, for the checkout at PATH.
emit_inuse_rows() {
  ir_repo="$1"; ir_path="$2"
  [ -n "$inuse_hits" ] || return 0
  while IFS= read -r rec; do
    [ -z "$rec" ] && continue
    h_pid="${rec%%$'\t'*}"; h_rest="${rec#*$'\t'}"
    h_cmd="${h_rest%%$'\t'*}"; h_cwd="${h_rest#*$'\t'}"
    printf 'INUSE\t%s\t%s\t%s\t%s\t%s\n' "$ir_repo" "$ir_path" "$h_pid" "$h_cmd" "${h_cwd%/}"
  done <<EOF
$inuse_hits
EOF
}

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
stale_local=0; stale_remote=0; pr_local=0; pr_remote=0
gh_repos_n=0; pr_repos_n=0
orphan_n=0; parked_n=0; drift_n=0; inuse_n=0

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

# Print HOST/OWNER/NAME for a GitHub-style origin URL (https://, ssh://, or the
# scp-like git@host:owner/name[.git]); print nothing for anything else -- no
# origin, a local path, a nested group path. Reads the configured URL rather
# than the insteadOf-rewritten one, so a fetch alias does not hide the host.
github_slug() {
  _url="$(git -C "$1" config --get remote.origin.url 2>/dev/null)" || return 0
  _url="${_url%/}"; _url="${_url%.git}"
  case "$_url" in
    *://*) _rest="${_url#*://}"; _rest="${_rest#*@}"
           _host="${_rest%%/*}"; _path="${_rest#*/}" ;;
    *@*:*) _rest="${_url#*@}"; _host="${_rest%%:*}"; _path="${_rest#*:}" ;;
    *) return 0 ;;
  esac
  _host="${_host%%:*}"   # drop a port
  case "$_host" in ''|*/*) return 0 ;; esac
  case "$_path" in
    */*/*|*/|/*|'') return 0 ;;          # exactly OWNER/NAME, nothing else
    */*) printf '%s/%s' "$_host" "$_path" ;;
  esac
}

# 0 when gh holds a token for HOST, cached per host. `gh auth token` is the
# probe rather than `gh auth status`: the latter exits non-zero as soon as ANY
# account on the host is stale, even while the active one works.
gh_hosts_ok=" "; gh_hosts_bad=" "
gh_host_ok() {
  case "$gh_hosts_ok" in *" $1 "*) return 0 ;; esac
  case "$gh_hosts_bad" in *" $1 "*) return 1 ;; esac
  if gh auth token -h "$1" >/dev/null 2>&1; then
    gh_hosts_ok="${gh_hosts_ok}$1 "
    return 0
  fi
  gh_hosts_bad="${gh_hosts_bad}$1 "
  printf 'sweep-scan: gh has no token for %s -- merged-PR proof skipped there\n' "$1" >&2
  return 1
}

# Load the merged-PR cache for one repo: ONE gh call, rows newest-merge first,
# tab-separated NUMBER HEADREF HEADOID BASEREF MERGEOID MERGEDAT ("-" where GitHub
# has no value, so no field is ever empty). Sets $pr_cache (empty = nothing to
# prove with) and bumps the gh_repos_n / pr_repos_n counters.
load_pr_cache() {
  _repo="$1"; _def="$2"
  pr_cache=""
  [ "$PR_MODE" = "on" ] || return 0
  slug="$(github_slug "$_repo")"
  [ -n "$slug" ] || return 0
  gh_repos_n=$((gh_repos_n + 1))
  gh_host_ok "${slug%%/*}" || return 0
  if pr_cache="$(gh pr list --repo "$slug" --state merged --base "$_def" --limit "$PR_LIMIT" \
        --json number,headRefName,headRefOid,baseRefName,mergeCommit,mergedAt \
        --jq 'sort_by(.mergedAt) | reverse | .[] | [.number, .headRefName, .headRefOid, .baseRefName, (.mergeCommit.oid // "-"), (.mergedAt // "-")] | @tsv' 2>/dev/null)"; then
    pr_repos_n=$((pr_repos_n + 1))
  else
    pr_cache=""
    printf 'sweep-scan: gh pr list failed (offline? no access?): %s -- classified from git alone\n' "$_repo" >&2
  fi
}

# Merged-PR proof for one commit. Sets $pr_num to the number of a merged pull
# request into origin/<default> that vouches for TIP, else empties it.
# Candidates are cache rows whose head ref is NAME (a reused or long-lived
# branch name may have several -- newest first, older ones still count) or
# whose head oid IS the tip (a renamed local branch, a detached worktree). A
# candidate proves TIP when (1) its merge commit is an ancestor of the local
# origin/<default> -- so a stale remote-tracking ref only makes us more
# conservative -- and (2) no non-merge commit reachable from TIP is missing
# from both origin/<default> and the PR head: tip == head, tip behind head, or
# only merges after head all pass; a rebased, rewritten, or continued branch
# fails and stays UNIQUE. Fields are split on tabs by hand: `read` with a
# whitespace IFS would collapse runs of tabs and shift the columns.
pr_proof() {
  _repo="$1"; _tip="$2"; _name="$3"; _def="$4"
  pr_num=""
  [ -n "$pr_cache" ] && [ -n "$_tip" ] || return 0
  while IFS= read -r row; do
    [ -z "$row" ] && continue
    c_num="${row%%$'\t'*}"; rest="${row#*$'\t'}"
    c_head="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"
    c_oid="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"
    c_base="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"
    c_merge="${rest%%$'\t'*}"
    [ -n "$c_num" ] && [ -n "$c_oid" ] || continue
    if [ "$c_head" != "$_name" ] && [ "$c_oid" != "$_tip" ]; then continue; fi
    [ "$c_base" = "$_def" ] || continue
    case "$c_merge" in ''|-) continue ;; esac
    git -C "$_repo" merge-base --is-ancestor "$c_merge" "origin/$_def" 2>/dev/null || continue
    left="$(git -C "$_repo" rev-list --count --no-merges "origin/$_def..$_tip" "^$c_oid" 2>/dev/null)" || continue
    if [ "$left" = "0" ]; then
      pr_num="$c_num"
      return 0
    fi
  done <<EOF
$pr_cache
EOF
}

# Classify one rev against origin/<default>: MERGED (ancestor), EQUIV (every
# commit patch-equivalent to one upstream -- how a single-commit squash-merge or
# a re-landed branch looks), PRMERGED(#N) (a merged pull request vouches for it
# -- the multi-commit squash-merge that defeats `git cherry`), or UNIQUE(N) (N
# commits whose content is nowhere on the default branch). PRNAME is the head
# ref name to look the PR up by: defaults to REV; pass "" to match by commit
# only (a detached HEAD). A rev that does not resolve is UNIQUE(?) -- an
# unreadable ref must never pass as proof. Sets $state.
classify_branch() {
  _repo="$1"; _rev="$2"; _def="$3"; _prname="${4-$2}"
  tip="$(git -C "$_repo" rev-parse --verify --quiet "$_rev^{commit}" 2>/dev/null)"
  if [ -z "$tip" ]; then
    state="UNIQUE(?)"
    return
  fi
  if git -C "$_repo" merge-base --is-ancestor "$tip" "origin/$_def" 2>/dev/null; then
    state="MERGED"
    return
  fi
  if ! cherry_out="$(git -C "$_repo" cherry "origin/$_def" "$tip" 2>/dev/null)"; then
    state="UNIQUE(?)"
    return
  fi
  uniq_ct="$(printf '%s\n' "$cherry_out" | grep -c '^+' || true)"
  if [ "${uniq_ct:-0}" -eq 0 ]; then
    state="EQUIV"
    return
  fi
  pr_proof "$_repo" "$tip" "$_prname" "$_def"
  if [ -n "$pr_num" ]; then
    state="PRMERGED(#${pr_num})"
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

  # Merged pull requests into the default branch -- one gh call per repo,
  # consumed by every classification below (worktrees, branches, remote
  # branches, the parked primary).
  load_pr_cache "$repo" "$def"

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
      # CONTAINED is the proof that HEAD's content is on origin/<default>:
      # yes (ancestor), EQUIV or PRMERGED(#N) as for branches (a detached HEAD
      # can still match a merged PR by commit), no (unproven).
      classify_branch "$repo" "$wt_head" "$def" "$wt_branch"
      case "$state" in
        MERGED) contained="yes" ;;
        EQUIV|PRMERGED*) contained="$state" ;;
        *) contained="no" ;;
      esac
      wt_dirty="$(git -C "$wt_path" status --porcelain 2>/dev/null | grep -c . || true)"
      # INUSE: a live process stands in the worktree (registered path or its
      # resolved one) -- the skill never removes such a worktree.
      in_use "$wt_path" "$wt_real"
      [ "$inuse" = "yes" ] && inuse_n=$((inuse_n + 1))
      printf 'WT\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$repo" "$wt_path" "$head_desc" "$contained" "${wt_dirty:-0}" "$wt_prunable" "$inuse"
      emit_inuse_rows "$repo" "$wt_path"
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
      case "$state" in
        MERGED|EQUIV) stale_local=$((stale_local + 1)) ;;
        PRMERGED*) stale_local=$((stale_local + 1)); pr_local=$((pr_local + 1)) ;;
      esac
    fi
    printf 'BRANCH\t%s\t%s\t%s\t%s\t%s\t%s\n' "$repo" "$b" "$state" "$upstate" "$co" "$date"
  done < <(git -C "$repo" for-each-ref refs/heads \
             --format='%(refname:short)%09%(upstream:short)%09%(upstream:track)%09%(committerdate:short)' 2>/dev/null)

  # Remote branches other than the default, classified like local ones:
  # MERGED / EQUIV / PRMERGED(#N) mean nothing on them that origin/<default>
  # does not already have (deletion candidates -- the skill still checks for
  # an open PR and confirms each one before proposing deletion).
  while IFS= read -r rline; do
    [ -z "$rline" ] && continue
    ref="${rline%%$'\t'*}"; date="${rline#*$'\t'}"
    rb="${ref#refs/remotes/origin/}"
    [ "$rb" = "HEAD" ] && continue
    [ "$rb" = "$def" ] && continue
    classify_branch "$repo" "$ref" "$def" "$rb"
    case "$state" in
      MERGED|EQUIV) stale_remote=$((stale_remote + 1)) ;;
      PRMERGED*) stale_remote=$((stale_remote + 1)); pr_remote=$((pr_remote + 1)) ;;
    esac
    printf 'RBRANCH\t%s\t%s\t%s\t%s\n' "$repo" "$rb" "$state" "$date"
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
      in_use "$d" "$d_real"
      [ "$inuse" = "yes" ] && inuse_n=$((inuse_n + 1))
      printf 'ORPHAN\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$repo" "$d" "$target" "$repairable" "${size_kb:-?}" "${files:-?}" "$inuse"
      emit_inuse_rows "$repo" "$d"
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
    in_use "$repo"
    [ "$inuse" = "yes" ] && inuse_n=$((inuse_n + 1))
    printf 'PARKED\t%s\t%s\t%s\t%s\t%s\t%s\n' "$repo" "$cur" "$state" "$def" "$def_behind" "$inuse"
    emit_inuse_rows "$repo" "$repo"
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

if [ "$PR_MODE" = "on" ]; then
  pr_proof_s="${pr_repos_n}/${gh_repos_n}"
else
  pr_proof_s="off"
fi
if [ "$INUSE_MODE" = "on" ]; then inuse_s="$inuse_n"; else inuse_s="?"; fi
printf 'SUMMARY\trepos=%s\tworktrees=%s\tdirty=%s\tahead=%s\tbehind=%s\tgone=%s\twith-stashes=%s\tfetch-failures=%s\tstale-local-branches=%s\tstale-remote-branches=%s\tpr-merged-local=%s\tpr-merged-remote=%s\tpr-proof=%s\torphan-dirs=%s\tparked=%s\tin-use=%s\tmanifest-drift=%s\n' \
  "$total_repos" "$total_wt" "$dirty_n" "$ahead_n" "$behind_n" "$gone_n" "$stash_n" "$fetch_fail" \
  "$stale_local" "$stale_remote" "$pr_local" "$pr_remote" "$pr_proof_s" "$orphan_n" "$parked_n" "$inuse_s" "$drift_n"
