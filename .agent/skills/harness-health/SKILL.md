---
name: harness-health
description: Monthly self-check of the harness - cron jobs vs heartbeat/log signal, state-file staleness vs an expectation table, unused skills, and (--full) read-only auth probes per connector token. Run monthly or on-demand when something in the harness feels broken.
---

## Capabilities

- **Cron health**: reads the installed `crontab -l`, scopes findings to lines that belong to THIS repo (matched by absolute repo path), and cross-references each known repo cron job against `dashboard-data/agent_heartbeat.jsonl` (preferred), its own state file's timestamp field, or its log file's mtime. Flags a job **silent** when there has been no activity for more than 3x its expected cadence, plus any recent `fail` rows or `needs_reauth` flags in the last 30 days. Crontab lines belonging to other projects (e.g. the You repliz/goakal blocks that share this crontab) are counted and reported as present but are **never evaluated or modified**.
- **State-file staleness**: checks each ledger/state file against a fixed expectation table (mention_ledger 2h, commitments 12h, waiting_on 3h, outcomes 8d, tickets 48h, decisions exempt). Files that don't exist yet (a sibling component not built/landed yet) are reported `not_built_yet`, never treated as a failure.
- **Unused skills**: every directory under `.agent/skills/` that is never mentioned in `journal/activity_log.jsonl` in the last 60 days is flagged `info` (not necessarily dead - some skills are used interactively without an activity_log entry, so treat this as a lead to check, not a verdict).
- **`--full` auth probes**: cheapest possible read-only call per connector that has a `token.env` under `.agent/skills/*/token.env` - Slack `auth.test`, Fathom `--action list --limit 1`, Jira `daily-digest`, Google Calendar `list --days-forward 0`. Metabase is always reported `skip` (its session token is a manual Google-OAuth cookie, not probed automatically). A missing `token.env` skips gracefully - it is never treated as a failure.

## Usage

```bash
python3 .agent/skills/harness-health/scripts/harness_health.py run          # quick (no network probes)
python3 .agent/skills/harness-health/scripts/harness_health.py run --full   # + auth probes
python3 .agent/skills/harness-health/scripts/harness_health.py report       # fail+warn findings, briefing-ready markdown
python3 .agent/skills/harness-health/scripts/harness_health.py report --all # + info-level (unused skills, other-repo cron note)
```

State: `journal/state/harness_health.json` (last run's findings + per-check detail, overwritten each run - this is a point-in-time health snapshot, not a lifecycle ledger).
Monthly report: `journal/harness_health/<YYYY-MM>.md` (one appended section per run, durable history).

## Cron (designed, not installed by this builder)

Per the plan: `0 9 1 * *` monthly, with `--full`:

```
0 9 1 * * flock -n /tmp/harness_health.lock python3 <repo>/.agent/skills/harness-health/scripts/harness_health.py run --full >> <repo>/.agent/skills/harness-health/harness_health_cron.log 2>&1
```

Installing this line, wiring the `journal/state/routines.json` row, and any `--full` heartbeat writes are Stage B integration work, not this builder's scope (no crontab edits here).

## Notes

- Clone of `mention_ledger.py`'s conventions: stdlib only, `BASE_DIR` derived from `__file__`, atomic `.tmp` + `os.replace()` state writes, `API_PAUSE=0.15` between network calls.
- `tickets.json`, other components' state files (`commitments.json`, `waiting_on.json`, `decisions.json`, `outcomes.json`, `people.json`), the dashboard, and all workflows/commands are **read-only** from this script's point of view - it never writes to them.
- The cron registry (`CRON_REGISTRY` in the script) is hand-maintained. When a new component lands its own cron line (commitment-ledger, waiting-watchdog, premeeting-cards, outcomes-loop), add a matching entry so this check covers it - until then those jobs show up only in the `DESIGNED_CRON` reference list, not evaluated.
- `run` always writes one `harness-health` row to `dashboard-data/agent_heartbeat.jsonl` (status `fail` if any finding is `severity: fail`, else `ok`) so a broken monthly check is itself visible on the Routines panel.
