# Antigravity Agent State & Capabilities Registry

This file acts as the centralized brain for checking integration and token availability BEFORE executing external operations. 

## 1. Active Integration Tokens

| Integration | Type | Scope / Role | Status | Verified On |
| :--- | :--- | :--- | :--- | :--- |
| **Slack (Work)** | Bot Token (`xoxb-`) | `channels:history`, `channels:read` | 🟢 ACTIVE | 2026-04-08 |
| **Slack (Work)** | User Token (`xoxp-`) | `search:read` (Global Search) | 🟢 ACTIVE | 2026-04-08 |
| **Google Calendar** | OAuth (Work Profile) | Read/Write Events | 🟢 ACTIVE | 2026-04-08 |
| **Google Drive** | OAuth (Work) | Read/Write/Comments | 🟢 ACTIVE | 2026-04-08 |
| **Fathom AI** | API Key | Transcripts & Summaries | 🟢 ACTIVE | 2026-04-08 |
| **GitHub** | Local/Remote | [product-second-brain](https://github.com/you/product-second-brain) | 🟢 CONNECTED | 2026-04-17 |
| **Atlassian** | API Token | Jira & Confluence (Work) | 🟢 ACTIVE | 2026-04-23 |

## 2. Skill Readiness Protocol

Before invoking any complex workflow (esp. reporting or syncing), check the dependencies here:

- **Weekly Report Generator**: Requires Calendar, Drive, and Slack **User** Token. Do not proceed if Slack User Token is missing.
- **Fathom Sync**: Requires Fathom API Key.
- **Master Product Updater**: Requires Google Sheets API Auth.

## 3. Maintenance Notes
*If a token returns `invalid_scope` or `not_allowed_token_type`, DO NOT fail silently. Escalate to the user to update this central registry.*
