---
name: Weekly Report Generator
description: A skill to synthesize project updates into a comprehensive weekly progress report. Requires verifying AGENT_STATE.md and pulling API data from Google Drive, Google Calendar, Slack, and Fathom.
---

# Weekly Report Generator Skill

This skill outlines the process for creating detailed weekly reports. It MUST leverage real-time API integrations across the user's "Second Brain" to prevent hallucination or missing context.

## Prerequisites: Pre-Flight Check
Before generating any report, **you MUST view `.agent/AGENT_STATE.md`** to verify which integration tokens (Slack, Google Drive, Calendar, Fathom) are currently ACTIVE. Do not execute missing integrations.

## Workflow

### 1. Identify Reporting Scope
- **Client**: Determine which client (e.g., Work, Secondary) the report is for.
- **Period**: Define the start and end dates (usually the last 7 days).

### 2. Gather Information (Comprehensive API Sweep)
Execute these sweeps based on the active tokens in `AGENT_STATE.md`:

- **A. Task & Repo Base**:
    - Check `Dashboard.md` & `todo.md` for local task completion status.
    - Run local directory searches (e.g., `find . -mtime -7`) for recently modified files.

- **B. Google Drive (Drive Connector)**:
    - Search the client's Google Drive for any new PRDs, Roadmaps, or Meeting Notes using `gdrive_manager.py search`.

- **C. Google Calendar (Calendar Connector)**:
    - Run `python .agent/skills/google-calendar-connector/gcal_manager.py sweep --profile [client] --output markdown`
    - Analyze the *This Week* and *Last Week* sections to map exactly what meetings occurred.

- **D. Fathom Transcripts (Fathom Connector)**:
    - For key meetings found in Calendar, run `fathom_client.py --action list`, find the ID, and then `fathom_client.py --action transcript --id [ID]` to extract specific action items and blockers discussed.

- **E. Slack Communications (Slack Connector)**:
    - **Global Search**: If a User Token (`xoxp-`) is active in `token.env`, run `slack_client.py --action search --query "from:<SLACK_ID> after:[DATE]"` to capture all decisions made by the user.
    - **Fallback**: Read history of primary product channels.

### 3. Structure the Report
Create a new markdown file: `Clients/[Client]/reports/[Client]_Weekly_Report_[YYYY-MM-DD].md`.

Ensure you physically link (using absolute paths or exact google doc links) to any new documents discovered during the Drive Sweep.

#### Section 1: Executive Summary
- High-level narrative of the week.
- Mention major milestones achieved (e.g., Launch, PRD approval).

#### Section 2: Key Deliverables & Progress
- Must categorize by Component.
- Must include **Hard Links** to Docs/Sheets found during the Drive/Repo sweep.

#### Section 3: Recent Meeting Insights
- Must list the actual meetings extracted from Fathom/Calendar.

#### Section 4: Critical Blockers & Risks
- Validate blockers against the Slack & Fathom sweeps. (Who is blocking what).

#### Section 5: Priorities for Next Week
- List top 3-5 focus items derived from the Calendar and Standup notes.

### 4. Finalizing
- Cross-reference the report with `Dashboard.md` to ensure accuracy.
- Save the report.
- Update `Dashboard.md` to link to the new report.
- Notify the user.
