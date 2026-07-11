#!/usr/bin/env python3
"""
work-link-sync — Auto-link new Work Drive files to Master Docs & Spreadsheet

Usage:
  python3 link_sync.py --url <google_doc_url> --name <display_name> --component <component_name> [--type prd|master|reference]

Examples:
  python3 link_sync.py \
    --url "https://docs.google.com/document/d/ABC123/edit" \
    --name "PRD: IAM Phase 2 RBAC" \
    --component "IAM (Identity Access Management)" \
    --type prd

What it does:
  1. Finds matching rows in Master Product List spreadsheet → updates Documents/Links (col D)
  2. Finds the Master Doc for the component → adds the new file to Related Documents section
"""

import argparse
import sys
import os
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'work-drive-connector'))
from gdrive_manager import authenticate
from googleapiclient.discovery import build

SHEET_ID = '<YOUR_DRIVE_ID>'
SHEET_NAME = 'Master Product List & Breakdown (MECE)'

# Master Doc IDs per component (update as new Master Docs are created)
MASTER_DOCS = {
    'IAM (Identity Access Management)': '<YOUR_DRIVE_ID>',
    'Gamification': '<YOUR_DRIVE_ID>',
    'Promotion Engine': '<YOUR_DRIVE_ID>',
    'Blockchain': '<YOUR_DRIVE_ID>',
    'Mixed Payment': None,  # Add Master Doc ID when created
}

# Aliases for flexible component matching
COMPONENT_ALIASES = {
    'iam': 'IAM (Identity Access Management)',
    'identity': 'IAM (Identity Access Management)',
    'gamification': 'Gamification',
    'gamif': 'Gamification',
    'promotion': 'Promotion Engine',
    'promo': 'Promotion Engine',
    'voucher': 'Promotion Engine',
    'blockchain': 'Blockchain',
    'crypto': 'Blockchain',
    'mixed payment': 'Mixed Payment',
    'payment': 'Mixed Payment',
}

# Global timeout: 180 seconds
def timeout_handler(signum, frame):
    print("[ERROR] Work Link Sync timed out after 180 seconds", file=sys.stderr)
    sys.exit(1)

if os.name != 'nt': # signal.alarm is Unix-only
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)

def resolve_component(component_input):
    lower = component_input.lower().strip()
    if lower in COMPONENT_ALIASES:
        return COMPONENT_ALIASES[lower]
    # Try direct match (case-insensitive)
    for canonical in MASTER_DOCS:
        if canonical.lower() == lower:
            return canonical
    return component_input  # Return as-is if no match

def update_spreadsheet(sheets, component, url, name):
    """Update Documents/Links column for all rows matching the component."""
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{SHEET_NAME}'!A1:H300"
    ).execute()

    rows = result.get('values', [])
    updates = []
    formula = f'=HYPERLINK("{url}","{name}")'

    for i, row in enumerate(rows, start=1):
        if not row:
            continue
        l0 = row[0] if len(row) > 0 else ''
        l1 = row[1] if len(row) > 1 else ''
        if l0 == 'Shared Components' and l1 == component:
            updates.append({
                'range': f"'{SHEET_NAME}'!D{i}",
                'values': [[formula]]
            })

    if updates:
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={'valueInputOption': 'USER_ENTERED', 'data': updates}
        ).execute()
        print(f"  ✓ Spreadsheet: Updated {len(updates)} rows for '{component}'")
    else:
        print(f"  ⚠ Spreadsheet: No rows found for component '{component}'")
    return len(updates)

def update_master_doc(service, component, url, name, doc_type):
    """Append new link to Related Documents section of the Master Doc."""
    master_doc_id = MASTER_DOCS.get(component)
    if not master_doc_id:
        print(f"  ⚠ Master Doc: No Master Doc registered for '{component}'")
        return False

    docs = build('docs', 'v1', credentials=service._http.credentials)

    # Read current doc content to find Related Documents section
    doc = docs.documents().get(documentId=master_doc_id).execute()
    content = doc.get('body', {}).get('content', [])

    # Find the end index of the document to append
    end_index = doc['body']['content'][-1]['endIndex'] - 1

    # Build the text to append
    new_line = f"\n| {name} | {doc_type.upper()} — {url} |"

    docs.documents().batchUpdate(
        documentId=master_doc_id,
        body={
            'requests': [{
                'insertText': {
                    'location': {'index': end_index},
                    'text': new_line
                }
            }]
        }
    ).execute()

    print(f"  ✓ Master Doc: Added '{name}' to Related Documents")
    return True

def main():
    parser = argparse.ArgumentParser(description='Work Link Sync — auto-link new files to Master Docs & Spreadsheet')
    parser.add_argument('--url', required=True, help='Google Doc URL of the new file')
    parser.add_argument('--name', required=True, help='Display name for the link')
    parser.add_argument('--component', required=True, help='Shared component name (e.g., "IAM", "Blockchain")')
    parser.add_argument('--type', default='reference', choices=['prd', 'master', 'reference'],
                        help='Type of document: prd, master, or reference')
    parser.add_argument('--spreadsheet-only', action='store_true',
                        help='Only update spreadsheet, skip Master Doc update')

    args = parser.parse_args()

    component = resolve_component(args.component)
    print(f"\nWork Link Sync")
    print(f"  File    : {args.name}")
    print(f"  URL     : {args.url}")
    print(f"  Component: {component}")
    print(f"  Type    : {args.type}")
    print()

    creds = authenticate()
    sheets = build('sheets', 'v4', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)

    # Update spreadsheet
    updated = update_spreadsheet(sheets, component, args.url, args.name)

    # Update Master Doc (skip if --spreadsheet-only or if this IS a master doc)
    if not args.spreadsheet_only and args.type != 'master':
        try:
            update_master_doc(drive, component, args.url, args.name, args.type)
        except Exception as e:
            print(f"  ⚠ Master Doc update failed (Docs API may not be enabled): {e}")
            print(f"  → Manually add to Master Doc: {MASTER_DOCS.get(component, 'Not registered')}")

    print(f"\nDone. {updated} spreadsheet rows updated.")

if __name__ == '__main__':
    main()
