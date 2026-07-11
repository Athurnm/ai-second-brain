#!/usr/bin/env python3
"""
Update column B (L1: Component) cells to be HYPERLINK formulas pointing to Master Docs.
Column D (Documents/Links) is NOT touched at all.

All rows sharing the same L1 value get the same hyperlink on column B.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'work-drive-connector'))
from gdrive_manager import authenticate
from googleapiclient.discovery import build

SHEET_ID = '<YOUR_DRIVE_ID>'
SHEET_NAME = 'Master Product List & Breakdown (MECE)'

# ─── MAPPING: L1 component name → (Master Doc URL, display label) ─────────────
# URL = the Google Drive link to the uploaded Master Documentation
# Label = the exact text currently in column B (must not change visually)

COMPONENT_MASTER_DOC = {
    # ── Ecom Solutions ──────────────────────────────────────────────────────────
    'PIM': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'PIM'
    ),
    'E-commerce Core': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'E-commerce Core'
    ),
    'OMS': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'OMS'
    ),
    'E-commerce Front-end Builder': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'E-commerce Front-end Builder'
    ),
    'TMS': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'TMS'
    ),
    'Promo Engine': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Promo Engine'
    ),
    'Search Experience': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Search Experience'
    ),
    'Recommendation & Personalization': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Recommendation & Personalization'
    ),
    'Monetization': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Monetization'
    ),
    # ── Seller Portal ───────────────────────────────────────────────────────────
    'Product Upload & PIM Integration': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Product Upload & PIM Integration'
    ),
    'Real-Time Price & Stock Update': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Real-Time Price & Stock Update'
    ),
    'Order Fulfillment Workflow': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Order Fulfillment Workflow'
    ),
    'SFTP Integration': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'SFTP Integration'
    ),
    'Secure Account Management': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Secure Account Management'
    ),
    'Order List Enhancements': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Order List Enhancements'
    ),
    'Improvements (General)': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Improvements (General)'
    ),
    'MFN Elite Self-Shipping': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'MFN Elite Self-Shipping'
    ),
    'Seller Performance Dashboard': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Seller Performance Dashboard'
    ),
    'Self-Service Returns': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Self-Service Returns'
    ),
    'RBAC Multi-User': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'RBAC Multi-User'
    ),
    'Digital Products': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Digital Products'
    ),
    'Dispute Resolution': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Dispute Resolution'
    ),
    'External API Integration / Developer Portal': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'External API Integration / Developer Portal'
    ),
    # ── B2C Superapp ────────────────────────────────────────────────────────────
    'App Store Launch': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'App Store Launch'
    ),
    'B2C Wallet & Balance Hub': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'B2C Wallet & Balance Hub'
    ),
    'Digital Goods Store': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Digital Goods Store'
    ),
    'Checkout v1 & Payment Gateway': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Checkout v1 & Payment Gateway'
    ),
    'Work Verification': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Work Verification'
    ),
    'Physical Goods Marketplace': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Physical Goods Marketplace'
    ),
    'Gifti Global Migration': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Gifti Global Migration'
    ),
    'Mixed Payment Engine v.1': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Mixed Payment Engine v.1'
    ),
    'Mixed Payment v.2': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Mixed Payment v.2'
    ),
    'Order Management & Tracking': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Order Management & Tracking'
    ),
    'In-App Messaging': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'In-App Messaging'
    ),
    'Wishlist & Social': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Wishlist & Social'
    ),
    'Gamification & mTrust': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Gamification & mTrust'
    ),
    # ── Shared Components ────────────────────────────────────────────────────────
    # Note: Partner Portal has been removed from the spreadsheet - skip those.
    # Shared Component Master Doc IDs are from the previous session's uploads in Drive.
    'IAM (Identity Access Management)': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit',
        'IAM (Identity Access Management)'
    ),
    'Gamification': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit',
        'Gamification'
    ),
    'Blockchain': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit',
        'Blockchain'
    ),
    'Promotion Engine': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit',
        'Promotion Engine'
    ),
    'Mixed Payment': (
        'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
        'Mixed Payment'
    ),
}

def extract_url_from_formula(formula):
    """Extract URL from =HYPERLINK("url","label") formula."""
    import re
    m = re.search(r'=HYPERLINK\("([^"]+)"', formula)
    return m.group(1) if m else None

def main():
    dry_run = '--dry-run' in sys.argv

    creds = authenticate()
    sheets = build('sheets', 'v4', credentials=creds)

    # Load all rows (columns A through D so we can read existing column D for Shared Components)
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{SHEET_NAME}'!A1:D300",
        valueRenderOption='FORMULA'
    ).execute()
    rows = result.get('values', [])
    print(f"Loaded {len(rows)} rows.\n")

    # Build batch update for column B
    updates = []
    processed = set()

    for i, row in enumerate(rows[1:], start=2):
        l1 = row[1] if len(row) > 1 else ''
        if not l1 or l1 not in COMPONENT_MASTER_DOC:
            continue

        url, label = COMPONENT_MASTER_DOC[l1]
        if url is None:
            if l1 not in processed:
                print(f"  ⚠ No URL resolved for '{l1}' — skipping")
                processed.add(l1)
            continue

        formula = f'=HYPERLINK("{url}","{label}")'
        updates.append({
            'range': f"'{SHEET_NAME}'!B{i}",
            'values': [[formula]]
        })

        if l1 not in processed:
            processed.add(l1)

    print(f"\nPrepared {len(updates)} column B updates across {len(processed)} components.")

    if dry_run:
        print("\n[DRY RUN] — no changes made.")
        # Show sample
        for u in updates[:5]:
            print(f"  {u['range']}: {u['values'][0][0][:80]}...")
        return

    # Execute in batches of 50
    BATCH = 50
    for start in range(0, len(updates), BATCH):
        batch = updates[start:start + BATCH]
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={'valueInputOption': 'USER_ENTERED', 'data': batch}
        ).execute()
        print(f"  ✓ Updated rows {start+1}–{start+len(batch)}")

    print(f"\nDone. Column B updated for {len(processed)} components, {len(updates)} rows total.")
    print("Column D was not touched.")

if __name__ == '__main__':
    main()
