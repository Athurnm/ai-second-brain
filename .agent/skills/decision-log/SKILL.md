---
name: decision-log
description: Durable ledger of decisions You tracks across Work/Secondary (from Fathom meetings, Slack, GDocs, or captured manually) - "what did we decide about X" without re-digging through memory. No cron; capture is Claude-driven via /mom and morning/evening update SOPs.
---

## Capabilities

- Track a decision from "open question" through "decided" (with rationale + decider) to optionally "superseded" by a later decision.
- Attach one or more sources (Fathom recording, Slack permalink, GDoc, or manual note) and stakeholder names to each item.
- Emit a briefing-ready markdown report ordered: overdue-open first, then open by deadline (no-deadline last), then decided in the last 7 days.

## Usage

```bash
# capture a new open decision (surfaced e.g. during /mom or a meeting)
python3 .agent/skills/decision-log/scripts/decision_log.py add \
  --title "Q3 pricing floor for B2C bundles" \
  --decider "YourManager Barry" \
  --deadline 2026-07-20 \
  --project "B2C Super App" \
  --source "https://fathom.video/calls/12345" --source-type fathom --source-label "Fathom" \
  --stakeholders "YourManager Barry, Teammate"

# mark it decided
python3 .agent/skills/decision-log/scripts/decision_log.py decide DEC-0001 \
  --decision "Floor set at 12% margin, revisit at Q4"

# a later decision replaces an earlier one
python3 .agent/skills/decision-log/scripts/decision_log.py supersede DEC-0001 --by DEC-0007

# patch fields / add a source or stakeholder after the fact
python3 .agent/skills/decision-log/scripts/decision_log.py update DEC-0001 \
  --add-source "https://workincentives.slack.com/archives/..." --source-type slack \
  --add-stakeholders "Teammate Rasheed"

# list (for quick scanning; use report for briefings)
python3 .agent/skills/decision-log/scripts/decision_log.py list --status open

# briefing-ready markdown (embed verbatim in morning/evening update)
python3 .agent/skills/decision-log/scripts/decision_log.py report
python3 .agent/skills/decision-log/scripts/decision_log.py report --all   # include superseded
```

## Notes

- State file: `journal/state/decisions.json` — `{next_seq, items: {DEC-NNNN: {...}}, last_sweep}`.
- IDs are human-typeable and monotonic: `DEC-0001`, `DEC-0002`, ...
- `decider_slug` / `stakeholder_slugs` use `slugify(name)` (lowercase-dash) so this ledger can later
  cross-reference `journal/state/people.json` (owned by the `stakeholders` component) without a hard
  dependency — resolve by slug, fall back to the free-text name if the slug isn't in people.json yet.
- `sources[].type` is one of `fathom | slack | gdoc | manual`.
- No cron and no network calls in this script — it is a pure local ledger. Decisions get captured by
  Claude during `/mom` (meeting decisions -> `add`/`decide`), morning/evening update SOPs, or ad hoc
  whenever You and someone land on a decision.
- `report` ordering is fixed: (1) overdue open (deadline < today WIB), (2) open by deadline ascending
  (no-deadline items last), (3) decided in the last 7 days. Superseded items are hidden unless `--all`.
- This skill never writes to `tickets.json`, the mention ledger, or any other component's state —
  read-only relationship with the rest of the harness is by slug/id cross-reference only.
