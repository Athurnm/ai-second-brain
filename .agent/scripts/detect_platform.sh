#!/usr/bin/env bash
# Single source of truth for machine awareness across macOS, WSL, and Windows.
#
# Run at session start:
#   bash .agent/scripts/detect_platform.sh
#
# Prints four lines the agent (Claude / Gemini) reads to adapt every skill call:
#   PLATFORM     macos | wsl | windows
#   REPO_ROOT    absolute repo path for THIS machine
#   RUN_PREFIX   string to prepend to a Python skill command (empty on macOS/WSL)
#   RUN_SUFFIX   string to append   to a Python skill command (empty on macOS/WSL)
#
# On macOS and WSL, run skills natively:   python3 .agent/skills/.../x.py ...
# On native Windows, wrap them:            <RUN_PREFIX>python3 .agent/skills/.../x.py ...<RUN_SUFFIX>
# NEVER use wsl.exe on macOS -- the binary does not exist there.

WSL_ROOT="."

case "$(uname -s 2>/dev/null)" in
  Darwin)               PLATFORM="macos"   ;;
  Linux)                PLATFORM="wsl"     ;;   # You's Linux is always WSL
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  *)                    PLATFORM="windows" ;;   # uname missing => native Windows
esac

if [ "$PLATFORM" = "windows" ]; then
  # Native Windows: proxy into WSL (credentials/tokens live in the WSL filesystem)
  REPO_ROOT="$WSL_ROOT"
  RUN_PREFIX="wsl.exe bash -c \"cd $WSL_ROOT && "
  RUN_SUFFIX="\""
else
  # macOS or WSL: run natively from wherever this repo is checked out.
  # Prefer $CLAUDE_PROJECT_DIR (set by Claude Code); fall back to this script's repo.
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
  RUN_PREFIX=""
  RUN_SUFFIX=""
fi

echo "PLATFORM=$PLATFORM"
echo "REPO_ROOT=$REPO_ROOT"
echo "RUN_PREFIX=$RUN_PREFIX"
echo "RUN_SUFFIX=$RUN_SUFFIX"
