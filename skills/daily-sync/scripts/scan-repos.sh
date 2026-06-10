#!/usr/bin/env bash
# scan-repos.sh -- discover local git repos and print one status line per checkout.
#
# Part of the yar:daily-sync skill. Read-only by design: it never touches a
# working tree, branch, or stash; --fetch only updates remote-tracking refs so
# the ahead/behind/gone numbers are current before a morning pull or a night
# sweep. macOS bash 3.2 compatible (no mapfile, no associative arrays).
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: scan-repos.sh [--fetch] [ROOT ...]

Discover git repos and print a tab-separated status table, one line per
checkout (main repos and their linked worktrees), then a SUMMARY line.

Roots, first source that yields anything wins:
  1. ROOT arguments
  2. $DAILY_REPO_ROOTS -- colon-separated directories (~ allowed)
  3. whichever of these exist:
     ~/Projects ~/Code ~/code ~/repos ~/src ~/dev ~/Developer

Options:
  --fetch    run `git fetch --all --prune` per repo before reading status
             (network; needed for accurate ahead/behind/gone)
  -h|--help  this text

Scan depth below each root: $DAILY_SCAN_DEPTH (default 4).

Columns:
  KIND      repo | worktree
  PATH      absolute path of the checkout
  BRANCH    current branch, or DETACHED
  DIRTY     changed + untracked paths (0 = clean)
  AHEAD     commits ahead of upstream  (- = no upstream)
  BEHIND    commits behind upstream    (- = no upstream)
  UPSTREAM  ok | gone | none  (gone = upstream deleted on the remote --
            the reliable "merged" signal under squash-merges)
  STASHES   stash entries (local-only state a push cannot save)
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
    printf 'scan-repos: root not found, skipping: %s\n' "$r" >&2
  fi
done <<EOF
$src
EOF

if [ -z "$roots" ]; then
  {
    echo 'scan-repos: no scan roots found.'
    echo 'Set DAILY_REPO_ROOTS to a colon-separated list of directories that'
    echo 'contain your git repos, e.g. DAILY_REPO_ROOTS=~/Projects:~/Clients'
  } >&2
  exit 1
fi

DEPTH="${DAILY_SCAN_DEPTH:-4}"
case "$DEPTH" in
  ''|*[!0-9]*) echo 'scan-repos: DAILY_SCAN_DEPTH must be a positive integer' >&2; exit 1 ;;
esac

printf 'scan-repos: scanning (depth %s):\n' "$DEPTH" >&2
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
  echo 'scan-repos: no git repos found under the scanned roots.' >&2
  exit 1
fi

total_repos=0; total_wt=0; dirty_n=0; ahead_n=0; behind_n=0
gone_n=0; stash_n=0; fetch_fail=0

# Print one status line for a checkout and update the summary counters.
# One `git status --porcelain=v2 --branch` call gives branch, upstream state,
# ahead/behind, and the dirty count; `gone` = upstream configured but its
# remote-tracking ref vanished (the branch.ab line disappears).
emit() {
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

printf 'KIND\tPATH\tBRANCH\tDIRTY\tAHEAD\tBEHIND\tUPSTREAM\tSTASHES\n'

while IFS= read -r repo; do
  [ -z "$repo" ] && continue
  [ "$(git -C "$repo" rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] || continue
  total_repos=$((total_repos + 1))
  if [ "$FETCH" = 1 ]; then
    if ! git -C "$repo" fetch --all --prune --quiet 2>/dev/null; then
      fetch_fail=$((fetch_fail + 1))
      printf 'scan-repos: fetch failed (offline? no remote?): %s\n' "$repo" >&2
    fi
  fi
  emit "repo" "$repo"
  # Linked worktrees: `worktree list --porcelain` lists the main checkout
  # first -- skip it, we just printed it.
  first=1
  while IFS= read -r wt; do
    [ -z "$wt" ] && continue
    if [ "$first" = 1 ]; then first=0; continue; fi
    total_wt=$((total_wt + 1))
    emit "worktree" "$wt"
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
done <<EOF
$repos
EOF

printf 'SUMMARY\trepos=%s\tworktrees=%s\tdirty=%s\tahead=%s\tbehind=%s\tgone=%s\twith-stashes=%s\tfetch-failures=%s\n' \
  "$total_repos" "$total_wt" "$dirty_n" "$ahead_n" "$behind_n" "$gone_n" "$stash_n" "$fetch_fail"
