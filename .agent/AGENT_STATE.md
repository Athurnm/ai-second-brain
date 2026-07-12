# Antigravity Agent State & Capabilities Registry

This file acts as the centralized brain for checking integration and token availability BEFORE executing external operations.

## 1. Active Integration Tokens

| Integration | Type | Scope / Role | Status | Verified On |
| :--- | :--- | :--- | :--- | :--- |
| **OpenRouter** | API Key (`sk-or-v1-`) | Claude Code gateway (Opus) | ✅ ACTIVE | 2026-07-12 |
| **GitHub** | Local/Remote | [ai-second-brain](https://github.com/Athurnm/ai-second-brain) | ✅ CONNECTED | 2026-07-12 |
| **Slack (Work)** | Bot Token (`xoxb-`) | `channels:history`, `channels:read` | ⏳ PENDING SETUP | - |
| **Slack (Work)** | User Token (`xoxp-`) | `search:read` (Global Search) | ⏳ PENDING SETUP | - |
| **Google Calendar** | OAuth (Work Profile) | Read/Write Events | ⏳ PENDING SETUP | - |
| **Google Drive** | OAuth (Work) | Read/Write/Comments | ⏳ PENDING SETUP | - |
| **Fathom AI** | API Key | Transcripts & Summaries | ⏳ PENDING SETUP | - |
| **Atlassian** | API Token | Jira & Confluence (Work) | ⏳ PENDING SETUP | - |

## 2. Hook Registry (Claude Code harness)

All hooks live in `.claude/hooks/`. Line endings fixed to LF on 2026-07-12.

| Hook | Trigger | Active in Antigravity? |
| :--- | :--- | :--- |
| `session_git_sync.sh` | SessionStart | Manual - run `git pull --rebase origin main` |
| `dashboard_context.py` | SessionStart | Yes - Antigravity reads Dashboard.md |
| `wib_clock.sh` | SessionStart | Yes - timestamp injected via metadata |
| `glm_mode.sh` | SessionStart | N/A - no GLM bridge on Antigravity |
| `emdash_guard.sh` | PostToolUse Write/Edit | Yes - enforced via no-emdash skill |
| `slack_send_guard.sh` | PreToolUse Slack send | Yes - Antigravity approval prompts |
| `drive_verify.sh` | PostToolUse Bash | Yes - gdocs-create skill verification |

## 3. Skill Readiness Protocol

Before invoking any complex workflow (esp. reporting or syncing), check the dependencies here:

- **Weekly Report Generator**: Requires Calendar, Drive, and Slack User Token. Do not proceed if Slack User Token is missing.
- **Fathom Sync**: Requires Fathom API Key in `.env` as `FATHOM_API_KEY`.
- **Master Product Updater**: Requires Google Sheets API Auth.
- **Slack Connector**: Requires `SLACK_BOT_TOKEN` and `SLACK_USER_TOKEN` in `.env`.

## 4. Maintenance Notes

*If a token returns `invalid_scope` or `not_allowed_token_type`, DO NOT fail silently. Escalate to the user to update this central registry.*

*Update the "Verified On" column whenever you confirm a token still works.*
