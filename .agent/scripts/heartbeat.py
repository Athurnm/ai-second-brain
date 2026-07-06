#!/usr/bin/env python3
"""Shared heartbeat for scheduled routines + specialist agents (observability).

Each job/agent appends one status row so You can SEE on the localhost:3737 "Routines"
panel whether a 2am cloud routine succeeded, without polling. No human owner needed: the
system self-reports; a ❌ row (or a stale last-success) is the signal to act.

Usage:
  python3 .agent/scripts/heartbeat.py --job seo-check --status ok  --summary "you.com: 3 fixes"
  python3 .agent/scripts/heartbeat.py --job evening-update --status fail --summary "work drive token expired" --needs-reauth
  python3 .agent/scripts/heartbeat.py --recent 20     # print recent rows
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.environ.get("AGY_BRIDGE_DATA_DIR", os.path.join(REPO_ROOT, "dashboard-data"))
PATH = os.path.join(DATA_DIR, "agent_heartbeat.jsonl")

def write(job, status, summary, needs_reauth):
    os.makedirs(DATA_DIR, exist_ok=True)
    row = {
        "job": job,
        "ts_wib": datetime.now(WIB).isoformat(timespec="seconds"),
        "status": status,                 # ok | fail
        "summary": (summary or "")[:300],
        "needs_reauth": bool(needs_reauth),
    }
    with open(PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))

def recent(n):
    if not os.path.exists(PATH):
        print("(no heartbeat rows yet)")
        return
    with open(PATH, "r", encoding="utf-8") as fh:
        rows = [l.strip() for l in fh if l.strip()]
    for line in rows[-n:]:
        print(line)

def main():
    ap = argparse.ArgumentParser(description="agent/routine heartbeat")
    ap.add_argument("--job")
    ap.add_argument("--status", choices=["ok", "fail"])
    ap.add_argument("--summary", default="")
    ap.add_argument("--needs-reauth", action="store_true")
    ap.add_argument("--recent", type=int)
    args = ap.parse_args()
    if args.recent:
        recent(args.recent)
        return
    if not args.job or not args.status:
        ap.error("--job and --status required (or use --recent N)")
    write(args.job, args.status, args.summary, args.needs_reauth)

if __name__ == "__main__":
    main()
