# Gmail Connector Skill

Manage You's Gmail account (connected to `brian.faridhi@workincentives.com`) for reading, searching, and organizing emails.

## Overview
This skill allows the assistant to interact with the Gmail API. It supports fetching recent emails, searching using standard Gmail queries, reading full content, and archiving messages.

## Tools

### `profile`
Get the user's Gmail profile (email address and message counts).
- **Command**: `python .agent/skills/gmail-connector/gmail_manager.py profile`

### `list-emails`
List recent emails or search with a query.
- **Command**: `python .agent/skills/gmail-connector/gmail_manager.py list`
- **Arguments**:
  - `--query`: Gmail search string (e.g., `from:work`, `is:unread`, `subject:urgent`).
  - `--limit`: Number of results to return (default 10).

### `get-email`
Retrieve the full content of a specific email.
- **Command**: `python .agent/skills/gmail-connector/gmail_manager.py get <msg_id>`

### `archive-email`
Move an email from Inbox to Archive.
- **Command**: `python .agent/skills/gmail-connector/gmail_manager.py archive <msg_id>`

### `send`
Send a plain-text email from `brian.faridhi@workincentives.com` (appears in Sent). The `gmail.modify` scope already permits sending. Always confirm with You before sending.
- **Command**:
  ```bash
  python .agent/skills/gmail-connector/gmail_manager.py send \
    --to "faraz.saleem@workincentives.com" \
    --cc "Teammate.khoder@workincentives.com,amr.abokhalil@workincentives.com" \
    --subject "Subject" \
    --body-file /tmp/body.txt
  ```
- **Arguments**:
  - `--to`: recipient(s), comma-separated (required).
  - `--cc`: cc recipient(s), comma-separated (optional).
  - `--subject`: subject line (required).
  - `--body` OR `--body-file`: inline text, or a file with the body (use `--body-file` for multi-line to avoid shell escaping).

## Setup & Authentication
The skill uses the Work project's `credentials.json` (located in `.agent/skills/work-drive-connector/`) and saves `token_gmail_work.json` in the skill directory.

**Interactive (WSL/terminal with stdin):** Run any command; it triggers an OAuth flow. Copy the `code` from the browser address bar and paste it when prompted.

**Headless (two-step, for non-interactive shells):**
1. `python .agent/skills/gmail-connector/gmail_manager.py auth-url` → open the printed URL signed in as `brian.faridhi@workincentives.com`, approve, copy the `code=` value from the (failed-to-load) `localhost:8080` redirect URL.
2. `python .agent/skills/gmail-connector/gmail_manager.py auth-save --code "PASTE_CODE_HERE"` → saves the token.

If a send fails with "Gmail API has not been used in project ... or it is disabled," enable the Gmail API once in the Google Cloud project tied to the Work OAuth client, then retry.

## Best Practices
- **Privacy**: Only read emails that are relevant to the current task.
- **Filtering**: Use queries to minimize the amount of data processed.
- **Organization**: Archive emails once they have been converted into tasks or processed.
