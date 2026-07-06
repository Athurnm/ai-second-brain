---
name: Work Drive Connector
description: Work Google Drive skill (brian.faridhi@workincentives.com). Upload, update, rename, delete, search, read, and list comments on Work Drive files. Uses token at work-drive-connector/token.json.
---

# Work Drive Connector

For `brian.faridhi@workincentives.com` only. For personal docs use `google-drive-connector`.

> **Update Protocol:** See `CLAUDE.md § Update Protocol`. Always `read` before `update`.
> **Permissions:** All uploads and updates automatically set sharing to "Anyone with the link can comment".

---

## Commands

```bash
BASE="timeout 180s python3 .agent/skills/work-drive-connector/gdrive_manager.py"

$BASE upload   --file path.md --convert [--folder FOLDER_ID]
$BASE update   --id FILE_ID --file path.md --convert
$BASE read     --id FILE_ID
$BASE search   --query "keyword"
$BASE rename   --id FILE_ID --name "New Name"
$BASE delete   --id FILE_ID [--permanent]
$BASE comments --id FILE_ID
```

## Token
Auto-refreshed from `token.json` in this directory.
