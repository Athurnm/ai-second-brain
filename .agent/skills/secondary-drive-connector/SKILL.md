---
name: Secondary Drive Connector
description: Upload, search, and read documents in the Google Drive of the secondary client (whatever company is currently in use besides Work/personal). Generic, company-agnostic. MCP-first; Python script is the fallback.
---

# Secondary Drive Connector

Generic Drive connector for the **secondary client** (the non-Work, non-personal company currently in use). Drop that company's `credentials.json` + `token.json` into this skill dir and it serves them via `--account secondary` / `--profile secondary`.

> **Primary method: MCP tools.** Python script (`gdrive_manager.py`) is legacy - only use if MCP is unavailable.

---

## Upload a File to Drive (as Google Doc)

```bash
# Step 1: encode
base64 -w 0 "path/to/YOUR_FILE.md"
```

```
# Step 2: upload via MCP
mcp__claude_ai_Google_Drive__create_file
  title: "Document Title"
  mimeType: "text/plain"
  content: <base64 string>
  parentId: "<secondary client My Drive root id>"
```

Returns: `viewUrl` (direct Google Docs link).

---

## Search Drive

```
mcp__claude_ai_Google_Drive__search_files
  query: title contains 'Keyword'
  pageSize: 10
  excludeContentSnippets: true
```

---

## Read a File

```
mcp__claude_ai_Google_Drive__read_file_content
  fileId: "<id>"
```

---

## Legacy Python Script (fallback only)

Only use if MCP fails or token is valid and formatting is critical.

```bash
timeout 180s python3 ".agent/skills/secondary-drive-connector/gdrive_manager.py" upload \
  --file "path/to/file.md" --convert --share
```

Token file: `.agent/skills/secondary-drive-connector/token.json`
Calendar token (for `gcal_manager.py --profile secondary`): `.agent/skills/secondary-drive-connector/token_calendar_secondary.json`
If expired: needs manual re-auth via OAuth flow.
