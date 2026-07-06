---
name: Master Product List Updater
description: A skill to systematically update the Master Product List (Google Sheet and Doc formats) after a new feature or PRD is created, using the Google Sheets API.
---

# Master Product List Updater

This skill automates the registration of new features and PRDs into the roadmap tracking ecosystem. It ensures that local Markdown, Google Docs, and Google Sheets are synchronized in a single step.

## Automated Workflow

When a PRD is finalized (State 4):
1. Use the `register_prd.py` script to update all destinations.
2. The script will:
    - Update `Master_Product_List_Restructured.md` (Local).
    - Update the corresponding Google Doc on Work Drive.
    - Insert/Update rows in the "Master Product List & Breakdown (MECE)" Google Sheet tab.

## Usage

```bash
python3 .agent/skills/master-product-list/register_prd.py \
  --component "E-commerce Core" \
  --feature "MGC Legacy Sync" \
  --details "Event-driven sync pipeline; product data, pricing, and stock write-back; delta sync" \
  --version "V1 Phase" \
  --status "Full" \
  --url "https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit" \
  --title "PRD Seller Portal MGC Legacy Sync"
```

## Sheet Integrity
The script uses `batchUpdate` to insert rows into the correct Component block in the Google Sheet (ID: `<YOUR_DRIVE_ID>`), preserving the hierarchical layout.

