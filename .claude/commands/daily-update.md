---
description: Daily update - auto-detects WIB time; runs morning prep before 17:00 WIB (or if no morning ran yet), evening recap after
argument-hint: "[optional focus, or 'morning'/'evening' to force a mode]"
---

Determine current WIB time first: run `TZ=Asia/Jakarta date '+%H:%M %A %Y-%m-%d'`.

If $ARGUMENTS forces a mode ("morning" or "evening"), obey it. Otherwise (You's rule: morning until 17:00 WIB, since his work window starts ~12:30):
- Before 17:00 WIB AND no morning update has run yet today → follow `.claude/commands/morning-update.md`
- 17:00 WIB or later, or morning already ran today → follow `.claude/commands/evening-update.md`

State which mode you chose and why (current WIB time) before starting.
