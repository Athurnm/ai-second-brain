#!/usr/bin/env python3
"""
Add 19 missing items from Copy - WIP to Master Product List.

Master column layout: A=L0, B=L1(HYPERLINK), C=L2, D=Documents/Links, E=Status, F=PRD Status, G=L3, H=Phase
WIP column layout:    A=L0, B=L1(plain),     C=L2, D=L3,               E=Status, F=PRD Status, G=Week1, H=Week2

Mapping WIP→Master:
  WIP[A] → Master[A]  (L0)
  WIP[B] → Master[B]  (L1, with HYPERLINK if master doc exists)
  WIP[C] → Master[C]  (L2)
  ''      → Master[D]  (Documents/Links — leave blank; PRDs added separately)
  WIP[E] → Master[E]  (Status)
  WIP[F] → Master[F]  (PRD Status)
  WIP[D] → Master[G]  (L3: Detailed Item)
  ''      → Master[H]  (Phase — leave blank)
"""

import os, sys, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'work-drive-connector'))
from gdrive_manager import authenticate
from googleapiclient.discovery import build

SHEET_ID = '<YOUR_DRIVE_ID>'
MAIN_TAB = 'Master Product List & Breakdown (MECE)'
WIP_TAB = 'Copy - WIP'

# Master Doc URLs for L1 components that have them (from fix_column_b_links.py)
MASTER_DOC_URLS = {
    'PIM': 'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
    'Product Upload & PIM Integration': 'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
    'Improvements (General)': 'https://docs.google.com/document/d/<YOUR_DRIVE_ID>/edit?usp=drivesdk',
    # 'Onboarding & KYB' — no Master Doc yet, leave col B as plain text
}

def build_col_b(l1_label):
    """Return HYPERLINK formula if master doc exists, else plain text."""
    url = MASTER_DOC_URLS.get(l1_label)
    if url:
        return f'=HYPERLINK("{url}","{l1_label}")'
    return l1_label

def pad(row, n=8):
    return list(row) + [''] * (n - len(row))

def extract_label(cell):
    """Extract display label from =HYPERLINK("url","label") formula."""
    if isinstance(cell, str) and cell.startswith('=HYPERLINK('):
        m = re.search(r'=HYPERLINK\("[^"]*","([^"]+)"\)', cell)
        if m:
            return m.group(1)
    return cell or ''

def norm(s):
    return (s or '').strip().rstrip()

def get_rows(sheets, tab, render='FORMULA', rng='A1:H300'):
    return sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{tab}'!{rng}",
        valueRenderOption=render
    ).execute().get('values', [])

def get_sheet_gid(sheets):
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta['sheets']:
        if s['properties']['title'] == MAIN_TAB:
            return s['properties']['sheetId']
    raise ValueError(f"Tab '{MAIN_TAB}' not found")

def wip_to_master_row(wip_row):
    """Convert a WIP row (8 cols) to a Master row (8 cols)."""
    r = pad(wip_row, 8)
    l0      = r[0]  # A
    l1_raw  = r[1]  # B (plain text in WIP)
    l2      = norm(r[2])  # C
    l3      = norm(r[3])  # D in WIP → G in master
    status  = r[4]  # E
    prd_st  = r[5]  # F

    l1_label = norm(extract_label(l1_raw))
    col_b = build_col_b(l1_label) if l1_label else ''

    return [l0, col_b, l2, '', status, prd_st, l3, '']

