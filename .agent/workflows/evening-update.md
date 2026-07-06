---
description: Evening closing update - full day recap, accomplishments vs morning plan, completion tracking
---
// turbo-all

# Evening Update Workflow

This workflow should be triggered each evening at ~21:30 WIB (or on-demand with `/evening-update`) to close the day with a full recap and completion tracking.

## Run Automated Script (Evening Mode)

Execute the daily runner in evening mode for a thorough data harvest.

```bash
// turbo
python .agent/scripts/daily_update_runner.py --mode evening
```

## Email Check (mandatory)

You acts off email too, so sweep it every evening (the runner does NOT pull email).

1. `gmail-connector` (Work, `brian.faridhi@workincentives.com`): `gmail_manager.py list --query "newer_than:1d -category:promotions -category:social" --limit 30`.
2. Surface, today-scoped: (a) **milestones / signals** an email confirms (e.g. an App Store submission accepted, a client approval), (b) threads still **waiting on a You reply / decision** to carry over, (c) **new meeting invites** not yet on the board, (d) doc-comment mentions owed.
3. Tie each to the morning plan, a meeting-prep item, or a todo: did it get done, or does it carry over?
4. Filter noise (order pings, newsletters, Otter/Read/Fireflies/Fathom auto-recaps). Never auto-send email; surface the follow-up, draft only on request (approval-gated like Slack).

## Closing Recap & Completion Tracking

1. The script writes two outputs: `daily_update_evening.md` (human-readable) and `_temp/harvest_evening_[date].json` (structured sidecar).
2. **For synthesis, read `_temp/harvest_evening_[date].json` first** -- it is a compact structured JSON (sections: slack, jira, calendar, files_modified, files_created, backlogs, fathom, morning_plan, portfolio) and avoids re-reading the full 150-180 KB markdown dump. Fall back to `daily_update_evening.md` only if the JSON is missing or a section is empty. The markdown remains the user-facing deliverable and is NOT deleted.
3. Cross-reference the morning's proposed priorities from `_temp/daily_plan_[date].md`:
   - Mark completed items.
   - Identify carryover items that need to move to tomorrow.
4. Update `Dashboard.md`:
   - Create/update the `### [Date] (Malam): Closing & Recap` section.
   - Update project statuses and backlogs.
   - Archive daily entries older than 7 days to `journal/daily_logs/`.
   - Ensure the visual dashboard is live: run `bash .agent/scripts/ensure_dashboard.sh`. Idempotent — it exits if `localhost:3737` is already up and restarts the server if it died. The server serves `Dashboard.md` live, so this surfaces the freshly-written recap. Do NOT run `dashboard_sync.py` here: it would overwrite the hand-written `(Malam)` section.
5. Update `journal/todo.md`:
   - Mark completed items as `[x]`.
   - Flag stale items with no activity in 7+ days.
6. Sync Fathom meeting notes and Work Document Index.
7. Run GitHub sync to push all changes.
8. Present to You:
   - Accomplishments vs Morning Plan scorecard.
   - Key Slack signals and decisions from today.
   - Open items carrying to tomorrow.
   - Sprint progress delta since morning.

## Standing Watch — AI Circle Launch Sprint (until 12 Jul 2026)

Until the AI Circle workshop launches (Sun 12 Jul 2026), every daily update MUST surface the launch sprint as its own block.

**SOT (single source of truth) = the "You Weekly Report & To-Do" doc** — GDoc `<YOUR_DRIVE_ID>` (personal account, owner you@example.com), local mirror `~/antigravity-projects/You/AI_Circle_WEEKLY_TODO.md`. NOT `AI_Circle_EXECUTION.md` (that is now strategy/blitz-calendar only).

1. Read the SOT (local mirror first; if You says it changed, re-pull the GDoc via MCP `read_file_content` and refresh the mirror). Per-owner tables: Teammate (A1–A12), Teammate (R1–R4), Tim (T1–T3), You (B1–B2).
2. For each item due **today or earlier** still `⬜`, flag it explicitly as AT RISK / SLIPPING — name owner, deadline, what it gates. Watch hardest: **Teammate's marketing course (R1), hard deadline 6 Jul** — gates the launch ad campaign.
3. Cross-check the AI Circle Google Calendar reminders (personal profile, 1–12 Jul) so no deadline passes silently.
4. If You confirms an item done/changed, update the local mirror row, then push to the SOT GDoc (`gdrive_manager.py update --id 1Aw57... --file ...WEEKLY_TODO.md --convert --account personal`) and confirm the link.
5. Output a one-line health verdict: `AI Circle launch: ON TRACK / AT RISK (reason)`.

## Quality Rubric (Full)

Apply ALL 9 checkpoints from the Daily Update Quality Rubric. This is mandatory for evening updates.

Run verify_briefing_numbers.py against the harvest sidecar; fix any MISMATCH before delivery. (`python3 .agent/scripts/verify_briefing_numbers.py --briefing <briefing.md> --harvest _temp/harvest_evening_<date>.json`)
