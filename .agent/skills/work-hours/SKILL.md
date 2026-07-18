---
name: work-hours
description: Reconstruct the owner's working hours per day from digital traces (Claude Code transcripts, meetings, git) — parallel streams, actual vs effective hours, leverage multiplier. Feeds the ⏱ Hours tab on the visual dashboard.
---

# work-hours

Answers: kapan gw mulai kerja, ngerjain apa aja paralel barengan, total jam berapa,
dan berapa leverage-nya (output paralel ÷ jam aktual).

## Capabilities

- Harvests every Claude Code session transcript under `~/.claude/projects/` and
  classifies it: `entrypoint: claude-vscode|cli` = interactive workstream (counts),
  `entrypoint: sdk-cli` = automation (inbox digests etc — excluded, counted
  separately as `automated_runs`). Subagent transcripts under `<session-uuid>/`
  inherit the parent session.
- Meetings from `journal/fathom_registry.json` (recorded = attendance verified)
  merged with Google Calendar (`gcal_manager.py --profile work`, cached per day in
  state). Declined and solo events (focus blocks) are skipped; scheduled meetings
  that have not happened yet are clipped at "now".
- Git commits (product-second-brain, You, owner-arfi-website) as timeline markers.
- Per day (04:00 WIB boundary — late-night work counts to the day it started;
  calendar events are bucketed by workday too, so a 02:00 WIB call lands on the
  right day):
  - `actual_h` — union of all activity (jam kerja beneran)
  - `effective_h` — sum of per-stream hours (parallel counted N times)
  - `leverage` — effective ÷ actual (measured parallelism)
  - `attention_h` — human-typed prompt clusters + meetings, bounded by actual
    (hands-on floor, always ≤ actual_h)
  - `human_equiv_h` / `output_x` — meetings 1:1 + AI hours × AI-speed factor
    (default **2.5**, research-calibrated: see `research_ai_speed_factor.md` —
    blended ×2-2.5 conservative-defensible for the owner's mix, ×3 optimistic edge,
    coding closer to ×1-2. Override: `--ai-speed N` or env `WORK_HOURS_AI_SPEED`.
    Still an estimate; the UI labels it "assumed". Revisit ~quarterly, capability
    moves fast.)
- Overlapping meeting entries merge into one stream (the owner is one person —
  double-booked slots and one recording spanning two events never count twice);
  strictly back-to-back meetings stay separate.
- Lanes: Meetings / Work PM / You / Other AI. Stream labels from the session's
  `aiTitle` (fallback: slash command or first prompt).

## Usage

```bash
python3 .agent/skills/work-hours/scripts/work_hours.py sweep --backfill 2   # cron form
python3 .agent/skills/work-hours/scripts/work_hours.py sweep --backfill 14  # rebuild 2 weeks
python3 .agent/skills/work-hours/scripts/work_hours.py sweep --date 2026-07-10
python3 .agent/skills/work-hours/scripts/work_hours.py show  --date 2026-07-16
```

## State

- `journal/state/work_hours.json` — per-day stats + streams (served at `/api/work-hours`,
  rendered on the ⏱ Hours dashboard tab). Also holds the per-day gcal event cache.
- `journal/state/work_hours_cache.json` — per-file incremental parse cache (byte
  offset + event minutes); prunes entries with file mtime older than 21 days.

## Refresh

**Self-refreshing via the dashboard**: `GET /api/work-hours` spawns a detached
`sweep --backfill 2` whenever the state file is older than 15 min (flock +
debounce, single-flight). With the Hours tab open, the 60s frontend poll keeps
the data current — no cron required.

Optional cron (background freshness with the dashboard closed; needs the owner to
install it, a session permission gate blocks agents from editing crontab):

```
*/20 * * * * flock -n /tmp/work_hours.lock /bin/bash -c 'cd . && python3 .agent/skills/work-hours/scripts/work_hours.py sweep --backfill 2 --quiet && python3 .agent/scripts/heartbeat.py --job work-hours --status ok' >> ./.agent/skills/work-hours/work_hours_cron.log 2>&1
```

Registered in dashboard `JOB_LOG_MAP` + `JOB_RUN_MAP` (System tab: log tail + ▶ Run now).

## Notes / limitations

- First sweep over a window does a full parse (~2s for 14 days thanks to byte-level
  prefilters); after that it re-reads only appended bytes per file.
- Calendar-only meetings count as `scheduled` (attendance not verified) — the
  timeline fades them and the tooltip discloses it. Recording overlap upgrades them
  to `recorded` and can extend the end time.
- Sessions left open with background wakeups still count as activity; the gap rule
  (>15 min splits) keeps idle windows out.
- `actual_h` counts any-stream activity (AI working unattended included). The
  strictly hands-on floor is `attention_h`; the honest "the owner worked X hours" story
  is: attention ≤ actual ≤ effective.
