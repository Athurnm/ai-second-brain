#!/usr/bin/env python3
"""
Update Work Master Product List & Breakdown (MECE) sheet.
Changes:
1. Add L0: Product column (leftmost)
2. For B2C Super App rows: L0="B2C Superapp", promote old L2 → new L1, old L3 → new L2
3. For Seller Portal rows: L0="Seller Portal", same L1/L2 promotion
4. For Ecom rows: L0="Ecom Solutions", keep L1/L2/L3 as-is
5. Mixed Payment: L0="Shared Components"
6. Delete Monetization rows that are B2C duplicates (keep only Dynamic Slot Monetization)
7. Add Partner Portal rows (To Do)
8. Update Status column based on Q1-Q2 2026 presentation data
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from gdrive_manager import authenticate
from googleapiclient.discovery import build

SHEET_ID = '<YOUR_DRIVE_ID>'
SHEET_NAME = 'Master Product List & Breakdown (MECE)'

# Old column indices (0-based)
IDX_L1    = 0  # L1: Component
IDX_L2    = 1  # L2: Feature
IDX_DOCS  = 2  # Documents / Links
IDX_PRD   = 3  # PRD Status
IDX_STAT  = 4  # Status
IDX_L3    = 5  # L3: Detailed Item
IDX_PHASE = 6  # Phase

# New header after restructure
NEW_HEADER = ['L0: Product', 'L1: Component', 'L2: Feature',
              'Documents / Links', 'PRD Status', 'Status',
              'L3: Detailed Item', 'Phase']

# L1 values that belong to Ecom Solutions (structure: L0→L1→L2→L3)
ECOM_L1 = {
    'PIM', 'E-commerce Core', 'OMS', 'E-commerce Front-end Builder',
    'TMS', 'Promo Engine', 'Search Experience', 'Recommendation & Personalization',
    'Monetization',  # only Dynamic Slot rows survive the filter below
}

# Monetization: only keep this L2 value; delete all others (B2C duplicates)
MONETIZATION_KEEP = {'Dynamic Slot Monetization'}

# Status map keyed by (l0, l2) where l2 is the FEATURE GROUP
# For B2C/SP rows: l2 = old L2 (which becomes new L1 after promotion)
# For Ecom rows:   l2 = old L2 (stays as L2)
STATUS_MAP = {
    # ── B2C Superapp ────────────────────────────────────────────────────
    ('B2C Superapp', 'App Store Launch'):               'In Progress',
    ('B2C Superapp', 'B2C Wallet & Balance Hub'):       'In Progress',
    ('B2C Superapp', 'Digital Goods Store'):            'In Progress',
    ('B2C Superapp', 'Checkout v1 & Payment Gateway'):  'In Progress',
    ('B2C Superapp', 'Work Verification'):             'In Progress',
    ('B2C Superapp', 'Physical Goods Marketplace'):     'In Progress',
    ('B2C Superapp', 'Gifti Global Migration'):         'To Do',
    ('B2C Superapp', 'Mixed Payment Engine v.1'):       'In Progress',
    ('B2C Superapp', 'Order Management & Tracking'):    'In Progress',
    ('B2C Superapp', 'In-App Messaging'):               'To Do',
    ('B2C Superapp', 'Wishlist & Social'):              'To Do',
    ('B2C Superapp', 'Gamification & mTrust'):          'To Do',
    ('B2C Superapp', 'Mixed Payment v.2'):              'To Do',
    # ── Seller Portal ───────────────────────────────────────────────────
    ('Seller Portal', 'Product Upload & PIM Integration'):             'Released',
    ('Seller Portal', 'Real-Time Price & Stock Update'):               'In Progress',
    ('Seller Portal', 'Order Fulfillment Workflow'):                    'Released',
    ('Seller Portal', 'SFTP Integration'):                             'To Do',
    ('Seller Portal', 'Secure Account Management'):                    'To Do',
    ('Seller Portal', 'Order List Enhancements'):                      'To Do',
    ('Seller Portal', 'Improvements (General)'):                       'In Progress',
    ('Seller Portal', 'MFN Elite Self-Shipping'):                      'To Do',
    ('Seller Portal', 'Seller Performance Dashboard'):                 'To Do',
    ('Seller Portal', 'Self-Service Returns'):                         'To Do',
    ('Seller Portal', 'RBAC Multi-User'):                              'To Do',
    ('Seller Portal', 'Digital Products'):                             'To Do',
    ('Seller Portal', 'Dispute Resolution'):                           'To Do',
    ('Seller Portal', 'External API Integration / Developer Portal'):  'To Do',
    # ── PIM (Ecom Solutions) ────────────────────────────────────────────
    ('Ecom Solutions', 'PIM Core (MedusaJS)'):              'Released',
    ('Ecom Solutions', 'Category & Attribute Structure'):   'Released',
    ('Ecom Solutions', 'Catalog Distribution Service'):     'To Do',
    # ── E-commerce Core ─────────────────────────────────────────────────
    ('Ecom Solutions', 'Seller Offer Management'):          'To Do',
    ('Ecom Solutions', 'Inventory Management Service'):     'In Progress',
    ('Ecom Solutions', 'MGC Legacy Sync'):                  'In Progress',
    ('Ecom Solutions', 'Sales Channel Management'):         'To Do',
    ('Ecom Solutions', 'Collection Management'):            'To Do',
    ('Ecom Solutions', 'Review Management'):                'To Do',
    # ── OMS ─────────────────────────────────────────────────────────────
    ('Ecom Solutions', 'OMS Core / Order State Machine'):   'In Progress',
    ('Ecom Solutions', 'Payment & Settlement Integration'): 'To Do',
    # ── E-commerce Front-end Builder ────────────────────────────────────
    ('Ecom Solutions', 'Storefront Builder (Admin Panel)'):    'To Do',
    ('Ecom Solutions', 'Storefront Template (Consumer-facing)'): 'To Do',
    # ── TMS ─────────────────────────────────────────────────────────────
    ('Ecom Solutions', 'TMS Core Infrastructure'):  'To Do',
    ('Ecom Solutions', 'Carrier Integrations'):     'To Do',
    ('Ecom Solutions', 'Real-Time Tracking'):       'To Do',
    # ── Promo Engine ────────────────────────────────────────────────────
    ('Ecom Solutions', 'Promotions V1'):            'To Do',
    ('Ecom Solutions', 'Stacking & A/B Testing'):   'To Do',
    # ── Search Experience ───────────────────────────────────────────────
    ('Ecom Solutions', 'Advanced Search Engine'):   'In Progress',
    # ── Recommendation ──────────────────────────────────────────────────
    ('Ecom Solutions', 'AI Recommendation Engine'): 'To Do',
    # ── Monetization / Slot ─────────────────────────────────────────────
    ('Ecom Solutions', 'Dynamic Slot Monetization'): 'To Do',
    # ── Shared Components / Mixed Payment ────────────────────────────────
    ('Shared Components', 'Checkout & Payment Gateway'):       'In Progress',
    ('Shared Components', 'Mixed Payment Engine'):             'In Progress',
    ('Shared Components', 'Pay with Cards & Digital Wallets'): 'In Progress',
}

def cell(row, idx, default=''):
    """Safe cell getter."""
    if idx < len(row):
        v = row[idx]
        return v if v is not None else default
    return default

def process(rows):
    new_rows = [NEW_HEADER]

    for row in rows[1:]:   # skip old header
        l1    = cell(row, IDX_L1)
        l2    = cell(row, IDX_L2)
        docs  = cell(row, IDX_DOCS)
        prd   = cell(row, IDX_PRD)
        stat  = cell(row, IDX_STAT)
        l3    = cell(row, IDX_L3)
        phase = cell(row, IDX_PHASE)

        # ── Filter: drop Monetization rows that are B2C duplicates ──────
        if l1 == 'Monetization' and l2 not in MONETIZATION_KEEP:
            continue

        # ── Classify row ─────────────────────────────────────────────────
        if l1 in ECOM_L1:
            # Structure stays: L0 → L1 (component) → L2 (feature) → L3
            l0     = 'Ecom Solutions'
            new_l1 = l1
            new_l2 = l2
            new_l3 = l3

        elif l1 == 'Mixed Payment':
            l0     = 'Shared Components'
            new_l1 = l1
            new_l2 = l2
            new_l3 = l3

        elif l1 == 'Seller Portal':
            # Promote: old L2 → new L1, old L3 → new L2
            l0     = 'Seller Portal'
            new_l1 = l2
            new_l2 = l3
            new_l3 = ''

        elif l1 == 'B2C Super App':
            # Promote: old L2 → new L1, old L3 → new L2
            l0     = 'B2C Superapp'
            new_l1 = l2
            new_l2 = l3
            new_l3 = ''

        else:
            # Unknown – preserve as-is with empty L0
            l0     = ''
            new_l1 = l1
            new_l2 = l2
            new_l3 = l3

        # ── Update Status ─────────────────────────────────────────────────
        # Use l2 (feature group) as key – consistent for all row types
        status_key = (l0, l2)
        if status_key in STATUS_MAP:
            new_stat = STATUS_MAP[status_key]
        elif stat:
            new_stat = stat   # keep existing non-empty status
        else:
            new_stat = 'To Do'

        new_rows.append([l0, new_l1, new_l2, docs, prd, new_stat, new_l3, phase])

    # ── Append Partner Portal rows ────────────────────────────────────────
    partner_components = [
        'Games Aggregator & Providers B2B/B2C',
        'Content Music/Video/Education',
        'Vendor Registration',
        'Vendor Migration',
    ]
    for comp in partner_components:
        new_rows.append(['Partner Portal', comp, '', '', 'Missing', 'To Do', '', 'Future'])

    return new_rows

def main():
    creds   = authenticate()
    service = build('sheets', 'v4', credentials=creds)
    sheets  = service.spreadsheets()

    # Read current data
    result = sheets.values().get(
        spreadsheetId=SHEET_ID,
        range=SHEET_NAME
    ).execute()
    rows = result.get('values', [])
    print(f"Read {len(rows)} rows from sheet.")

    # Process
    new_rows = process(rows)
    print(f"Processed → {len(new_rows)} rows (incl. header).")

    # Preview first few rows
    for r in new_rows[:5]:
        print(' | '.join(str(c) for c in r))
    print('...')
    print(f"Last row: {new_rows[-1]}")

    # Confirm before writing
    answer = input("\nProceed with writing to sheet? [y/N]: ").strip().lower()
    if answer != 'y':
        print("Aborted.")
        return

    # Clear sheet and write new data
    sheets.values().clear(
        spreadsheetId=SHEET_ID,
        range=SHEET_NAME
    ).execute()

    sheets.values().update(
        spreadsheetId=SHEET_ID,
        range=f'{SHEET_NAME}!A1',
        valueInputOption='USER_ENTERED',
        body={'values': new_rows}
    ).execute()

    print(f"\nDone! Wrote {len(new_rows)} rows to '{SHEET_NAME}'.")

if __name__ == '__main__':
    main()