def main():
    dry_run = '--dry-run' in sys.argv

    creds = authenticate()
    sheets = build('sheets', 'v4', credentials=creds)

    # ── Load WIP (rows 1-90) ──────────────────────────────────────────────────
    print("Loading WIP tab...")
    wip_rows = get_rows(sheets, WIP_TAB, rng='A1:H90')
    # WIP header row 1 (index 0), data starts index 1
    print(f"  {len(wip_rows)} rows")

    # ── Collect the specific WIP rows we want, preserving order ──────────────
    # Groups in WIP order:
    #   1) PIM / Catalog Service two way product sync    (rows 10-12 = indices 9-11)
    #   2) Product Upload / Testing & Prod deployment    (row 62 = index 61)
    #   3) blank-L1 / Orders & fulfilment integration    (rows 63-67 = indices 62-66)
    #   4) Improvements (General) items                  (rows 68-79 = indices 67-78)
    #   5) Onboarding & KYB                              (rows 80-83 = indices 79-82)

    # Define the L2 values to capture per group (used to identify rows)
    pim_catalog_l2      = 'Catalog Service two way product sync'
    prod_upload_l2      = 'Testing & Prod deployment'
    orders_l2           = 'Orders & fulfilment integration'
    improvements_l2s    = {
        'JustLaunch Shipping: Ship-to-Office & Repackage',
        'Hide Customer Details Before Order Acceptance',
        'AWB Upload: Support Image Files',
        'Self-Managed Delivery: Automated Status via Estimated Time',
        'Admin LiveOps: Show Courier & Tracking Info',
        'Tenant-Specific Last-Mile Logistics',
        'Order Export Enhancements',
        'Order Cancellation Logic',
        'Bulk Accept Orders & Bulk Create AWB',
        'Regulatory: National Address (Short Format) Enforcement',
        'New Order Email notification with Throttling',
        'AWB Ready Email Notification with Throttling',
    }
    kyb_l1 = 'Onboarding & KYB'

    # Collect by group — each group is (label, [wip_row, ...])
    group_pim_catalog   = []
    group_prod_upload   = []
    group_orders        = []
    group_improvements  = []
    group_kyb           = []

    for i, raw in enumerate(wip_rows[1:], start=2):  # 1-based row number
        r = pad(raw, 8)
        l0  = norm(r[0])
        l1  = norm(r[1])
        l2  = norm(r[2])
        l3  = norm(r[3])

        if l0 == 'Ecom Solutions' and l1 == 'PIM' and l2 == pim_catalog_l2:
            group_pim_catalog.append(raw)
        elif l0 == 'Seller Portal' and l1 == 'Product Upload & PIM Integration' and l2 == prod_upload_l2:
            group_prod_upload.append(raw)
        elif l0 == 'Seller Portal' and l1 == '' and l2 == orders_l2:
            group_orders.append(raw)
        elif l0 == 'Seller Portal' and l1 == 'Improvements (General)' and l2 in improvements_l2s:
            group_improvements.append(raw)
        elif l0 == 'Seller Portal' and l1 == kyb_l1:
            group_kyb.append(raw)

    print(f"\nCollected from WIP:")
    print(f"  PIM Catalog Service rows: {len(group_pim_catalog)}")
    print(f"  Product Upload Testing row: {len(group_prod_upload)}")
    print(f"  Orders & fulfilment rows: {len(group_orders)}")
    print(f"  Improvements (General) rows: {len(group_improvements)}")
    print(f"  Onboarding & KYB rows: {len(group_kyb)}")

    # Convert to master format
    master_pim_catalog   = [wip_to_master_row(r) for r in group_pim_catalog]
    master_prod_upload   = [wip_to_master_row(r) for r in group_prod_upload]
    master_orders        = [wip_to_master_row(r) for r in group_orders]
    master_improvements  = [wip_to_master_row(r) for r in group_improvements]
    master_kyb           = [wip_to_master_row(r) for r in group_kyb]

    if dry_run:
        print("\n[DRY RUN] Rows to be inserted:")
        for label, rows in [
            ('PIM Catalog Service', master_pim_catalog),
            ('Product Upload Testing', master_prod_upload),
            ('Orders & fulfilment', master_orders),
            ('Improvements (General)', master_improvements),
            ('Onboarding & KYB', master_kyb),
        ]:
            print(f"\n  == {label} ==")
            for r in rows:
                print(f"    {r}")
        return

    # ── Load master to find insertion points ─────────────────────────────────
    print("\nLoading master tab...")
    master_rows = get_rows(sheets, MAIN_TAB, rng='A1:H300')
    print(f"  {len(master_rows)} rows")

    # Build index: (l1_label, l2_label) → last row number (1-based)
    last_row_of = {}  # key=(l1,l2) → row_number
    l1_last_row = {}  # key=l1 → last row number with that l1

    for i, raw in enumerate(master_rows[1:], start=2):
        r = pad(raw, 8)
        l1 = norm(extract_label(r[1]))
        l2 = norm(r[2])
        key = (l1, l2)
        last_row_of[key] = i
        if l1:
            l1_last_row[l1] = i

    def find_insert_after(l1_label, l2_label=None):
        """Return the row number after which we insert."""
        if l2_label:
            k = (l1_label, l2_label)
            if k in last_row_of:
                return last_row_of[k]
        if l1_label in l1_last_row:
            return l1_last_row[l1_label]
        return None

    # Determine insertion points (check before any inserts since indices shift)
    # We process from BOTTOM to TOP so early indices are not displaced

    plan = []

    # 5) Onboarding & KYB — insert after last Improvements (General) row
    after_kyb = find_insert_after('Improvements (General)')
    plan.append(('Onboarding & KYB', after_kyb, master_kyb))

    # 4) Improvements (General) — insert after last existing Improvements (General) row
    after_impr = find_insert_after('Improvements (General)')
    plan.append(('Improvements (General)', after_impr, master_improvements))

    # 3) Orders & fulfilment integration — insert after last Product Upload & PIM Integration row
    after_orders = find_insert_after('Product Upload & PIM Integration')
    plan.append(('Orders & fulfilment integration', after_orders, master_orders))

    # 2) Product Upload: Testing & Prod deployment — insert after last Product Upload row
    after_pu = find_insert_after('Product Upload & PIM Integration')
    plan.append(('Product Upload & PIM Integration (Testing row)', after_pu, master_prod_upload))

    # 1) PIM Catalog Service — insert after last "Category & Attribute Structure" row
    after_pim = find_insert_after('PIM', 'Category & Attribute Structure')
    plan.append(('PIM Catalog Service', after_pim, master_pim_catalog))

    print("\nInsertion plan (bottom-to-top order):")
    for label, after_row, rows in plan:
        print(f"  '{label}': {len(rows)} rows after master row {after_row}")

    # Sort descending by row number so we insert bottom-first
    plan.sort(key=lambda x: x[1] if x[1] else 0, reverse=True)

    gid = get_sheet_gid(sheets)

    for label, after_row, rows in plan:
        if not rows:
            print(f"  SKIP '{label}': no rows to insert")
            continue
        n = len(rows)

        if after_row is None:
            # Append to end
            sheets.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range=f"'{MAIN_TAB}'!A1",
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': rows}
            ).execute()
            print(f"  ✓ Appended {n} rows for '{label}'")
            continue

        # Insert n blank rows after after_row (0-based index = after_row)
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={'requests': [{
                'insertDimension': {
                    'range': {
                        'sheetId': gid,
                        'dimension': 'ROWS',
                        'startIndex': after_row,   # insert AFTER row after_row (0-based = after_row)
                        'endIndex':   after_row + n
                    },
                    'inheritFromBefore': True
                }
            }]}
        ).execute()

        # Fill the new rows
        start = after_row + 1  # 1-based
        sheets.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"'{MAIN_TAB}'!A{start}:H{start + n - 1}",
            valueInputOption='USER_ENTERED',
            body={'values': rows}
        ).execute()

        print(f"  ✓ Inserted {n} rows after master row {after_row} for '{label}'")

    total = sum(len(r) for _, _, r in plan)
    print(f"\nDone. {total} rows added to Master Product List.")

if __name__ == '__main__':
    main()
