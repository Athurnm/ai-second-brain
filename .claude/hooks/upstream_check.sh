#!/usr/bin/env bash
# SessionStart hook: light check whether the upstream template has new commits.
#
# Runs ONLY in forks of the AI Second Brain template. The source repos (this one,
# and you/ai-second-brain itself) self-skip: you cannot be behind yourself.
#
# Cheap by design: one `git ls-remote` (a single ref lookup, no object download),
# throttled to once per 24h and cached. Offline or slow network exits silently.
# Portable pure bash (no python/jq) — WSL/Linux, macOS, Windows Git Bash.
# Always exits 0; never blocks the session.
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE_URL="https://github.com/BrianArfi/ai-second-brain.git"
STATE="$REPO_DIR/.claude/.upstream_check"
TTL=86400  # re-check the network at most once per day

json_escape() {
  local s="$1"
  s=${s//\\/\\\\}; s=${s//\"/\\\"}
  s=${s//$'\r'/}; s=${s//$'\n'/\\n}; s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

# Announce an available update to both Claude (context) and the user (system message).
emit_behind() {
  local ctx sysmsg
  ctx="$(json_escape "=== Harness update available ===
The upstream AI Second Brain template has commits your fork does not have.
Tell the user they can pull them with /update-harness (it merges, resolves
conflicts, and surfaces any new .env variables). Do NOT run it unprompted.")"
  sysmsg="$(json_escape "Harness update available upstream. Run /update-harness to pull it in.")"
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"},"systemMessage":"%s"}\n' \
    "$ctx" "$sysmsg"
  exit 0
}

# Everything else is silence: an up-to-date fork should cost the user zero attention.
quiet() { exit 0; }

command -v git >/dev/null 2>&1 || quiet
git -C "$REPO_DIR" rev-parse --git-dir >/dev/null 2>&1 || quiet

origin="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || echo '')"
upstream="$(git -C "$REPO_DIR" remote get-url upstream 2>/dev/null || echo '')"

# Normalize for comparison: lowercase, drop trailing .git, drop scp-style/user prefixes.
norm() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -e 's/\.git$//' -e 's#.*[/:]\([^/]*/[^/]*\)$#\1#'; }
origin_slug="$(norm "$origin")"

# --- Who am I? -------------------------------------------------------------
# Skip when this repo IS the template (nothing upstream of it).
[ "$origin_slug" = "you/ai-second-brain" ] && quiet

# Run only for genuine forks: either an `upstream` remote points at the template
# (set by /update-harness, survives a renamed fork), or origin is an unrenamed fork.
is_fork=0
[ -n "$upstream" ] && [ "$(norm "$upstream")" = "you/ai-second-brain" ] && is_fork=1
case "$origin_slug" in */ai-second-brain) is_fork=1 ;; esac
[ "$is_fork" -eq 1 ] || quiet

# --- Throttle --------------------------------------------------------------
now="$(date +%s 2>/dev/null || echo 0)"
last_ts=0; last_state=""
if [ -f "$STATE" ]; then
  read -r last_ts last_state < "$STATE" 2>/dev/null || true
  case "$last_ts" in ''|*[!0-9]*) last_ts=0 ;; esac
fi

if [ "$now" -gt 0 ] && [ $((now - last_ts)) -lt "$TTL" ]; then
  # Inside the TTL: answer from cache, no network. A pending update keeps
  # reminding every session until it is actually merged.
  [ "$last_state" = "behind" ] && emit_behind
  quiet
fi

# --- The actual check ------------------------------------------------------
# ls-remote fetches one ref, not the history. Guard it with a timeout where
# GNU timeout exists (Windows ships an incompatible timeout.exe).
url="${upstream:-$TEMPLATE_URL}"
LS=(git ls-remote "$url" refs/heads/main)
if timeout --version 2>/dev/null | grep -q GNU; then
  LS=(timeout 8 "${LS[@]}")
fi
remote_sha="$("${LS[@]}" 2>/dev/null | awk 'NR==1{print $1}')"

# Offline, private, or unreachable: stay silent and do NOT poison the cache,
# so the next session retries instead of waiting out the full TTL.
[ -n "$remote_sha" ] || quiet

# Is that commit already IN this branch? Must be an ancestor of HEAD — merely
# having the object is not enough: any prior `git fetch upstream` leaves the
# commit sitting locally, unmerged, and a presence check would call that current.
# --is-ancestor also fails when the object is absent, which is the same answer.
if git -C "$REPO_DIR" merge-base --is-ancestor "$remote_sha" HEAD 2>/dev/null; then
  state="current"
else
  state="behind"
fi

printf '%s %s\n' "$now" "$state" > "$STATE" 2>/dev/null || true
[ "$state" = "behind" ] && emit_behind
quiet
