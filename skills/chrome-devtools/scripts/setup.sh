#!/usr/bin/env bash
# setup.sh — register the chrome-devtools MCP servers (user scope, all projects)
# with named login profiles, a pinned server version, and telemetry disabled.
#
# Usage:
#   setup.sh [profile-name ...]
#
# Always registers:
#   chrome            --isolated        throwaway profile - the default choice
# Plus, per given profile name (kebab-case, e.g. "personal work acme"):
#   chrome-<name>     --user-data-dir   persistent login profile for that identity
#
# The profile names are user-specific identities (one per account/company the
# user operates as); the account→profile mapping belongs in the user's global
# CLAUDE.md, not here and never in a repo. Idempotent: existing entries are left
# alone unless FORCE=1.
#
# Env overrides:
#   CHROME_DEVTOOLS_MCP_VERSION   server package version (default: pinned below)
#   CHROME_PROFILES_DIR           profile base dir (default: ~/.claude/chrome-profiles)
#   HEADLESS=1                    register the servers headless (default: headed)
#   FORCE=1                       replace existing server entries
#
# Remove later with:  claude mcp remove -s user chrome  (and each chrome-<name>)
# and delete ~/.claude/chrome-profiles to wipe saved logins.
set -euo pipefail

VERSION="${CHROME_DEVTOOLS_MCP_VERSION:-1.7.0}"
BASE="${CHROME_PROFILES_DIR:-$HOME/.claude/chrome-profiles}"

command -v claude >/dev/null 2>&1 || { echo "x claude CLI not found in PATH." >&2; exit 1; }
command -v npx    >/dev/null 2>&1 || { echo "x npx (Node.js) not found in PATH." >&2; exit 1; }

for name in "$@"; do
  case "$name" in
    *[!a-z0-9-]*|"")
      echo "x invalid profile name '$name' (use kebab-case: a-z, 0-9, -)" >&2
      exit 2 ;;
  esac
done

HEADLESS_ARGS=()
[ "${HEADLESS:-0}" = "1" ] && HEADLESS_ARGS=(--headless)

add_server() {
  local name="$1"; shift
  if claude mcp get "$name" >/dev/null 2>&1; then
    if [ "${FORCE:-0}" = "1" ]; then
      echo "~ $name: exists - replacing (FORCE=1)"
      claude mcp remove -s user "$name" >/dev/null 2>&1 || claude mcp remove "$name" >/dev/null
    else
      echo "= $name: already configured - leaving as-is (rerun with FORCE=1 to replace)"
      return 0
    fi
  fi
  claude mcp add -s user "$name" -- npx -y "chrome-devtools-mcp@${VERSION}" \
    --no-usage-statistics ${HEADLESS_ARGS[@]+"${HEADLESS_ARGS[@]}"} "$@" >/dev/null
  echo "+ $name: registered (chrome-devtools-mcp@${VERSION})"
}

add_server chrome --isolated

for name in "$@"; do
  mkdir -p "$BASE/$name"
  add_server "chrome-$name" "--user-data-dir=$BASE/$name"
done

cat <<EOF

Done. Profiles live under: $BASE (local disk only - never inside a repo).
Next steps:
  1. RESTART the Claude Code session - MCP config loads at session start.
  2. Sign into each identity once, in a plain (non-automated) window,
     one profile at a time:
EOF
if [ $# -gt 0 ]; then
  for name in "$@"; do
    echo "       open-profile.sh $name"
  done
else
  echo "       open-profile.sh <name>   # after: setup.sh <name>"
fi
cat <<'EOF'
     ...then CLOSE that window before running automation on the profile.
  3. Record the account -> profile mapping in your global ~/.claude/CLAUDE.md
     so any session knows which identity a task belongs to.
EOF
