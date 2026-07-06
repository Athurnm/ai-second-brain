---
name: Google Docs Writer (Legacy)
description: Legacy skill — upload markdown as formatted Google Docs via MCP HTML conversion. Prefer gdocs-create for new docs and work/google-drive-connector for updates.
---

# Google Docs Writer Skill (Legacy)

> **Prefer `gdocs-create` for new docs and `work-drive-connector`/`google-drive-connector` for updates.**
> Use this only if those are unavailable or you need `.docx` output specifically.

> **Update Protocol:** See `CLAUDE.md § Update Protocol`.

---

## Fallback: python-docx Upload

```bash
python3 .agent/skills/gdocs-writer/scripts/gdocs_writer.py upload \
  --file "path/to/file.md" \
  --title "Document Title" \
  --cred-dir ".agent/skills/work-drive-connector" \
  --parent-id "<YOUR_DRIVE_ID>"
```

**Limitations:** DOCX output is ~40KB — hard to read/pass in the same session.
