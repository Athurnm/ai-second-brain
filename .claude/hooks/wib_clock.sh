#!/usr/bin/env bash
# SessionStart hook: inject current WIB date/time so the model never reasons from UTC.
# Contract: always exit 0; never block a session.
set -u

now="$(TZ=Asia/Jakarta date '+%A, %Y-%m-%d %H:%M WIB' 2>/dev/null)" || exit 0
[ -n "$now" ] || exit 0

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"=== You local time === Now: %s. Use THIS for all date/day reasoning (You is UTC+7, Indonesia). Sessions can cross midnight - re-run TZ=Asia/Jakarta date if much time has passed."}}\n' "$now"
exit 0
