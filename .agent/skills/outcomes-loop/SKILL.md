---
name: outcomes-loop
description: Post-launch outcomes loop - tracks shipped features against PRD success-criteria metrics, pulled from Mixpanel and Metabase on a weekly cadence.
---

# Outcomes Loop

Closes the loop between "we shipped it" and "did it work." For each shipped
feature (tied to its PRD), attach one or more success-criteria metrics backed
by a Mixpanel or Metabase query. `check` pulls the latest value, compares it
against the target/direction, and flags on_track / off_track / no_data /
needs_reauth — mechanically, no LLM involved.

Clones the `mention_ledger.py` conventions: `BASE_DIR` derived from
`__file__`, atomic `.tmp` + `os.replace()` state writes, argparse
subcommands, stdlib-only Python.

State: `journal/state/outcomes.json`

## Capabilities

- Register a shipped feature and link it to its PRD.
- Attach metrics sourced from Mixpanel (`query-events` / `query-funnel` /
  `retention`) or Metabase (`sql <db_id>`).
- Weekly `check`: pulls each metric's latest value, evaluates against
  `target`/`direction` (`above`/`below`), appends to a capped 26-entry
  history, and writes a heartbeat row (`--needs-reauth` set whenever any
  metric hit an auth-shaped failure).
- `report`: briefing-ready markdown grouped by feature, status icons per
  metric, for embedding in the weekly/evening update.
- `close-feature`: stop active tracking once the review window is done
  (history is kept, not deleted).

## Usage

```bash
# Register a shipped feature
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py add-feature \
  --title "OTO Logistics Aggregator" --shipped-on 2026-07-01 \
  --project "Work/Ecommerce" \
  --prd "https://docs.google.com/document/d/..." \
  --review-until 2026-08-01

# Attach a Mixpanel event-count metric (id defaults to slugify(title))
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py add-metric \
  --feature oto-logistics-aggregator --name "Weekly orders via OTO" \
  --target 500 --direction above \
  --source-kind mixpanel --mode query-events \
  --events "oto_order_created" --unit day --lookback-days 7

# Attach a Mixpanel funnel metric
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py add-metric \
  --feature oto-logistics-aggregator --name "Checkout funnel conversion" \
  --target 0.35 --direction above \
  --source-kind mixpanel --mode query-funnel --funnel-id 12345 --unit week

# Attach a Metabase SQL metric
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py add-metric \
  --feature oto-logistics-aggregator --name "OMS error rate" \
  --target 0.02 --direction below \
  --source-kind metabase --db-id 2 \
  --sql "SELECT error_rate FROM oto_daily_metrics ORDER BY day DESC LIMIT 1"

# Weekly cron pull (all active features), then briefing
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py check
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py report        # active only
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py report --all  # incl. closed

# Retire a feature once its review window is done
python3 .agent/skills/outcomes-loop/scripts/outcomes_loop.py close-feature --feature oto-logistics-aggregator
```

Cron (design only — NOT installed by this skill): weekly Monday
`20 8 * * 1 flock -n /tmp/outcomes_loop.lock python3 <abs>/outcomes_loop.py check >> <skill>/outcomes_loop_cron.log 2>&1`,
followed by `report` embedded in the Monday morning/weekly-report SOP.

## Notes

- Sources: Mixpanel via `.agent/skills/mixpanel-connector/scripts/mixpanel_client.py`
  (`query-events` / `query-funnel` / `retention`); Metabase via
  `.agent/skills/metabase-connector/scripts/metabase.js sql <db_id> "<query>"`
  (base `metabase.workincentives.me`, db_id 2 for the main app DB — confirm
  per-metric).
- `check` NEVER crashes the run over one bad metric. A Metabase non-zero exit,
  or any response text matching an auth-shaped pattern (`401`,
  "unauthenticated", "unauthorized", "session expired", "fetch failed",
  DNS/connection failures), secondarys that metric's `status` to `needs_reauth`,
  sets `needs_reauth: true` at the top of state, and the heartbeat row for
  `outcomes-loop` carries `--needs-reauth`. Mixpanel plan/quota errors (e.g.
  HTTP 402 "plan does not allow API calls") are treated as `no_data`, not
  `needs_reauth` — that's a billing/plan issue, not a stale session.
  Metabase's `METABASE_SESSION_TOKEN` (Google OAuth cookie) is the most common
  offender; re-auth is manual (browser DevTools → paste new cookie into
  `.agent/skills/metabase-connector/.env` or `token.env`) — this skill only
  surfaces the need, never re-auths itself.
- Value extraction from Mixpanel/Metabase responses is best-effort: known
  shapes (funnel `overall_conv_ratio`, Metabase first numeric column of the
  first row) are tried first, falling back to summing all numeric leaves in
  the response. If a metric's target comparison looks off, check
  `last_note` in state (or the `↳` line under it in `report`) for what the
  raw response actually looked like, and consider a source-specific SQL/query
  change (e.g. `LIMIT 1 ORDER BY day DESC` on Metabase) to get a single clean
  number.
- History is capped at 26 entries per metric (~6 months of weekly checks).
- `tickets.json`, the mention ledger, fathom registry, `dashboard/`,
  `.agent/workflows/`, and `.claude/` are READ-ONLY from this skill — no
  writes outside `.agent/skills/outcomes-loop/**` and
  `journal/state/outcomes.json`.
- No Slack/email/WhatsApp sends anywhere in this script — read-only pulls +
  a local heartbeat row only.
