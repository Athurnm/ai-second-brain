#!/usr/bin/env bash
# PostToolUse hook on Write|Edit: warn when an em-dash/en-dash lands in a repo .md/.txt file.
# You's #1 style rule (no-emdash skill) - enforced deterministically, warning-only
# (em-dashes are legitimate when quoting transcripts, so never block).
# Fast-path: grep stdin first - files without dashes exit in milliseconds, no python spawn.
# Contract: always exit 0.
set -u

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0

# Fast-path: no em-dash/en-dash anywhere in the payload -> done.
printf '%s' "$input" | grep -q $'—\|–' || exit 0

command -v python3 >/dev/null 2>&1 || exit 0

HOOK_INPUT="$input" python3 - <<'PY' 2>/dev/null || exit 0
import json, os, sys

try:
    d = json.loads(os.environ.get("HOOK_INPUT", "{}"))
    ti = d.get("tool_input") or {}
    path = str(ti.get("file_path") or "")
    if not path.endswith((".md", ".txt")):
        sys.exit(0)

    # Only police files inside this repo; skip dirs that quote external content.
    project = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    norm = os.path.abspath(path)
    if not norm.startswith(os.path.abspath(project)):
        sys.exit(0)
    skip = ("/_archive/", "/.agent/", "/node_modules/", "/scratch/", "/_temp/")
    if any(s in norm for s in skip):
        sys.exit(0)

    content = str(ti.get("content") or "") + str(ti.get("new_string") or "")
    if "—" not in content and "–" not in content:
        sys.exit(0)

    rel = os.path.relpath(norm, os.path.abspath(project))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (f"Em-dash detected in {rel}. Repo rule (no-emdash skill): replace "
                              "em-dash/en-dash characters with - or -- before delivering this document.")
    }}))
except Exception:
    pass
sys.exit(0)
PY
exit 0
