---
description: Daily scan and update of all changes (created, modified, deleted) with high-level overview to Dashboard, plus Slack message summary
---
// turbo-all

# Daily Update Workflow

This workflow auto-detects the appropriate mode based on current time:
- **Before 14:00 WIB**: Runs Morning Prep mode (equivalent to `/morning-update`)
- **After 14:00 WIB**: Runs Evening Closing mode (equivalent to `/evening-update`)

## Auto-Detect Mode

Check the current local time. If before 14:00, run morning mode. If after 14:00, run evening mode.

### Morning Mode (before 14:00)

```bash
// turbo
python .agent/scripts/daily_update_runner.py --mode morning
```

Follow the Morning Update Workflow steps for priority setting and summary generation.

### Evening Mode (after 14:00)

```bash
// turbo
python .agent/scripts/daily_update_runner.py --mode evening
```

Follow the Evening Update Workflow steps for closing recap, completion tracking.

## Dashboard Refresh & Summary Generation

1. **For synthesis, prefer the JSON sidecar over the markdown file**: read `_temp/harvest_[mode]_[date].json` (compact structured data) instead of the full `daily_update_morning.md` / `daily_update_evening.md`. Fall back to the markdown only if the JSON is missing. The markdown files are kept as user-facing deliverables.
2. Update `Dashboard.md` with the appropriate section (Pagi or Malam).
3. For evening mode: sync Jira sprint data, archive old entries, run GitHub sync.
4. Notify You with a summary highlighting the most important actionable items.
