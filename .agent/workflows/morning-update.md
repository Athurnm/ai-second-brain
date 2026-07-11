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

## Mention Ledger, DM Sweep & Prior-Day Backfill (mandatory)

The channel skim (5 msgs/channel) misses DM threads and old-thread replies. The **Mention Ledger** (`.agent/skills/slack-tracker/scripts/mention_ledger.py`, cron `*/30`) is the mechanical safety net for both. Every morning:

0. **Run the ledger first**: `python3 .agent/skills/slack-tracker/scripts/mention_ledger.py report` → embed the "🔴 Waiting on your reply" list in the briefing verbatim (priority/YourManager items on top, with age + permalink). Then `... classify` to GLM-triage the channel digest and fold `needs_reply`/`action_item` results into the day's signal. The ledger is the source of truth for unanswered mentions — do NOT re-derive them from raw channel dumps.
1. Deep-read open DMs, especially **YourManager** (`<SLACK_ID>`) and other leadership. **ANY message from YourManager is high priority by default** and must surface in the day's signal.
2. If **NO evening update ran the prior day**, also pull yesterday's **Fathom** meeting outcomes (registry + MCP) so closed-meeting decisions are not lost, since Fathom is otherwise an evening-only harvest step.
3. If **NO evening update ran the prior day**, also run the **tracker reconcile** from `.agent/workflows/evening-update.md` step 5b (verify long-overdue tickets against sent DMs/MOMs/email, update status with evidence) so the dashboard Today tab does not accumulate stale items.

## New Ledgers & Cards (mandatory)

Each ledger below is the **SOURCE OF TRUTH** for its domain — embed its `report` output verbatim and do NOT re-derive its items from raw Slack/Fathom/calendar dumps.

1. **Pre-meeting cards**: `python3 .agent/skills/premeeting-cards/scripts/premeeting_cards.py generate` (idempotent; cron `45 7 * * 1-5` usually already ran — rerun is safe), then `... report` → embed the index verbatim. Cards live in `journal/premeeting/<date>/`; link each card next to its meeting in the briefing.
2. **Commitments (You owes others)**: `python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py report` → embed verbatim (overdue first). If the last `sweep` printed `FALLBACK_TO_CLAUDE` or `pending_candidates` remain in `journal/state/commitments.json`, Claude extracts those candidates itself (read each candidate's text, decide if it is a real commitment, identify recipient + due) and registers the results via `commitment_ledger.py add ...` — do not leave candidates to rot.
3. **Waiting-on watchdog (others owe You)**: `python3 .agent/skills/waiting-watchdog/scripts/waiting_watchdog.py sweep --check-slack` (the Slack-thread close check is SOP-only, never cron'd), then `... report` → embed verbatim. Every 🚨 BREACHED line becomes an **explicit escalation action in today's Top-5** (who to ping, on which channel, per the item's `escalate_to`/`escalation_path`).
4. **Decision log**: `python3 .agent/skills/decision-log/scripts/decision_log.py report` → embed verbatim (overdue-open decisions on top). Surface any decision whose deadline is today/past as a today-action.
5. **Reply queue (drafts only)**: `python3 .agent/skills/reply-queue/scripts/reply_queue.py draft --limit 15`, then `... report` → embed, and link today's draft file `journal/reply_drafts_<date>.md` in the briefing. If the file contains a `## FALLBACK_TO_CLAUDE` section, Claude drafts those replies itself in You's voice: plain flowing prose, no emoji, no numbered-bold lists. Drafts are never sent from here — sending stays approval-gated via `/slack-draft`.

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

## Quality Rubric (Morning Subset)

Apply checkpoints 1 (Source Citation), 2 (Cross-Reference & Completion), 4 (Staleness Scoring), 7 (Roster & Team Ownership), and 8 (Keyword Sweeper) from the Daily Update Quality Rubric. Other checkpoints are optional in morning mode.

Run verify_briefing_numbers.py against the harvest sidecar; fix any MISMATCH before delivery. (`python3 .agent/scripts/verify_briefing_numbers.py --briefing <briefing.md> --harvest _temp/harvest_morning_<date>.json`)
