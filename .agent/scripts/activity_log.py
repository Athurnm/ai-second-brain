#!/usr/bin/env python3
"""Append-only activity event log (the harness's full-context memory).

Every meaningful action by You OR the agent appends one event here, tagged to a project,
so the dashboard can roll it up and the agent always has context. Append-only = no corruption.

Usage:
  python3 .agent/scripts/activity_log.py --actor agent --action task_done \
    --project "AI Circle" --target social-producer --summary "Built /social-plan command"
  python3 .agent/scripts/activity_log.py --recent 20
  python3 .agent/scripts/activity_log.py --recent 20 --project Marketplace
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOG = os.path.join(REPO, "journal", "activity_log.jsonl")

def _next_id():
    n = 0
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
    return f"evt-{n + 1:05d}"

def append(actor, action, project, target, summary, refs):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    row = {
        "event_id": _next_id(),
        "ts_wib": datetime.now(WIB).isoformat(timespec="seconds"),
        "actor": actor,                 # brian | agent
        "action": action,               # task_done | daily_update | slack_reply | doc_update | status_change | note | ...
        "target_type": "ticket" if (target or "").upper().startswith(("S-", "E-", "O-", "T-")) else "other",
        "target_id": target or "",
        "project": project or "Other",
        "summary": (summary or "")[:300],
        "refs": refs or [],
    }
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))

def recent(n, project):
    if not os.path.exists(LOG):
        print("(no events yet)")
        return
    rows = []
    with open(LOG, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if project and r.get("project") != project:
                continue
            rows.append(r)
    for r in rows[-n:]:
        print(json.dumps(r, ensure_ascii=False))

def main():
    ap = argparse.ArgumentParser(description="append-only activity event log")
    ap.add_argument("--actor", choices=["brian", "agent"], default="agent")
    ap.add_argument("--action")
    ap.add_argument("--project", default="Other")
    ap.add_argument("--target", default="")
    ap.add_argument("--summary", default="")
    ap.add_argument("--ref", action="append", default=[], help="a link/ref (repeatable)")
    ap.add_argument("--recent", type=int)
    args = ap.parse_args()
    if args.recent:
        recent(args.recent, args.project if args.project != "Other" else None)
        return
    if not args.action:
        ap.error("--action required (or use --recent N)")
    append(args.actor, args.action, args.project, args.target, args.summary, args.ref)

if __name__ == "__main__":
    main()
