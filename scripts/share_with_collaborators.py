#!/usr/bin/env python3
"""Grant the standing Work collaborators (Teammate + known ExampleVendor team) commenter
access on a Drive file.

Standing rule (You, 2026-06-24): always allow Teammate and all known ExampleVendor team
to access the Master Product List and any document we create, with comment access.

Run this AFTER the domain-restrict step on any Work GDoc we create/update, so the
external ExampleVendor collaborators (who are not on the workincentives.com domain grant)
can still open and comment.

The collaborator list lives in scripts/work_collaborators.txt (one email per line).

Usage:
  python3 scripts/share_with_collaborators.py --id FILE_ID [--role commenter|writer|reader] [--account work|personal] [--dry-run]
"""
import argparse, os, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = {
    "work": os.path.join(REPO, ".agent/skills/work-drive-connector/token.json"),
    "personal": os.path.join(REPO, ".agent/skills/google-drive-connector/token.json"),
}
LIST_FILE = os.path.join(REPO, "scripts/work_collaborators.txt")

def load_emails():
    emails = []
    with open(LIST_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                emails.append(line)
    return emails

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="Drive file ID")
    ap.add_argument("--role", default="commenter", choices=["commenter", "writer", "reader"])
    ap.add_argument("--account", default="work", choices=["work", "personal"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    emails = load_emails()
    print(f"Collaborators to grant '{args.role}' on {args.id}: {len(emails)}")
    if args.dry_run:
        for e in emails:
            print(f"  [dry-run] {e}")
        return

    creds = Credentials.from_authorized_user_file(TOKENS[args.account])
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
    svc = build("drive", "v3", credentials=creds)

    ok, skipped = 0, 0
    for e in emails:
        try:
            svc.permissions().create(
                fileId=args.id,
                body={"type": "user", "role": args.role, "emailAddress": e},
                sendNotificationEmail=False,
                supportsAllDrives=True,
                fields="id",
            ).execute()
            print(f"  ✓ {e}")
            ok += 1
        except HttpError as err:
            print(f"  ! {e}: {err}")
            skipped += 1
    print(f"Done. granted={ok} skipped/errors={skipped}")

if __name__ == "__main__":
    main()
