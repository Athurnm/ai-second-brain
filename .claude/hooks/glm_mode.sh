#!/usr/bin/env bash
# SessionStart hook: surface the GLM offload-mode toggle so the Router knows whether to
# offload heavy generation/research/draft to agy-bridge GLM 5.2 (local, zero Claude quota).
FLAG="${CLAUDE_PROJECT_DIR:-.}/.agent/glm_mode.flag"
state="off"
[ -f "$FLAG" ] && state="$(tr -d '[:space:]' < "$FLAG" | tr '[:upper:]' '[:lower:]')"
if [ "$state" = "on" ]; then
  echo "=== GLM MODE: ON ==="
  echo "Offload heavy generation/research/draft sub-tasks to GLM 5.2 via agy-bridge"
  echo "(python3 .agent/skills/agy-bridge/run.py --task draft|research|harvest ...). Claude"
  echo "orchestrates + reviews + applies; do NOT burn Claude tokens on bulk generation."
  echo "Toggle off with: /glm off"
else
  echo "=== GLM MODE: OFF (normal routing) ==="
  echo "Default harness routing. Turn on with /glm on to offload heavy work to GLM 5.2 (cheap, local)."
fi
