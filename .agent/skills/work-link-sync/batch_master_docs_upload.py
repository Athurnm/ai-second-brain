#!/usr/bin/env python3
"""
Batch upload Master Documentation files to Google Drive and update the spreadsheet.

For each L1 component that is missing a Master Documentation link, this script:
1. Uploads the corresponding local markdown file to Google Drive (as Google Doc)
2. Updates ALL rows of that L1 component in the spreadsheet with the Master Doc HYPERLINK

Usage:
  python3 batch_master_docs_upload.py [--dry-run] [--component "OMS"]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'work-drive-connector'))
from gdrive_manager import authenticate
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─── SPREADSHEET CONFIG ────────────────────────────────────────────────────────
SHEET_ID = '<YOUR_DRIVE_ID>'
SHEET_NAME = 'Master Product List & Breakdown (MECE)'

# ─── REPO BASE PATH ────────────────────────────────────────────────────────────
REPO_BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
CLIENTS_DIR = os.path.join(REPO_BASE, 'Clients', 'Work')

# ─── GOOGLE DRIVE PARENT FOLDER IDs ────────────────────────────────────────────
# These are the Work Drive folders for each product area
# 'None' means: upload to Drive root / search for folder dynamically
DRIVE_FOLDERS = {
    'ecom':    None,  # Will search for "Ecom Solutions" folder or use root
    'b2c':     None,  # Will search for "B2C Superapp" folder
    'seller':  None,  # Will search for "Seller Portal" folder
    'partner': None,  # Will search for "Partner Portal" folder
    'shared':  None,  # Shared Components
    'oms':     None,  # OMS
}

# ─── COMPONENT → FILE MAPPING ─────────────────────────────────────────────────
# Maps (L0, L1) spreadsheet values to local markdown files and display names.
COMPONENT_DOCS = [
    # ─── Ecom Solutions ───────────────────────────────────────────────────────
    {
        'l0': 'Ecom Solutions',
        'l1': 'E-commerce Core',
        'file': os.path.join(CLIENTS_DIR, 'OMS', 'Master_OMS_Documentation.md'),  # OMS = Ecom Core backbone
        'display_name': 'Master E-commerce Core Documentation',
        'note': 'OMS is the Ecom Core backbone — using OMS Master Doc as Ecom Core hub',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'OMS',
        'file': os.path.join(CLIENTS_DIR, 'OMS', 'Master_OMS_Documentation.md'),
        'display_name': 'Master OMS Documentation',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'E-commerce Front-end Builder',
        'file': os.path.join(CLIENTS_DIR, 'Ecommerce', 'Master_EcomFrontend_Documentation.md'),
        'display_name': 'Master Ecom Frontend Builder Documentation',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'TMS',
        'file': os.path.join(CLIENTS_DIR, 'Ecommerce', 'Master_TMS_Documentation.md'),
        'display_name': 'Master TMS Documentation',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'Promo Engine',
        'file': os.path.join(CLIENTS_DIR, 'Ecommerce', 'Master_PromoEngine_Documentation.md'),
        'display_name': 'Master Promo Engine Documentation',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'Search Experience',
        'file': os.path.join(CLIENTS_DIR, 'Ecommerce', 'Master_SearchExperience_Documentation.md'),
        'display_name': 'Master Search Experience Documentation',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'Recommendation & Personalization',
        'file': os.path.join(CLIENTS_DIR, 'Ecommerce', 'Master_RecommendationEngine_Documentation.md'),
        'display_name': 'Master Recommendation Engine Documentation',
    },
    {
        'l0': 'Ecom Solutions',
        'l1': 'Monetization',
        'file': os.path.join(CLIENTS_DIR, 'Ecommerce', 'Master_Monetization_Documentation.md'),
        'display_name': 'Master Monetization Documentation',
    },
    # ─── Seller Portal ────────────────────────────────────────────────────────
    {
        'l0': 'Seller Portal',
        'l1': 'Product Upload & PIM Integration',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_ProductUpload_Documentation.md'),
        'display_name': 'Master SP Product Upload Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Real-Time Price & Stock Update',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_PriceStock_Documentation.md'),
        'display_name': 'Master SP Price & Stock Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Order Fulfillment Workflow',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_OrderFulfillment_Documentation.md'),
        'display_name': 'Master SP Order Fulfillment Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'SFTP Integration',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_SFTPIntegration_Documentation.md'),
        'display_name': 'Master SP SFTP Integration Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Secure Account Management',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_SecureAccount_Documentation.md'),
        'display_name': 'Master SP Secure Account Management Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Order List Enhancements',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_OrderList_Documentation.md'),
        'display_name': 'Master SP Order List Enhancements Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Improvements (General)',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_Improvements_Documentation.md'),
        'display_name': 'Master SP Improvements Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'MFN Elite Self-Shipping',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_MFNElite_Documentation.md'),
        'display_name': 'Master SP MFN Elite Self-Shipping Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Seller Performance Dashboard',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_PerformanceDashboard_Documentation.md'),
        'display_name': 'Master SP Seller Performance Dashboard Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Self-Service Returns',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_Returns_Documentation.md'),
        'display_name': 'Master SP Self-Service Returns Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'RBAC Multi-User',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_RBAC_Documentation.md'),
        'display_name': 'Master SP RBAC Multi-User Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Digital Products',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_DigitalProducts_Documentation.md'),
        'display_name': 'Master SP Digital Products Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'Dispute Resolution',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_DisputeResolution_Documentation.md'),
        'display_name': 'Master SP Dispute Resolution Documentation',
    },
    {
        'l0': 'Seller Portal',
        'l1': 'External API Integration / Developer Portal',
        'file': os.path.join(CLIENTS_DIR, 'Seller Portal', 'Master_SP_ExternalAPI_Documentation.md'),
        'display_name': 'Master SP External API Integration Documentation',
    },
    # ─── B2C Superapp ─────────────────────────────────────────────────────────
    {
        'l0': 'B2C Superapp',
        'l1': 'App Store Launch',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_AppStoreLaunch_Documentation.md'),
        'display_name': 'Master B2C App Store Launch Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'B2C Wallet & Balance Hub',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_WalletBalanceHub_Documentation.md'),
        'display_name': 'Master B2C Wallet & Balance Hub Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Digital Goods Store',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_DigitalGoodsStore_Documentation.md'),
        'display_name': 'Master B2C Digital Goods Store Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Checkout v1 & Payment Gateway',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_Checkout_Documentation.md'),
        'display_name': 'Master B2C Checkout & Payment Gateway Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Work Verification',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_WorkVerification_Documentation.md'),
        'display_name': 'Master B2C Work Verification Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Physical Goods Marketplace',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_PhysicalGoods_Documentation.md'),
        'display_name': 'Master B2C Physical Goods Marketplace Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Gifti Global Migration',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_GiftiMigration_Documentation.md'),
        'display_name': 'Master B2C Gifti Global Migration Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Mixed Payment Engine v.1',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_MixedPayment_Documentation.md'),
        'display_name': 'Master B2C Mixed Payment Engine Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Mixed Payment v.2',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_MixedPayment_Documentation.md'),
        'display_name': 'Master B2C Mixed Payment Engine Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Order Management & Tracking',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_OrderManagement_Documentation.md'),
        'display_name': 'Master B2C Order Management & Tracking Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'In-App Messaging',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_InAppMessaging_Documentation.md'),
        'display_name': 'Master B2C In-App Messaging Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Wishlist & Social',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_WishlistSocial_Documentation.md'),
        'display_name': 'Master B2C Wishlist & Social Documentation',
    },
    {
        'l0': 'B2C Superapp',
        'l1': 'Gamification & mTrust',
        'file': os.path.join(CLIENTS_DIR, 'B2C SuperApp', 'Master_B2C_Gamification_Documentation.md'),
        'display_name': 'Master B2C Gamification & mTrust Documentation',
    },
    # ─── Partner Portal ───────────────────────────────────────────────────────
    {
        'l0': 'Partner Portal',
        'l1': 'Games Aggregator & Providers B2B/B2C',
        'file': os.path.join(CLIENTS_DIR, 'Partner Portal', 'Master_PP_GamesAggregator_Documentation.md'),
        'display_name': 'Master PP Games Aggregator Documentation',
    },
    {
        'l0': 'Partner Portal',
        'l1': 'Content Music/Video/Education',
        'file': os.path.join(CLIENTS_DIR, 'Partner Portal', 'Master_PP_ContentMedia_Documentation.md'),
        'display_name': 'Master PP Content Media & Education Documentation',
    },
    {
        'l0': 'Partner Portal',
        'l1': 'Vendor Registration',
        'file': os.path.join(CLIENTS_DIR, 'Partner Portal', 'Master_PP_VendorRegistration_Documentation.md'),
        'display_name': 'Master PP Vendor Registration Documentation',
    },
    {
        'l0': 'Partner Portal',
        'l1': 'Vendor Migration',
        'file': os.path.join(CLIENTS_DIR, 'Partner Portal', 'Master_PP_VendorMigration_Documentation.md'),
        'display_name': 'Master PP Vendor Migration Documentation',
    },
]

def upload_markdown_as_doc(drive, file_path, display_name):
    """Upload a markdown file to Google Drive as a Google Doc."""
    if not os.path.exists(file_path):
        print(f"  ✗ File not found: {file_path}")
        return None

    media = MediaFileUpload(file_path, mimetype='text/plain', resumable=False)
    file_metadata = {
        'name': display_name,
        'mimeType': 'application/vnd.google-apps.document',
    }

    result = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webViewLink',
        supportsAllDrives=True
    ).execute()

    return result.get('id'), result.get('webViewLink')

def update_spreadsheet_rows(sheets, rows, l0, l1, url, display_name, dry_run=False):
    """Update all rows matching l0+l1 in column D with HYPERLINK formula."""
    formula = f'=HYPERLINK("{url}","{display_name}")'
    updates = []

    for i, row in enumerate(rows, start=1):
        row_l0 = row[0] if len(row) > 0 else ''
        row_l1 = row[1] if len(row) > 1 else ''
        if row_l0 == l0 and row_l1 == l1:
            updates.append({
                'range': f"'{SHEET_NAME}'!D{i}",
                'values': [[formula]]
            })

    if updates:
        if dry_run:
            print(f"  [DRY RUN] Would update {len(updates)} rows for [{l0}][{l1}]")
        else:
            sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={'valueInputOption': 'USER_ENTERED', 'data': updates}
            ).execute()
            print(f"  ✓ Spreadsheet: Updated {len(updates)} rows for [{l0}][{l1}]")
    else:
        print(f"  ⚠ No rows found for [{l0}][{l1}]")

    return len(updates)

def main():
    parser = argparse.ArgumentParser(description='Batch upload Master Docs + update spreadsheet')
    parser.add_argument('--dry-run', action='store_true', help='Print what would happen without making changes')
    parser.add_argument('--component', help='Only process this L1 component (for testing)')
    parser.add_argument('--skip-upload', action='store_true', help='Skip Drive upload, only update sheet (requires --url)')
    args = parser.parse_args()

    creds = authenticate()
    if not creds:
        print("Authentication failed.")
        sys.exit(1)

    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)

    # Load spreadsheet rows once
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{SHEET_NAME}'!A1:H300",
        valueRenderOption='FORMULA'
    ).execute()
    rows = result.get('values', [])
    print(f"Loaded {len(rows)} spreadsheet rows.\n")

    # Track uploaded files to avoid duplicate uploads (same file, multiple L1s)
    uploaded_cache = {}  # file_path → (file_id, url)

    components = COMPONENT_DOCS
    if args.component:
        components = [c for c in COMPONENT_DOCS if args.component.lower() in c['l1'].lower()]
        if not components:
            print(f"No component matching '{args.component}' found.")
            sys.exit(1)

    total_uploaded = 0
    total_rows_updated = 0

    for comp in components:
        l0 = comp['l0']
        l1 = comp['l1']
        file_path = comp['file']
        display_name = comp['display_name']
        note = comp.get('note', '')

        print(f"\n── [{l0}] [{l1}]")
        if note:
            print(f"   Note: {note}")

        if not os.path.exists(file_path):
            print(f"  ✗ Missing file: {file_path}")
            continue

        # Upload to Drive (with caching)
        if args.skip_upload:
            url = input(f"  Enter URL for '{display_name}': ").strip()
        elif file_path in uploaded_cache:
            file_id, url = uploaded_cache[file_path]
            print(f"  ↩ Using cached upload: {url}")
        else:
            if args.dry_run:
                print(f"  [DRY RUN] Would upload: {os.path.basename(file_path)}")
                url = f"https://docs.google.com/document/d/DRY_RUN_{l1.replace(' ', '_')}/edit"
                uploaded_cache[file_path] = (None, url)
            else:
                print(f"  ↑ Uploading '{display_name}'...")
                result = upload_markdown_as_doc(drive, file_path, display_name)
                if result is None:
                    continue
                file_id, url = result
                uploaded_cache[file_path] = (file_id, url)
                print(f"  ✓ Drive: {url}")
                total_uploaded += 1

        # Update spreadsheet
        n = update_spreadsheet_rows(sheets, rows, l0, l1, url, display_name, dry_run=args.dry_run)
        total_rows_updated += n

    print(f"\n{'─' * 50}")
    print(f"Done.")
    print(f"  Files uploaded to Drive: {total_uploaded}")
    print(f"  Spreadsheet rows updated: {total_rows_updated}")

if __name__ == '__main__':
    main()
