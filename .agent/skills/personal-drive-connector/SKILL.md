---
name: Google Drive Connector
description: Personal Google Drive skill (you@example.com). Upload, update, delete, search, read, share, and list comments on Drive files. Uses token at google-drive-connector/token.json.
---

# Google Drive Connector (Personal Account)

For `you@example.com`. Use `work-drive-connector` for Work documents.

> **Update Protocol:** See `CLAUDE.md § Update Protocol`. Always `read` before `update`.
> **Permissions:** All uploads and updates automatically set sharing to "Anyone with the link can comment".

---

## Commands

```bash
BASE="timeout 180s python3 .agent/skills/google-drive-connector/gdrive_manager.py"

$BASE upload   --file path.md --convert [--share] [--folder FOLDER_ID] [--role viewer|commenter|writer]
$BASE update   --id FILE_ID --file path.md --convert
$BASE read     --id FILE_ID
$BASE search   --query "keyword"
$BASE share    --id FILE_ID --email addr@example.com --role commenter
$BASE delete   --id FILE_ID [--permanent]
$BASE comments --id FILE_ID
```

- `--convert`: converts markdown/text to Google Doc

## Token
Auto-refreshed from `token.json` in this directory. If expired and can't refresh, browser re-auth required.
