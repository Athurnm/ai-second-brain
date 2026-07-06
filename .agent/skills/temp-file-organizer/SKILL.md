---
name: Temp File Organizer
description: Automatically detects and organizes stray temp/debug/output files in the Product Repo root. Runs as part of daily update to keep the repo clean.
---

# Temp File Organizer

## Purpose

During daily work, scripts and tools generate temp files (`.txt`, `.log`, `.json`, `.html`, `.csv`, `.bat`) in the Product Repo root. This skill detects those stray files and moves them into the `_temp/` directory, categorized by type.

## When to Run

- **During `/daily-update`** — Add this as a final step after the change scan.
- **On demand** — When the user asks to clean up or organize the repo.

## How It Works

### Step 1: Scan Root for Stray Files

Scan `c:\Users\You\Product Repo\` (root only, not subdirectories) for files that **should not be there**. 

**Files that STAY at root** (whitelist):
- `Dashboard.md`
- `README.md`
- `GEMINI.md`
- `credentials.json`
- `token.json`
- `token_calendar.json`
- `.gitignore`
- `.figma_token`

**Directories that STAY at root**:
- `.agent/`, `.git/`, `.venv/`
- `Clients/`, `inbox/`, `journal/`, `resources/`, `scripts/`, `_temp/`

Everything else at root is a stray file.

### Step 2: Categorize Stray Files

Determine the category based on filename patterns:

| Category | Pattern/Extension | Destination |
|---|---|---|
| `slack_dumps` | `slack_*`, `history_*`, `channel_*`, `*_history*` | `_temp/slack_dumps/` |
| `drive_dumps` | `drive_*`, `gdoc_*`, `marketplace_*`, `*_content*` | `_temp/drive_dumps/` |
| `clickup_dumps` | `*clickup*`, `spaces.json`, `*_lists.json`, `*_folders.json` | `_temp/clickup_dumps/` |
| `debug_output` | `debug_*`, `test_*`, `simple_*`, `faq_*` | `_temp/debug_output/` |
| `search_output` | `search_*`, `*_search*` | `_temp/search_output/` |
| `git_output` | `git_*`, `staged_*`, `modified*`, `created_*`, `recent_*` | `_temp/git_output/` |
| `log_files` | `*.log`, `*_log*`, `error_*`, `upload_*` | `_temp/log_files/` |
| `json_dumps` | Non-config `.json` files | `_temp/json_dumps/` |
| `qa_reports` | `daily_qa_*`, `qa_results_*` | `_temp/qa_reports/` |
| `batch_files` | `*.bat` | `_temp/batch_files/` |
| `scripts` | `*.py` (not in whitelist) | `scripts/utils/` |
| `misc_output` | Everything else | `_temp/misc_output/` |

### Step 3: Move Files

For each stray file:
1. Determine category from table above
2. Create the destination folder if it doesn't exist
3. Move the file (rename if conflicts)
4. Log the move

### Step 4: Report

After organizing, report to the user:
```
🧹 Repo Cleanup: Moved X stray files
- Y temp/debug files → _temp/
- Z scripts → scripts/
Root is clean ✅
```

Add this summary to the Daily Change Summary in `Dashboard.md` if running as part of `/daily-update`.

## What NOT to Move

- **Any `.md` files** — These may be intentional docs. Flag them to the user instead of moving.
- **Any file the user just created today** — If a file was created within the last hour, skip it and mention it in the report.
- **Config files** — `credentials.json`, `token.json`, `token_calendar.json` stay at root.

## _temp/ Directory Structure

```
_temp/
├── batch_files/       # .bat scripts
├── clickup_dumps/     # ClickUp API output
├── debug_output/      # Debug/test artifacts
├── drive_dumps/       # Google Drive content exports
├── git_output/        # Git status/diff captures
├── json_dumps/        # API response dumps
├── log_files/         # Script logs
├── misc_output/       # Uncategorized
├── qa_reports/        # QA test reports
├── search_output/     # Search result captures
├── slack_dumps/       # Slack channel exports
└── user_dumps/        # User list exports
```
