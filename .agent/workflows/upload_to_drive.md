---
description: Upload a file to Google Drive
---
// turbo-all

This workflow uploads a specified file to Google Drive using the **Google Drive Connector Skill**.

1. **Prerequisites**
   - Ensure `credentials.json` is present in the project root.
   - See skill documentation: `.agent/skills/google-drive-connector/SKILL.md`

2. **Upload File**
   ```bash
   python ".agent/skills/google-drive-connector/gdrive_manager.py" upload --file "[file_path]" --convert --share
   ```

3. **Search Files**
   ```bash
   python ".agent/skills/google-drive-connector/gdrive_manager.py" search --query "[keyword]"
   ```

4. **Read File**
   ```bash
   python ".agent/skills/google-drive-connector/gdrive_manager.py" read --id "[FILE_ID]"
   ```
