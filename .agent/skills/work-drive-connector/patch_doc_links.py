#!/usr/bin/env python3
"""
patch_doc_links.py — Patch stale Google Doc hyperlinks programmatically.

Usage:
  python3 patch_doc_links.py --doc-id DOC_ID --mapping old_id:new_id [old_id:new_id ...]
  python3 patch_doc_links.py --doc-id DOC_ID --mapping-file mappings.txt
  python3 patch_doc_links.py --doc-id DOC_ID --dry-run

Mapping file format (one per line):
  old_id:new_id

The script scans every TextRun in the document for hyperlinks whose URL
contains an old ID, then replaces the URL with the new ID via batchUpdate.
"""
import os
import sys
import json
import argparse
import signal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
SCOPES = ["https://www.googleapis.com/auth/drive"]

def timeout_handler(signum, frame):
    print("[ERROR] Timed out after 180 seconds", file=sys.stderr)
    sys.exit(1)

if os.name != "nt":
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)

def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print(f"[ERROR] No valid token at {TOKEN_FILE}. Re-authenticate first.")
            sys.exit(1)
    return creds

def collect_link_runs(content, mapping, dry_run):
    """
    Walk all structural elements and collect (startIndex, endIndex, old_url, new_url)
    for every TextRun whose link URL contains a stale ID.
    """
    updates = []

    def walk_elements(elements):
        for elem in elements:
            if "paragraph" in elem:
                for pe in elem["paragraph"].get("elements", []):
                    if "textRun" not in pe:
                        continue
                    tr = pe["textRun"]
                    link = tr.get("textStyle", {}).get("link", {})
                    url = link.get("url", "")
                    if not url:
                        continue
                    for old_id, new_id in mapping.items():
                        if old_id in url:
                            new_url = url.replace(old_id, new_id)
                            updates.append({
                                "startIndex": pe["startIndex"],
                                "endIndex": pe["endIndex"],
                                "old_url": url,
                                "new_url": new_url,
                            })
                            break
            elif "table" in elem:
                for row in elem["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        walk_elements(cell.get("content", []))
            elif "tableOfContents" in elem:
                walk_elements(elem["tableOfContents"].get("content", []))

    walk_elements(content)
    return updates

def build_update_requests(updates):
    """Convert collected updates to Docs API batchUpdate requests."""
    requests = []
    for u in updates:
        requests.append({
            "updateTextStyle": {
                "range": {
                    "startIndex": u["startIndex"],
                    "endIndex": u["endIndex"],
                },
                "textStyle": {
                    "link": {"url": u["new_url"]}
                },
                "fields": "link",
            }
        })
    return requests

def main():
    parser = argparse.ArgumentParser(description="Patch stale hyperlinks in a Google Doc")
    parser.add_argument("--doc-id", required=True, help="Google Doc ID to patch")
    parser.add_argument(
        "--mapping",
        nargs="+",
        metavar="OLD:NEW",
        help="One or more old_id:new_id pairs",
    )
    parser.add_argument(
        "--mapping-file",
        help="Path to a text file with one old_id:new_id per line",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing anything",
    )
    args = parser.parse_args()

    # Build mapping dict
    mapping = {}
    if args.mapping:
        for pair in args.mapping:
            parts = pair.split(":", 1)
            if len(parts) != 2:
                print(f"[ERROR] Bad mapping format: {pair}  (expected old_id:new_id)")
                sys.exit(1)
            mapping[parts[0].strip()] = parts[1].strip()
    if args.mapping_file:
        with open(args.mapping_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":", 1)
                if len(parts) != 2:
                    print(f"[WARN] Skipping bad line: {line}")
                    continue
                mapping[parts[0].strip()] = parts[1].strip()

    if not mapping and not args.dry_run:
        print("[ERROR] No mappings provided. Use --mapping or --mapping-file.")
        sys.exit(1)

    creds = authenticate()
    docs_service = build("docs", "v1", credentials=creds)

    print(f"[INFO] Fetching document {args.doc_id}...")
    doc = docs_service.documents().get(documentId=args.doc_id).execute()
    title = doc.get("title", "(untitled)")
    print(f"[INFO] Document: \"{title}\"")

    content = doc.get("body", {}).get("content", [])
    updates = collect_link_runs(content, mapping, args.dry_run)

    if not updates:
        print("[OK] No stale hyperlinks found. Nothing to change.")
        return

    print(f"\n[FOUND] {len(updates)} hyperlink(s) to patch:")
    for u in updates:
        print(f"  chars [{u['startIndex']}–{u['endIndex']}]")
        print(f"    OLD: {u['old_url']}")
        print(f"    NEW: {u['new_url']}")

    if args.dry_run:
        print("\n[DRY-RUN] No changes written.")
        return

    print(f"\n[INFO] Sending batchUpdate with {len(updates)} request(s)...")
    requests = build_update_requests(updates)
    result = docs_service.documents().batchUpdate(
        documentId=args.doc_id,
        body={"requests": requests},
    ).execute()
    print(f"[DONE] Patched {len(updates)} hyperlink(s) in \"{title}\".")
    print(f"       Doc: https://docs.google.com/document/d/{args.doc_id}/edit")

if __name__ == "__main__":
    main()
