---
description: Organize files from inbox into the proper structure
---
// turbo-all

# Organize Inbox Workflow

This workflow processes files from the `inbox/` folder and organizes them into the appropriate locations in `processed/`.

## Steps

1. **Check inbox for new files**
   - List all files in `c:\Users\You\Product Repo\inbox\`
   - If empty, confirm no files to process

2. **For each file, analyze content**
   - Read the file content
   - **Identify the Client** (essential for multi-client support)
   - Identify the document type (PRD, roadmap, user research, meeting notes, etc.)
   - Determine the product or category it belongs to
   - Extract key metadata (date, product name, client, etc.)

3. **Ask clarifying questions if needed**
   - If client is unclear: "Which client is this for?"
   - If product name is unclear: "Which product is this for?"
   - If document type is ambiguous: "Is this a PRD or a feature spec?"
   - If date is missing: "When was this created?"

4. **Determine target location**
   - Client-specific files → `processed/clients/[client-name]/...`
     - PRDs/Requirements → `processed/clients/[client-name]/products/[product-name]/requirements/`
     - Roadmaps → `processed/clients/[client-name]/products/[product-name]/roadmap.md`
     - Meeting Notes → `processed/clients/[client-name]/stakeholders/meetings/`
     - Feedback → `processed/clients/[client-name]/stakeholders/feedback/`
   - Generic Frameworks → `processed/frameworks/`
   - Generic Templates → `processed/resources/templates/`
   - Daily Thoughts → `processed/journal/YYYY-MM-DD.md`

5. **Standardize filename**
   - Use lowercase with hyphens
   - Include date prefix if relevant: `YYYY-MM-DD-description.md`
   - Keep it descriptive but concise

6. **Create necessary folders**
   - If product folder doesn't exist, create it
   - Create any missing subfolders

7. **Move and confirm**
   - Move file from `inbox/` to target location
   - Report to user: "Organized [filename] → [new location]"
   - Provide brief summary of what was filed

8. **Update index (optional)**
   - If maintaining an index file, add entry with metadata

## Example

```
Inbox file: "new_mobile_feature_v2.pdf"
Analysis: PRD for mobile app's new social sharing feature
Target: processed/products/mobile-app/requirements/2026-01-08-social-sharing-prd.md
Action: Convert PDF to markdown, move to target location
Confirmation: "Organized PRD for mobile app social sharing feature → products/mobile-app/requirements/"
```

## Tips

- Group similar files together when processing multiple items
- Create product folders using kebab-case naming
- Convert non-markdown files to markdown when possible for better searchability
- Add frontmatter metadata to markdown files for easier filtering
