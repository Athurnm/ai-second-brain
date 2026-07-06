---
name: No Title Change Enforcement
description: Enforces that updating existing Google Docs or Sheets must NOT change their titles. This preserves document IDs and internal links.
---

# No Title Change Enforcement

This skill ensures that when Antigravity updates an existing file on Google Drive (Work or Personal), the original title of the document is preserved, regardless of the local file name.

## The Rule
**NEVER change the title of an existing document during an update operation.**

### Why?
1. **Document ID Stability:** While IDs usually don't change, changing titles can break human-centric search and discovery.
2. **Internal Linking:** Many documents refer to each other by title.
3. **Source of Truth:** Drive titles are often carefully curated and should not be reverted to potentially messy local filenames (e.g., `PRD_V2_final_v3.md`).

## Implementation Pattern

When using the Google Drive API `update` method, ensure the `body` (metadata) does **NOT** contain the `name` field unless you explicitly intend to rename the file (which is a separate `rename` operation).

### Correct Pattern (Python)
```python
# GOOD: Only update content, not metadata
service.files().update(
    fileId=file_id,
    body={}, # Keep body empty to preserve existing name
    media_body=media,
    fields='id'
).execute()
```

### Incorrect Pattern (Python)
```python
# BAD: Overwrites title with local filename
file_metadata = {'name': 'local_filename.md'}
service.files().update(
    fileId=file_id,
    body=file_metadata, # THIS WILL CHANGE THE TITLE
    media_body=media,
    fields='id'
).execute()
```

## How to Verify
1. Identify the current title of the document on Google Drive.
2. Run the update command.
3. Verify on the web interface or via `read` that the title remains exactly the same.

## Scripts Protected by this Protocol
- `.agent/skills/work-drive-connector/gdrive_manager.py`
- `.agent/skills/google-drive-connector/gdrive_manager.py`
- `.agent/skills/gdocs-create/gdocs_create.py` (ensure update mode preserves title)
