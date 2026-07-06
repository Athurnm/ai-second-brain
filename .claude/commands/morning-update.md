---
description: Morning prep (~09:30 WIB) - overnight sweep, top-5 priorities, Dashboard (Pagi) section. Phase-gated, waits for You's alignment.
argument-hint: "[optional focus]"
---

Run the Morning Update. The two documents below are the authoritative SOP - follow them exactly:

@.agent/workflows/morning-update.md

@.agent/protocols/phased_update_protocol.md

Hard rules (restated because they are non-negotiable):
- Execute as 4 gated steps (Harvest → Summarize → Prioritize → Execute). NEVER jump from Step 1 to Step 4.
- Step 1 runs: `python3 .agent/scripts/daily_update_runner.py --mode morning` from repo root (on Windows, use the wsl.exe prefix from CLAUDE.md).
- Apply the morning subset of `.agent/protocols/daily_update_quality_rubric.md` (checkpoints 1, 2, 4, 7, 8).
- Wait for You's alignment before reordering `journal/todo.md` priorities.
- No em-dashes in any output.

Focus hint from You: $ARGUMENTS
