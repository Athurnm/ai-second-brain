#!/usr/bin/env python3
"""state_index.py - generate lean indexes from large journal/state JSON files.

Reads:
  journal/state/tickets.json      (~80 KB, 97 tickets with notes/comments/links)
  journal/state/portfolio.json    (~55 KB, teams -> initiatives -> workstreams)
  journal/state/decisions.json    (decision-log ledger, DEC-*)
  journal/state/commitments.json  (commitment-ledger, COM-*)

Writes (with --write):
  journal/state/tickets.index.json
  journal/state/portfolio.index.json
  journal/state/decisions.index.json
  journal/state/commitments.index.json

Each index keeps ONLY the key fields per item (id, title, status, owner,
project, due, ...) so harvest/briefing agents can read the small index first
and load the full body on demand by id.

Usage:
  python3 .agent/scripts/state_index.py            # dry-run: print summary only
  python3 .agent/scripts/state_index.py --write    # write both index files
"""

import argparse
import json
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STATE_DIR = os.path.join(BASE_DIR, 'journal', 'state')

TICKETS_SRC = os.path.join(STATE_DIR, 'tickets.json')
PORTFOLIO_SRC = os.path.join(STATE_DIR, 'portfolio.json')
DECISIONS_SRC = os.path.join(STATE_DIR, 'decisions.json')
COMMITMENTS_SRC = os.path.join(STATE_DIR, 'commitments.json')
TICKETS_IDX = os.path.join(STATE_DIR, 'tickets.index.json')
PORTFOLIO_IDX = os.path.join(STATE_DIR, 'portfolio.index.json')
DECISIONS_IDX = os.path.join(STATE_DIR, 'decisions.index.json')
COMMITMENTS_IDX = os.path.join(STATE_DIR, 'commitments.index.json')

def build_tickets_index(src_path):
    """tickets.json: {updated_wib, source, tickets: [{id, title, priority,
    status, kind, owner, project, note, due, links, initiative_id, ...}]}"""
    with open(src_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    tickets = data.get('tickets', [])
    items = []
    for t in tickets:
        items.append({
            'id': t.get('id'),
            'title': t.get('title'),
            'status': t.get('status'),
            'priority': t.get('priority'),
            'owner': t.get('owner'),
            'project': t.get('project'),
            'due': t.get('due'),
            'initiative_id': t.get('initiative_id'),
        })
    return {
        'generated_from': os.path.relpath(src_path, BASE_DIR),
        'source_updated_wib': data.get('updated_wib'),
        'note': 'Lean index. Full body (note/comments/links) lives in tickets.json; look up by id.',
        'count': len(items),
        'tickets': items,
    }

def build_portfolio_index(src_path):
    """portfolio.json: {updated_wib, schema_version, teams: [{id, name, world,
    owner, initiatives: [{id, name, status, health, owner, now, next_milestone,
    blockers, links, workstreams}]}]}"""
    with open(src_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for team in data.get('teams', []):
        for ini in team.get('initiatives', []):
            workstreams = ini.get('workstreams') or []
            items.append({
                'id': ini.get('id'),
                'title': ini.get('name'),
                'status': ini.get('status'),
                'health': ini.get('health'),
                'owner': ini.get('owner'),
                'project': team.get('name'),
                'due': ini.get('next_milestone'),
                'blocker_count': len(ini.get('blockers') or []),
                'workstream_count': len(workstreams),
                'workstreams_open': sum(
                    1 for w in workstreams if w.get('status') != 'done'),
            })
    return {
        'generated_from': os.path.relpath(src_path, BASE_DIR),
        'source_updated_wib': data.get('updated_wib'),
        'note': 'Lean index. Full body (now/blockers/links/workstreams) lives in portfolio.json; look up by id.',
        'count': len(items),
        'initiatives': items,
    }

def build_decisions_index(src_path):
    """decisions.json: {next_seq, items: {DEC-NNNN: {id, title, status, decider,
    deadline, ...}}, last_sweep} - keep id/title/status/decider/deadline only."""
    with open(src_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for it in (data.get('items') or {}).values():
        items.append({
            'id': it.get('id'),
            'title': it.get('title'),
            'status': it.get('status'),
            'decider': it.get('decider'),
            'deadline': it.get('deadline'),
        })
    items.sort(key=lambda x: x.get('id') or '')
    return {
        'generated_from': os.path.relpath(src_path, BASE_DIR),
        'note': 'Lean index. Full body (decision/sources/stakeholders) lives in decisions.json; look up by id.',
        'count': len(items),
        'decisions': items,
    }

def build_commitments_index(src_path):
    """commitments.json: {next_seq, items: {COM-NNNN: {id, text, to, due,
    status, ...}}, ...} - keep id/title(text)/status/owner(to)/due only."""
    with open(src_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for it in (data.get('items') or {}).values():
        items.append({
            'id': it.get('id'),
            'title': it.get('text'),
            'status': it.get('status'),
            'to': it.get('to'),
            'due': it.get('due'),
        })
    items.sort(key=lambda x: x.get('id') or '')
    return {
        'generated_from': os.path.relpath(src_path, BASE_DIR),
        'note': 'Lean index. Full body (permalink/source/confidence/notes) lives in commitments.json; look up by id.',
        'count': len(items),
        'commitments': items,
    }

def summarize(label, src_path, idx_payload, idx_path):
    src_size = os.path.getsize(src_path)
    idx_json = json.dumps(idx_payload, ensure_ascii=False, indent=1)
    print(f"[{label}]")
    print(f"  source : {src_path} ({src_size:,} bytes)")
    print(f"  index  : {idx_path} ({len(idx_json.encode('utf-8')):,} bytes, "
          f"{idx_payload['count']} items, "
          f"{100 * len(idx_json.encode('utf-8')) / src_size:.0f}% of source)")
    return idx_json

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true',
                        help='write index files (default: dry-run summary only)')
    args = parser.parse_args()

    jobs = [
        ('tickets', TICKETS_SRC, build_tickets_index, TICKETS_IDX),
        ('portfolio', PORTFOLIO_SRC, build_portfolio_index, PORTFOLIO_IDX),
        ('decisions', DECISIONS_SRC, build_decisions_index, DECISIONS_IDX),
        ('commitments', COMMITMENTS_SRC, build_commitments_index, COMMITMENTS_IDX),
    ]
    exit_code = 0
    for label, src, builder, idx_path in jobs:
        if not os.path.exists(src):
            print(f"[{label}] SKIP: source not found: {src}")
            exit_code = 1
            continue
        try:
            payload = builder(src)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[{label}] ERROR reading {src}: {e}")
            exit_code = 1
            continue
        idx_json = summarize(label, src, payload, idx_path)
        if args.write:
            with open(idx_path, 'w', encoding='utf-8') as f:
                f.write(idx_json + '\n')
            print(f"  written: {idx_path}")
        else:
            print("  dry-run: not written (use --write)")
    return exit_code

if __name__ == '__main__':
    sys.exit(main())
