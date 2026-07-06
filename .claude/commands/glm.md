# /glm

Toggle **GLM offload mode** on/off. When ON, the Router offloads heavy generation / research /
draft sub-tasks to GLM 5.2 via agy-bridge (local agy CLI, **zero Claude Code quota**); Claude
stays the orchestrator (plans, reviews, applies). When OFF, normal harness routing. Default OFF.

**Usage:** `/glm on` · `/glm off` · `/glm status`

**What to do when invoked:**
1. Resolve the flag file: `.agent/glm_mode.flag`.
2. `on` → write `on`; `off` → write `off`; `status` → read + report.
   ```bash
   echo on  > .agent/glm_mode.flag    # or: echo off
   cat .agent/glm_mode.flag
   ```
3. Confirm the new state to You. The SessionStart hook (`glm_mode.sh`) surfaces it each session;
   within the current session, honor the new state immediately.

**Behavior when ON:** route bulk reads → `agy-bridge --task harvest`; content/code/copy generation →
`--task draft`; analysis/research → `--task research`; cross-model critique → `--task critic`.
Keep orchestration, final judgment, and client-facing synthesis on Claude (per CLAUDE.md routing).
This is a convenience toggle; the underlying agy-bridge capability routing is unchanged.