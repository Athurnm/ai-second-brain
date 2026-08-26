---
name: command-queue
description: Turns the owner's task-comments (by:"owner" comments on dashboard tickets) into auto-dispatched headless `claude -p` worker runs, routing each to the right model+effort per the CLAUDE.md table. Scan → triage → spawn. Safe by construction — workers never send external messages; anything needing a send is drafted and flagged.
---

# Command Queue

the owner writes commands as comments on dashboard tickets (`journal/state/tickets.json`,
`comments[]` with `by:"owner"`). Before this, nothing executed them — they sat as
context until a session happened to read the ticket, so most were never actioned
(e.g. S-06 "cek status di jira…", ME-EARN-Teammate-DESIGN "ask Teammate for an update…").

This skill closes that gap: it picks up new command-comments and auto-dispatches a
detached `claude -p` worker to do the work, choosing the model+effort by task category.

## Commands

```bash
CQ=.agent/skills/command-queue/scripts/command_queue.py

python3 $CQ scan                    # enqueue new by:owner command comments
python3 $CQ baseline                # mark current backlog seen-but-not-run (ONCE, at activation)
python3 $CQ dispatch                # dry-run: triage + show model routing plan
python3 $CQ dispatch --live         # actually spawn workers (max 2 concurrent)
python3 $CQ dispatch --live --limit 3
python3 $CQ report                  # queue status (pending/dispatched/done/skipped)
```

## How it routes model + effort

A single cheap **haiku triage call** classifies each pending command into one of the
six CLAUDE.md categories, then the worker spawns with the matching tier (this IS the
Router role from CLAUDE.md, made mechanical):

| category | model | effort | thinking directive |
| :-- | :-- | :-- | :-- |
| harvest / lookup | haiku | low | — |
| draft | sonnet | medium | "think it through" |
| review | sonnet | medium | "think carefully, be adversarial" |
| synthesize | opus | high | "think hard, weigh + prioritise" |
| strategize | opus | high | "ultrathink, reason adversarially" |

Effort is carried as a thinking directive in the worker prompt (headless has no
`--effort` flag). Triage also tags `risk: needs_send` when fulfilling the command
clearly needs a Slack/email send — those still run, but draft-only (see Safety).

## Safety — DRAFT-ONLY (the owner's chosen autonomy level, 13 Jul 2026)

Workers can **read/research freely but write NOTHING except their draft**. The tool
whitelist (in `_spawn_worker`) is:

- Read, Grep, Glob, WebFetch, WebSearch
- `Write(journal/ai_drafts/**)` — the ONLY write path, scoped to the drafts dir
- read-only MCP: Atlassian (search/get Jira), Fathom (all read), Drive (search/read/meta),
  Slack (search/read thread+channel)

No Edit, no arbitrary Bash, no ticket mutation, no send tools, no Jira/Drive write tools.
A worker **cannot** touch client state, send a message, or edit a repo/ticket unattended —
it produces a draft the owner applies. This is enforced by the whitelist, not just the prompt.

- Each worker writes `journal/ai_drafts/cmd_<key>.md` with sections: What I found /
  Proposed action (full ready-to-send text if it's a message) / Needs the owner.
- On finish, the item moves to state **`review`** = awaiting the owner's approval.
- Max 2 concurrent workers; a comment is keyed `<ticket_id>:<comment_ts>` so it runs once.
- **`baseline` at activation** marks the historical backlog seen-but-not-run, so only
  comments written AFTER activation get dispatched.

## Approval surface (dashboard)

`review` items appear on the dashboard **Today** tab in the **"Commands awaiting your
approval"** card (`/api/command-queue` → `approvalsCard()`), newest first. Each row:
- **📄 review draft** → opens `journal/ai_drafts/cmd_<key>.md` in the Drawer (rendered).
- **✓ done** → `POST /api/command-queue-ack` → CLI `ack` → clears it (review → done).

CLI equivalents: `report` foregrounds the "📋 Awaiting your approval" section;
`ack <key|ticket_id>` clears one.

## State & outputs

- Queue: `journal/state/command_queue.json` — `items[<key>]` with state
  `pending|dispatched|done|skipped`, plus the chosen model/effort/run_id.
- Worker logs: `journal/ai_runs/cmd-*.log` (sentinel `AI_TASK_DONE rc=N`).
- Drafts / outcome summaries: `journal/ai_drafts/cmd_<key>.md`.

## Prerequisite / gotcha

- **Headless `claude -p` must be authenticated in the cron/non-interactive context.**
  This is the SAME dependency as the dashboard `POST /api/ai-task` feature. If a worker
  log shows `Not logged in · Please run /login`, the credential isn't resolving in that
  shell — fix auth (re-login or a long-lived token/API key for unattended cron) before
  relying on `--live`. `scan`/`baseline`/`report` need no auth; only `dispatch --live`
  and the triage step do (triage degrades gracefully: it leaves items pending).

## Cron (design only — install once the owner greenlights + auth is confirmed)

Runs inside the owner's machine-on window (12:30–21:45 WIB) per [[feedback_cron_machine_on_window]]:

```
*/20 12-21 * * 1-5 flock -n /tmp/command_queue.lock /bin/bash -c 'cd <repo> && python3 .agent/skills/command-queue/scripts/command_queue.py scan && python3 .agent/skills/command-queue/scripts/command_queue.py dispatch --live && python3 .agent/scripts/heartbeat.py --job command-queue --status ok' >> .agent/skills/command-queue/command_queue_cron.log 2>&1
```
