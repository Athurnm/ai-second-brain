---
description: Manage action items and backlogs for clients and projects
---
// turbo-all

# Manage Action Items Skill

This skill helps you manage action items and backlogs across the client/project hierarchy.

## Directory Structure

```
c:\Users\You\Product Repo\
├── processed/
│   └── clients/
│       └── [client-name]/           # e.g., Work, Secondary
│           ├── backlog.md           # Client-level backlog (optional)
│           └── products/
│               └── [project-name]/  # e.g., b2c-superapp, seller-portal
│                   └── backlog.md   # Project-level backlog
```

## Backlog File Format

All backlog files should follow this format:

```markdown
---
title: [Client/Project] Backlog
created: YYYY-MM-DD
status: active
---

# [Client/Project] Backlog

## To-Dos

### [Category Name]
- [ ] **Task Title** - Task description
  - **Update**: Progress note (YYYY-MM-DD)
  - **Status**: Waiting for X / In Progress / Blocked
  - **Thread**: [Link](url)
- [x] **Completed Task** - Description
  - **Update**: Completed on YYYY-MM-DD

---

## Questions to Resolve

| # | Question | Owner | Status | Discussion |
|---|----------|-------|--------|------------|
| 1 | Question text | @person | Asked/Received/Resolved | [Thread](url) |

---

## Meeting Requests

- [ ] **Meeting Title** - Context and invitees
- [x] **Completed Meeting** - Outcome (YYYY-MM-DD)
```

## Workflows

### 1. List All Backlogs

To find all backlog files:

```
// turbo
find_by_name(Pattern: "*backlog*.md", SearchDirectory: "c:\Users\You\Product Repo\processed\clients")
```

### 2. View Client/Project Backlog

1. Identify the client and project from user request
2. Navigate to the backlog file:
   - **Project backlog**: `processed/clients/[client]/products/[project]/backlog.md`
   - **Client backlog**: `processed/clients/[client]/backlog.md`
3. Read and summarize the backlog

### 3. Add New Action Item

1. Identify target backlog (ask user if unclear):
   - "Which client is this for?"
   - "Which project is this for?"
2. Open the backlog file
3. Find the appropriate category section (or create one)
4. Add the new item in this format:
   ```markdown
   - [ ] **Task Title** - Task description
   ```
5. If there are updates or context, add sub-bullets:
   ```markdown
   - [ ] **Task Title** - Task description
     - **Update**: Note (YYYY-MM-DD)
     - **Owner**: @person
   ```

### 4. Update Existing Item

1. Locate the backlog file
2. Find the item by searching for the task title
3. Update the item:
   - **Mark complete**: Change `- [ ]` to `- [x]`
   - **Add update**: Add sub-bullet with `**Update**: text (YYYY-MM-DD)`
   - **Change status**: Update or add `**Status**: new status`

### 5. Add Items from Meeting Notes

When user provides meeting notes (text or image):

1. Extract action items from the notes
2. Ask for clarification if client/project is unclear
3. Create or update the appropriate backlog file
4. Add all items under a new section header with the meeting date:
   ```markdown
   ### From Meeting (YYYY-MM-DD)
   - [ ] **Item 1** - Description
   - [ ] **Item 2** - Description
   ```

### 6. Create New Backlog

If no backlog exists for a client/project:

1. Create the file at the appropriate path
2. Use the standard frontmatter and structure
3. Add initial items if provided

## Task Markers

- `[ ]` - Not started
- `[/]` - In progress
- `[x]` - Completed
- `[-]` - Cancelled/Dropped

## Tips

- Always include dates in updates for traceability
- Use `**Owner**: @name` to track responsibility
- Link to Slack threads or documents when relevant
- Group related items under category headers
- When items are completed, keep them for a record but move them to a "Completed" section if the file gets long
