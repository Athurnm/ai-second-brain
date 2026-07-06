#!/usr/bin/env python3
"""
List / restrict Google Drive permissions for Work-owned files.

Reuses the work-drive-connector token. Drive scope covers permissions.

Usage:
  python3 .agent/scripts/drive_permissions.py list   <FILE_ID> [<FILE_ID> ...]
  python3 .agent/scripts/drive_permissions.py restrict <FILE_ID> [--domain DOMAIN] [--apply]

"restrict" removes any 'anyone' (public link) permission. If --domain is given,
it also grants that domain commenter access so the team keeps access. Without
--apply it is a DRY RUN (prints what it would do).
"""
import sys
import os
import argparse

CONNECTOR = os.path.join(
    os.path.dirname(__file__), "..", "skills", "work-drive-connector"
)
sys.path.insert(0, CONNECTOR)
os.chdir(CONNECTOR)  # token.json / credentials.json are resolved relative to cwd

import warnings
warnings.filterwarnings("ignore")

from googleapiclient.discovery import build  # type: ignore
from gdrive_manager import authenticate  # type: ignore

def _service():
    creds = authenticate()
    return build("drive", "v3", credentials=creds)

def list_perms(service, file_id):
    meta = service.files().get(
        fileId=file_id, fields="name,owners(emailAddress),mimeType"
    ).execute()
    perms = service.permissions().list(
        fileId=file_id,
        fields="permissions(id,type,role,emailAddress,domain,allowFileDiscovery)",
    ).execute().get("permissions", [])
    print(f"\n■ {meta.get('name')}  [{file_id}]")
    owners = ", ".join(o.get("emailAddress", "?") for o in meta.get("owners", []))
    print(f"  owner: {owners}")
    for p in perms:
        who = p.get("emailAddress") or p.get("domain") or p.get("type")
        flag = "  ⚠️ PUBLIC" if p.get("type") == "anyone" else ""
        print(f"  - [{p.get('type')}] {who}  role={p.get('role')}  id={p.get('id')}{flag}")
    return meta, perms

def restrict(service, file_id, domain, apply):
    meta, perms = list_perms(service, file_id)
    public = [p for p in perms if p.get("type") == "anyone"]
    has_domain = any(p.get("type") == "domain" and p.get("domain") == domain for p in perms)
    actions = []
    for p in public:
        actions.append(("remove-public", p["id"]))
    if domain and not has_domain:
        actions.append(("add-domain", domain))
    if not actions:
        print("  → already restricted; nothing to do.")
        return
    for kind, val in actions:
        if not apply:
            print(f"  [DRY] would {kind}: {val}")
            continue
        if kind == "remove-public":
            service.permissions().delete(fileId=file_id, permissionId=val).execute()
            print(f"  ✓ removed public permission {val}")
        elif kind == "add-domain":
            body = {"type": "domain", "role": "commenter", "domain": val}
            service.permissions().create(
                fileId=file_id, body=body, fields="id"
            ).execute()
            print(f"  ✓ granted domain '{val}' commenter access")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list"); pl.add_argument("ids", nargs="+")
    pr = sub.add_parser("restrict")
    pr.add_argument("ids", nargs="+")
    pr.add_argument("--domain", default=None)
    pr.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    service = _service()
    for fid in a.ids:
        try:
            if a.cmd == "list":
                list_perms(service, fid)
            else:
                restrict(service, fid, a.domain, a.apply)
        except Exception as e:
            print(f"\n■ {fid}\n  ERROR: {e}")

if __name__ == "__main__":
    main()
