#!/usr/bin/env bash
# SessionStart hook: surface the offload-mode toggle so the Router knows whether to
# offload heavy generation/research/draft to agy-bridge (flat-rate subscription, zero
# Claude quota). Backend is Gemini via the agy CLI since z.ai/GLM was retired 2026-07-27.
# The flag file and /glm command keep their historical names.
FLAG="${CLAUDE_PROJECT_DIR:-.}/.agent/glm_mode.flag"
state="off"
[ -f "$FLAG" ] && state="$(tr -d '[:space:]' < "$FLAG" | tr '[:upper:]' '[:lower:]')"
if [ "$state" = "on" ]; then
  echo "=== OFFLOAD MODE: ON (Gemini via agy-bridge) ==="
  echo "Offload heavy generation/research/draft sub-tasks to agy-bridge"
  echo "(python3 .agent/skills/agy-bridge/run.py --task draft|research|harvest ...). Claude"
  echo "orchestrates + reviews + applies; do NOT burn Claude tokens on bulk generation."
  echo "Backend: Gemini via agy. z.ai/GLM retired 2026-07-27, do not pin --backend zai."
  echo "Toggle off with: /glm off"
else
  echo "=== OFFLOAD MODE: OFF (normal routing) ==="
  echo "Default harness routing. Turn on with /glm on to offload heavy work to Gemini via agy-bridge."
fi
