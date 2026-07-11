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

0. **Mention Ledger pass (mandatory)**: `python3 .agent/skills/slack-tracker/scripts/mention_ledger.py report` → embed "🔴 Waiting on your reply" in the recap (anything still open at end of day is a carryover candidate for tomorrow's plan); run `... classify` to GLM-triage the day's channel digest. The ledger is the source of truth for unanswered mentions/DMs/threads — never re-derive from raw dumps.
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
5a. **New Ledgers pass (mandatory — each ledger is the SOURCE OF TRUTH for its domain; embed `report` output verbatim, never re-derive from raw dumps):**
   - **Decision log**: `python3 .agent/skills/decision-log/scripts/decision_log.py report` → embed. Then capture today's decided items: for every decision that actually landed today (in a meeting, Slack thread, or doc), run `decision_log.py decide <DEC-id> --decision "<what was decided>"`; brand-new decisions surfaced today get an `add` first (with `--source` + `--source-type`).
   - **Commitments**: `python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py sweep` then `... report` → embed. Where the mechanical auto-close missed something You verifiably delivered today (sent DM, shared doc, MOM evidence), close it manually: `commitment_ledger.py close <COM-id> --note "<evidence>"`.
   - **Waiting-on watchdog**: `python3 .agent/skills/waiting-watchdog/scripts/waiting_watchdog.py report` → embed. Any 🚨 BREACHED item carries into tomorrow's plan as an explicit escalation action.
   - **Stakeholder pages**: `python3 .agent/skills/stakeholders/scripts/stakeholders.py render --all` (regenerates the AUTO blocks on every `Clients/Work/People/` page from today's ledger state; idempotent).
   - **Monday only — outcomes loop**: `python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py report` → embed (the weekly `check` cron ran Monday 08:20 WIB; if a metric shows `needs_reauth`, surface the Metabase re-auth need to You).
5b. **Tracker reconcile (mandatory — keeps the dashboard Today tab honest):**
   - Sweep `journal/state/tickets.json` for open tickets with `due` >= 3 days in the past.
   - For each, verify reality before touching it: You's SENT Slack DMs (`from:@brian`), today's MOMs, email threads, Jira. Evidence it happened -> set `status: done` + a comment with the evidence link. Still real but slipped -> move `due` forward or downgrade priority, with a comment saying why. Riding another workstream -> `status: waiting` / `monitor` and name the vehicle.
   - Never mark done on guesswork; if unverifiable, leave open and note "unverified as of [date]".
   - Refresh `journal/state/portfolio.json` `updated_wib` + any initiative whose health/workstream status changed today, then regenerate the mirror via `python3 .agent/scripts/portfolio_render.py`.
   - Target end-state: zero tickets showing "stale ≥3d" on the dashboard Today tab without an explanatory comment.
6. Sync Fathom meeting notes and Work Document Index.
7. Run GitHub sync to push all changes.
8. Present to You:
   - Accomplishments vs Morning Plan scorecard.
   - Key Slack signals and decisions from today.
   - Open items carrying to tomorrow.
   - Sprint progress delta since morning.

## Quality Rubric (Full)

Apply ALL 9 checkpoints from the Daily Update Quality Rubric. This is mandatory for evening updates.

Run verify_briefing_numbers.py against the harvest sidecar; fix any MISMATCH before delivery. (`python3 .agent/scripts/verify_briefing_numbers.py --briefing <briefing.md> --harvest _temp/harvest_evening_<date>.json`)
