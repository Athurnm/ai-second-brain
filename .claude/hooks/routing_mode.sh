#!/usr/bin/env bash
# SessionStart: surface which model this session is on, so the main loop knows
# which direction to delegate (down to haiku/sonnet, up to fable) per CLAUDE.md ## Subagents.
# Non-blocking, informational only.
#
# Model comes from harness_config.py (backed by detect_runtime.sh, which reads the
# session transcript JSONL). That is authoritative because the SessionStart hook
# payload only carries a "model" field on some call sites -- it is absent on
# resume and clear -- which used to make this hook print "unknown" most of the time.
# The payload parse below is kept only as a last-resort fallback.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

MODEL="unknown"
TIER="unknown"
if command -v python3 >/dev/null 2>&1 && [ -f "$REPO_ROOT/.agent/scripts/harness_config.py" ]; then
  CFG_OUT=$(cd "$REPO_ROOT" && python3 .agent/scripts/harness_config.py --json 2>/dev/null)
  if [ -n "$CFG_OUT" ]; then
    MODEL=$(printf '%s' "$CFG_OUT" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unknown"); raise SystemExit
print(d.get("model") or "unknown")
' 2>/dev/null || echo unknown)
    TIER=$(printf '%s' "$CFG_OUT" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unknown"); raise SystemExit
print(d.get("tier") or "unknown")
' 2>/dev/null || echo unknown)
  fi
fi

# Fallback only: parse the SessionStart payload if the config lookup above came
# up empty. The payload is unreliable (missing on resume/clear) which is exactly
# why the config path above must win whenever it has an answer.
if [ "$MODEL" = "unknown" ]; then
  PAYLOAD=""
  if [ ! -t 0 ]; then
    PAYLOAD=$(timeout 2 cat 2>/dev/null || true)
  fi
  if [ -n "$PAYLOAD" ] && command -v python3 >/dev/null 2>&1; then
    MODEL=$(printf '%s' "$PAYLOAD" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unknown"); raise SystemExit
m = d.get("model") or {}
if isinstance(m, dict):
    print(m.get("display_name") or m.get("id") or "unknown")
else:
    print(m or "unknown")
' 2>/dev/null || echo unknown)
  fi
fi

echo "=== ROUTING MODE ==="
echo "Session model: ${MODEL} (tier: ${TIER})."
cat <<'EOF'
Announce the agent plan, do NOT gate on it. Before any task that will spawn
subagents or run a Workflow, emit ONE compact block first, then start work in
the SAME turn without waiting for approval:

  Plan agent: <1-line what> | <tier>: <who does what> | main loop: <what stays>

Routing (CLAUDE.md ## Subagents): match model to the WORK, not to the session.
  - DOWN (always): harvest / lookup / routine draft / conversion -> haiku|sonnet,
    even when this session is on a flagship model.
  - UP (when needed): complex decomposition or ambiguous multi-step planning ->
    Agent(model:"fable", effort:"xhigh"); on a fable session, spawn opus for a
    second flagship lens.
  - Main loop keeps final synthesis, judgment, and the owner-facing output.
Skip the block for single-tool or trivial work. Approval gates that already exist
(Slack sends, Drive writes) still apply and are unaffected by this.
EOF
