---
description: Evening recap (~21:30 WIB) - full day harvest, accomplishments vs morning plan, Dashboard (Malam) section, todo sync, LinkedIn check. Phase-gated.
argument-hint: "[optional focus]"
---

Run the Evening Update. The two documents below are the authoritative SOP - follow them exactly:

@.agent/workflows/evening-update.md

@.agent/protocols/phased_update_protocol.md

Hard rules (restated because they are non-negotiable):
- Execute as 4 gated steps (Harvest → Summarize → Prioritize → Execute). NEVER jump from Step 1 to Step 4.
- Step 1 runs: `python3 .agent/scripts/daily_update_runner.py --mode evening` from repo root (on Windows, use the wsl.exe prefix from CLAUDE.md).
- Apply ALL 9 checkpoints of `.agent/protocols/daily_update_quality_rubric.md` - mandatory in evening mode.
- Compare against the morning plan in `_temp/daily_plan_[date].md` (scorecard: done / carryover).
- End with the LinkedIn content check ("Udah posting di LinkedIn hari ini?").
- If You corrected your output or process at any point today, offer to run `/learn` to persist the lesson.
- No em-dashes in any output.

Focus hint from You: $ARGUMENTS
