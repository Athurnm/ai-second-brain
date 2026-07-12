#!/usr/bin/env bash
# PreToolUse hook on Slack send tools (matcher: mcp__.*[Ss]lack.*__.*(post|send|reply).*).
# Forces a confirmation prompt for EVERY Slack send, even if the tool is allowlisted -
# You's rule: nothing goes to Slack without explicit "kirim"/approval.
# Uses permissionDecision "ask" (not "deny") so an approved send costs one keypress.
# Contract: always exit 0; on any internal failure fall back to a static prompt.
set -u

input="$(cat 2>/dev/null)" || input=""

if command -v python3 >/dev/null 2>&1 && [ -n "$input" ]; then
  HOOK_INPUT="$input" python3 - <<'PY' 2>/dev/null && exit 0
import json, os
try:
    d = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    ti = d.get("tool_input", {}) or {}
    ch = str(ti.get("channel_id") or ti.get("channel") or ti.get("channel_name") or "?")
    txt = str(ti.get("text") or ti.get("message") or "")[:300].replace("\n", " / ").replace('"', "'")
    reason = (f"APPROVAL GATE - Slack send to [{ch}]. Did You explicitly say kirim/approve for THIS exact message? "
              f'Preview: "{txt}"')
except Exception:
    reason = "APPROVAL GATE - Slack send detected. Confirm You explicitly approved this exact message (kirim)."
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
    "permissionDecision": "ask", "permissionDecisionReason": reason}}))
PY
fi

# Fallback: no python3 or parse failure - still gate the send.
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"APPROVAL GATE - Slack send detected. Confirm You explicitly approved this exact message (kirim)."}}\n'
exit 0
