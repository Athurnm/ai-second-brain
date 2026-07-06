---
description: Sync recent Fathom recordings into structured local meeting notes per client/project
argument-hint: "[optional: number of recordings or date range]"
---

Run the Fathom sync. Authoritative SOP:

@.agent/workflows/sync-fathom.md

Summary: run `python3 scripts/fathom_to_notes.py` from repo root (Windows: use the wsl.exe prefix from CLAUDE.md), then report which note files were created/updated, grouped by client/project folder. Flag any recording that could not be matched to a calendar event.

Also run `python3 scripts/fathom_registry_sync.py` to update the cumulative **Fathom Meeting Registry** (`journal/fathom_registry.json` + human index `Fathom_Registry.md`). This walks Fathom's `next_cursor` pagination and matches each recording to the Work + personal calendars, so we keep a permanent map of "which Fathom link = which real meeting". Use `--backfill` only to rebuild full history. To answer "what's the Fathom for meeting X on date Y", grep `journal/fathom_registry.json` first.

$ARGUMENTS
