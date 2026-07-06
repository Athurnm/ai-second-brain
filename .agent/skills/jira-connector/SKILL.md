---
name: Jira Connector
description: A custom skill to query sprint progress across ExampleVendor and Work Incentives Atlassian instances, identify developer bottlenecks, and auto-generate Markdown summaries for the daily update.
---

# Jira Connector Skill

This custom skill provides direct integration with Jira Software across multiple instances (ExampleVendor and Work Incentives Atlassian domains) under Your Name's management. It parses active sprints, tracks ticket distributions, and alerts on critical resource bottlenecks.

## Capabilities

1. **Dual-Instance Agile Routing**: Queries ExampleVendor and Work Incentives Jira boards dynamically.
2. **Workload Analysis & Alerts**: Flags if any single team member holds more than 40% of active sprint tickets.
3. **Status Standardization**: Maps custom project workflows to uniform statuses (`TO DO`, `IN PROGRESS`, `UNDER REVIEW`, `DONE`).
4. **Daily digest output**: Compiles clean Markdown digests suitable for inclusion in `daily_update_output.md`.

## Integration Setup

The credentials for Jira are stored in the active Atlassian credentials in the workspace (`credentials.json` or environment variables).

- **Instance A**: `examplevendor.atlassian.net` (MSP, MBA, STOR)
- **Instance B**: `work-incentives.atlassian.net` (MP, MPS)

## Usage

Run the connector from the workspace root:

```bash
python .agent/skills/jira-connector/scripts/jira_client.py daily-digest
```
