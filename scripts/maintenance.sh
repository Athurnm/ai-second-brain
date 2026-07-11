#!/bin/bash
# Google Calendar Maintenance Script
# This script refreshes OAuth tokens by performing a silent sweep.

# Resolve repo root portably (macOS / WSL / cron): prefer CLAUDE_PROJECT_DIR,
# else derive from this script's own location (scripts/ -> repo root).
REPO_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
LOG_FILE="$REPO_DIR/scripts/maintenance.log"

echo "-----------------------------------------------" >> "$LOG_FILE"
echo "Daily Maintenance Started: $(date)" >> "$LOG_FILE"

cd "$REPO_DIR"

# Refresh all Google Services (Calendar & Drive) via Unified Auth Manager
echo "[$(date)] Running Unified Auth Manager..." >> "$LOG_FILE"
# GNU `timeout` exists on Linux/WSL but not stock macOS; degrade gracefully.
if command -v timeout >/dev/null 2>&1; then
  timeout 600s python3 scripts/auth_manager.py >> "$LOG_FILE" 2>&1
else
  python3 scripts/auth_manager.py >> "$LOG_FILE" 2>&1
fi
AUTH_RC=$?

# Self-report to the Routines panel so harness-health sees this job directly.
# Summary carries the healthy-service ratio (e.g. "3/6") so partial token
# expiries are visible without flapping the job to fail for known-dead profiles.
RATIO=$(grep -o 'Routine Finished: [0-9]*/[0-9]*' "$LOG_FILE" | tail -1 | grep -o '[0-9]*/[0-9]*')
if [ "$AUTH_RC" -eq 0 ]; then
  python3 "$REPO_DIR/.agent/scripts/heartbeat.py" --job maintenance --status ok --summary "token refresh sweep: ${RATIO:-?} services healthy" >> "$LOG_FILE" 2>&1
else
  python3 "$REPO_DIR/.agent/scripts/heartbeat.py" --job maintenance --status fail --summary "auth_manager exit $AUTH_RC (${RATIO:-?} healthy)" >> "$LOG_FILE" 2>&1
fi

echo "Daily Maintenance Finished: $(date)" >> "$LOG_FILE"
echo "-----------------------------------------------" >> "$LOG_FILE"
