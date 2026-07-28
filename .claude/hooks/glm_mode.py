#!/usr/bin/env python3
"""SessionStart hook: surface the offload-mode toggle so the Router knows whether to
offload heavy generation/research/draft to agy-bridge (flat-rate subscription, zero Claude
quota). Backend is Gemini via the agy CLI since z.ai/GLM was retired 2026-07-27; the flag
file and /glm command keep their historical names.

Cross-platform replacement for glm_mode.sh.

Contract: always exit 0; never block a session.
"""
import os
import sys
from pathlib import Path

DEFAULT_PROJECT_DIR = "."

def main():
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or DEFAULT_PROJECT_DIR
    flag_path = Path(project_dir) / ".agent" / "glm_mode.flag"

    state = "off"
    if flag_path.is_file():
        try:
            raw = flag_path.read_text(encoding="utf-8")
        except Exception:
            raw = ""
        state = "".join(raw.split()).lower()

    if state == "on":
        print("=== OFFLOAD MODE: ON (Gemini via agy-bridge) ===")
        print("Offload heavy generation/research/draft sub-tasks to agy-bridge")
        print("(python3 .agent/skills/agy-bridge/run.py --task draft|research|harvest ...). Claude")
        print("orchestrates + reviews + applies; do NOT burn Claude tokens on bulk generation.")
        print("Backend: Gemini via agy. z.ai/GLM retired 2026-07-27, do not pin --backend zai.")
        print("Toggle off with: /glm off")
    else:
        print("=== OFFLOAD MODE: OFF (normal routing) ===")
        print("Default harness routing. Turn on with /glm on to offload heavy work to Gemini via agy-bridge.")

    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
