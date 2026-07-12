#!/usr/bin/env bash
# PostToolUse hook on Bash: deterministic Drive Operation Verification (CLAUDE.md rule).
# If a gdocs_create/gdrive_manager create/upload/update ran but returned no file ID or
# Drive link, block and tell the model to treat it as a FAILURE.
# Fast-path: grep stdin first - 99% of Bash calls exit here in milliseconds, no python spawn.
# Contract: always exit 0 on internal failure; never block a session by accident.
set -u

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0

# Fast-path: only Drive write operations are interesting.
printf '%s' "$input" | grep -qE 'gdocs_create\.py|gdrive_manager\.py' || exit 0
printf '%s' "$input" | grep -qE 'create-doc|upload|update' || exit 0

command -v python3 >/dev/null 2>&1 || exit 0

HOOK_INPUT="$input" python3 - <<'PY' 2>/dev/null || exit 0
import json, os, re, sys

try:
    d = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    cmd = str((d.get("tool_input") or {}).get("command") or "")
    # Confirm the command itself is a Drive write op (stdin grep may have hit the response text).
    if not re.search(r"(gdocs_create\.py|gdrive_manager\.py)", cmd):
        sys.exit(0)
    if not re.search(r"(create-doc|upload|update)", cmd):
        sys.exit(0)

    resp = d.get("tool_response")
    if isinstance(resp, dict):
        text = " ".join(str(v) for v in resp.values())
    else:
        text = str(resp or "")

    # Success signals: a Drive/Docs link, or a plausible file ID (25+ chars of ID alphabet).
    ok = re.search(r"(docs\.google\.com/|drive\.google\.com/)", text) or \
         re.search(r"\b[-\w]{25,}\b", text)
    if ok:
        sys.exit(0)

    print(json.dumps({
        "decision": "block",
        "reason": ("Drive operation returned no file ID or Drive link. Per CLAUDE.md Drive Operation "
                   "Verification: treat this as a FAILURE. Verify with a search before proceeding; "
                   "do not assume the document was created/updated.")
    }))
except Exception:
    pass
sys.exit(0)
PY
exit 0
