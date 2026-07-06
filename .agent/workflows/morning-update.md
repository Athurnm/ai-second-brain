---
description: Morning prep update - sweep overnight signals, set today's priorities, and prepare the workday focus
---
// turbo-all

# Morning Update Workflow

This workflow should be triggered each morning at ~09:30 WIB (or on-demand with `/morning-update`) to prepare You's daily priorities and review overnight signals.

## Run Automated Script (Morning Mode)

Execute the daily runner in morning mode for a fast, priority-focused sweep.

```bash
// turbo
python .agent/scripts/daily_update_runner.py --mode morning
```

## Calendar-Driven Meeting Prep (mandatory)

The day is built around meetings, so the calendar is a first-class source, not an afterthought.

1. Pull today's Work calendar (`gcal_manager.py list --profile work --days-back 0 --days-forward 1`). For EVERY meeting that needs You's input/decision/output (skip pure standups/prayer/all-day), create a **per-meeting prep item** as a ticket in `journal/state/tickets.json` (id `MTG-<TAG>-<MMDD>`, `due` = today, `kind: self`, owner You, correct `project`). This is what surfaces it on the `localhost:3737` Today board, so a meeting like the Online Catalogue weekly is never lost.
2. For each prep item, note the goal, the doc/Slack/email inputs to read first, and any scheduling conflicts (two events same slot). Link them.
3. Flag calendar conflicts and any invite-time mismatches (an emailed updated-invite time differing from the live calendar) explicitly.

## Email Check (mandatory)

You acts off email too, so sweep it every morning.

1. `gmail-connector` (Work, `brian.faridhi@workincentives.com`): `gmail_manager.py list --query "newer_than:2d -category:promotions -category:social" --limit 25`.
2. Surface: (a) anything that is an **input for a meeting today** (e.g. a shared sheet/BRD/doc the meeting depends on), (b) **new meeting invites** not yet on the board, (c) threads **waiting on a You reply / decision**, (d) doc-comment mentions.
3. For each, state clearly whether it **needs and can be followed up by email** vs FYI, and tie it to the relevant meeting-prep item or todo.
4. Never auto-send email; surface the follow-up, draft only on request (approval-gated like Slack).

## DM Sweep & Prior-Day Backfill (mandatory)

The channel skim (5 msgs/channel) misses DM threads, where the highest-signal asks land. Every morning:

1. Deep-read open DMs, especially **YourManager** (`<SLACK_ID>`) and other leadership. **ANY message from YourManager is high priority by default** and must surface in the day's signal.
2. If **NO evening update ran the prior day**, also pull yesterday's **Fathom** meeting outcomes (registry + MCP) so closed-meeting decisions are not lost, since Fathom is otherwise an evening-only harvest step.

## Priority Setting & Summary

1. The script writes two outputs: `daily_update_morning.md` (human-readable) and `_temp/harvest_morning_[date].json` (structured sidecar). It also saves the proposed plan to `_temp/daily_plan_[date].md`.
2. **For synthesis, read `_temp/harvest_morning_[date].json` first** -- it is a compact structured JSON (sections: jira, calendar, slack, todo_p0) and avoids re-reading the full 100+ KB markdown dump. Fall back to `daily_update_morning.md` only if the JSON is missing or a section is empty. The markdown remains the user-facing deliverable and is NOT deleted.
3. Update `Dashboard.md`:
   - Create/update the `### [Date] (Pagi): Priorities & Prep` section.
   - Refresh the Calendar Focus for today.
   - Sync Jira sprint snapshot.
   - Ensure the visual dashboard is live: run `bash .agent/scripts/ensure_dashboard.sh`. Idempotent — it exits if `localhost:3737` is already up and restarts the server if it died. The server serves `Dashboard.md` live, so this surfaces the freshly-written section. Do NOT run `dashboard_sync.py` here: it would overwrite the hand-written `(Pagi)` section.
4. Present to You:
   - Today's calendar with P0/P1 meeting tags.
   - Top 5 proposed priorities (sourced from todo.md, overnight Slack, Jira).
   - Carryover items from yesterday.
   - Any overnight blockers or urgent messages.
5. Wait for You's alignment before updating todo.md priority order.

## Focus Block Enrichment (Calendar)

After You aligns on priorities, any **focus block** created/refreshed on his Work calendar (`gcal_manager.py create --profile work`) must carry a **rich `--desc`**, never just a terse one-liner. You acts directly off the calendar, so each block must answer: *what, why, where do I go, what do I do, who do I tell* — with clickable links. Use this template:

```
🎯 WHY: <one-line reason this matters now / the trigger>
📋 Ticket: <ME-XXX>
🔗 Docs: <Google Doc / PRD / Figma links>
💬 Context: <Slack permalink to the originating thread + who raised it>
✅ DO: <the concrete decision/output to produce in this block>
➡️ THEN: <who to communicate the result to + which channel>
```

Rules:
- Always hyperlink cited docs/threads (per [[feedback_always_link_cited_docs]]); never leave a source as plain text.
- Resolve every Slack ID to a name before writing it (per [[feedback_no_guessing_names]]).
- `gcal_manager.py` has **no `update`** action and MCP Calendar points at Secondary — so the rich `--desc` must be set at **create** time. For an existing block that can't be edited, surface the enriched brief in the Dashboard `(Pagi)` section instead and flag that the calendar copy is terse.

## Standing Watch — AI Circle Launch Sprint (until 12 Jul 2026)

Until the AI Circle workshop launches (Sun 12 Jul 2026), every morning update MUST surface the launch sprint as its own block.

**SOT = "You Weekly Report & To-Do"** — GDoc `<YOUR_DRIVE_ID>` (personal, you@example.com), local mirror `~/antigravity-projects/You/AI_Circle_WEEKLY_TODO.md`. NOT `AI_Circle_EXECUTION.md`.

1. Read the SOT mirror. Per-owner: Teammate (A1–A12), Teammate (R1–R4), Tim (T1–T3), You (B1–B2).
2. Flag any item due **today or earlier** still `⬜` as AT RISK — owner + deadline + what it gates. Hardest blocker: **Teammate's marketing course (R1), hard deadline 6 Jul** (gates the launch ad campaign).
3. Pull today-due Teammate/Teammate items + You's own gate items into the day's view so they don't slip behind Work work.
4. One-line health verdict: `AI Circle launch: ON TRACK / AT RISK (reason)`.

## Quality Rubric (Morning Subset)

Apply checkpoints 1 (Source Citation), 2 (Cross-Reference & Completion), 4 (Staleness Scoring), 7 (Roster & Team Ownership), and 8 (Keyword Sweeper) from the Daily Update Quality Rubric. Other checkpoints are optional in morning mode.

Run verify_briefing_numbers.py against the harvest sidecar; fix any MISMATCH before delivery. (`python3 .agent/scripts/verify_briefing_numbers.py --briefing <briefing.md> --harvest _temp/harvest_morning_<date>.json`)
