---
name: inbox-hub
description: Unified inbound-inquiry hub — aggregates everything waiting on the owner (Slack mentions/DMs via the mention ledger, Work Gmail, GDoc comments + Jira in phase 2) into journal/state/inbox.json, rendered as the dashboard 📥 Inbox tab with reversible triage and a per-item AI copilot (headless claude opus).
---

# Inbox Hub

One queue for every inbound inquiry so the owner follows up from a single interface instead of sweeping Slack, Gmail, GDocs, and Jira separately. Refreshed by cron every 30 minutes inside the work window, plus a manual "↻ Sweep sekarang" button on the dashboard.

## Sources

| Source | How | Notes |
| :--- | :--- | :--- |
| slack | mirrors OPEN items from `journal/state/slack_mention_ledger.json` | mention ledger stays the Slack SSOT; flow is one-way ledger → inbox (this skill never writes the ledger). When the ledger answers/dismisses an item, the mirrored inbox item auto-closes (`closed_by: source`) on the next sweep. |
| gmail | Gmail API (gmail-connector's `token_gmail_work.json`), query `newer_than:3d -category:promotions -category:social -from:me`, 25 msgs | metadata + snippet only; read-only (never archives/sends) |
| gdoc | STUB | phase 2: Drive comments API mentions |
| jira | STUB | phase 2: jira-connector comment mentions |

## The loop (v3, 2026-07-14)

1. **Sweep** (cron 30-min, work window): harvest **one item per CONVERSATION** — a whole DM, a channel thread, or a Gmail thread — never one row per message. `messages[]` holds the chronological log; a done item that receives new inbound activity auto-REOPENS with its stale draft cleared.
2. **GLM placeholder drafts** (same cron tick): instant 1-3 sentence drafts so nothing sits empty.
3. **inbox-digest** (headless claude sonnet, triggered via the server right after): reads up to 8 open reply-needed conversations, researches repo context (PRDs/MOMs/ledgers/tickets, bounded), and REPLACES the placeholders with drafts that actually answer the ask (`draft_source: claude`). Never sends.
4. **the owner reviews on the dashboard**: conversation bubbles + editable draft + **✅ Approve & kirim** — approving sends AS OWNER via `slack_client.py post` (user token) to the right channel/thread, marks the item done, and keeps the sent permalink. The approve click on the displayed draft IS the explicit Slack-send approval. Gmail threads are copy-only (send API lacks thread-reply support).

## Capabilities (CLI = the single writer of inbox.json)

```bash
python3 .agent/skills/inbox-hub/scripts/inbox_sweep.py sweep              # harvest + merge
python3 .agent/skills/inbox-hub/scripts/inbox_sweep.py set-status <id> --status open|done|ignored
python3 .agent/skills/inbox-hub/scripts/inbox_sweep.py link <id> --ticket T-123   # empty --ticket clears
python3 .agent/skills/inbox-hub/scripts/inbox_sweep.py report             # markdown embed for briefings
```

Triage statuses are an inbox-local overlay — never pushed back to Slack/Gmail — so **every action is reversible** (`set-status --status open` = the dashboard Undo). A source being DOWN never closes its items (failed sources carry their items forward untouched).

## Dashboard integration (dashboard/server.py + public/tab-inbox.js)

- `GET /api/inbox` — items sorted open-first/newest-first + counts + per-source health + each item's latest AI run and draft path.
- `POST /api/inbox-sweep` — manual sweep (sync, 90s cap).
- `POST /api/inbox-action {id, action: done|ignore|reopen|link, ticket?}` — triage via the CLI.
- `POST /api/ai-task {kind:'inbox', ref:<id>, instruction?}` — the per-item AI copilot: headless `claude -p` (model **opus**, the owner's subscription via the WSL-native binary) researches repo context (PRDs, MOMs, ledgers, tickets; may read the full Gmail thread read-only), then writes `journal/ai_drafts/inbox_<id>.md` with Context / Recommendation / Draft reply / Suggested ticket. `instruction` is the owner's free-form directive typed in the drawer ("balas setuju tapi minta timeline", "putuskan opsi A/B"). The prompt hard-forbids any external send; output is always a draft for review. Live tail + result render in the drawer via the shared AI poller.

## Cron (installed 2026-07-14)

```
*/30 12-21 * * 1-5  cd <repo> && inbox_sweep.py sweep && heartbeat.py --job inbox-sweep --status ok
```

Work-window WIB only (machine off outside 12:30–21:45, cron does not replay — per [[feedback_cron_machine_on_window]]). Log: `.agent/skills/inbox-hub/inbox_cron.log`.

## Gotchas

- Slack author names resolve via the mention ledger's `names` map; unmapped IDs render as raw `U…` IDs (never guessed — per [[feedback_no_guessing_names]]). Grow `reference_work_slack_roster` to improve coverage.
- Gmail token dies occasionally → the gmail source reports `ok:false` with a note; items are carried forward, nothing is lost. Re-auth via gmail-connector.
- `done` on a gmail item does NOT archive the email — inbox status is a local overlay only.
- The AI copilot's 409 "already running for this kind+ref" means a run for that item is still in flight — wait for its pill to finish.
