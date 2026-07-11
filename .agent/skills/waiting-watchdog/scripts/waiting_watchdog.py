#!/usr/bin/env python3
"""
waiting_watchdog.py - SLA watchdog for things You is waiting on from other people.

Design (per plan bangun-aja-semuanya-barengan-wiggly-noodle.md, Komponen 3):
  sweep (cron, hourly, pure local, zero-network): age-vs-SLA check only.
    since + sla_hours elapsed and status still open -> status=breached, breached_at set.
  sweep --check-slack (SOP-only, Claude-driven, NOT cron'd): for items with a Slack
    source, checks conversations.replies in the source thread for an owner reply
    posted after `since` -> status=answered.

Subcommands:
  add     --owner --what --sla-hours [--escalate-to] [--escalation-path] [--source] [--since]
  sweep   [--check-slack]
  report  [--all]
  close   <id>
  drop    <id>
  touch   <id>     (nudge: reset since=now, stamp last_nudge_at)

State: journal/state/waiting_on.json
Schema per item WAIT-NNNN: {id, owner, owner_slug, what, since, sla_hours, escalate_to,
  escalation_path, source{type, permalink}, status: open|breached|answered|dropped,
  breached_at, last_nudge_at, first_seen, closed_at, notes}

Clones conventions from .agent/skills/slack-tracker/scripts/mention_ledger.py:
BASE_DIR from __file__, load_state/save_state atomic .tmp+os.replace, argparse
subcommands, API_PAUSE between Slack calls, briefing-ready markdown from report.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
STATE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'waiting_on.json')
TOKEN_ENV = os.path.join(BASE_DIR, '.agent', 'skills', 'slack-connector', 'token.env')
HEARTBEAT = os.path.join(BASE_DIR, '.agent', 'scripts', 'heartbeat.py')
PEOPLE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'people.json')

DROPPED_RETENTION_DAYS = 14      # prune answered/dropped after this
API_PAUSE = 0.15

# ------------------------------------------------------------------- utils --

def slugify(name):
    s = (name or '').strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

_PERSON_LOOKUP = None   # cache: {lowercase name/alias/first-name -> canonical slug}

def _load_person_lookup():
    """journal/state/people.json is the canonical roster (owned by the
    stakeholders component). Build a case-insensitive lookup of full name,
    every alias, and unambiguous first names (first token of `name`, only
    when it maps to exactly one roster slug). Cached per process; graceful
    (empty lookup) if people.json is missing or unparseable."""
    global _PERSON_LOOKUP
    if _PERSON_LOOKUP is not None:
        return _PERSON_LOOKUP
    lookup = {}
    people = {}
    if os.path.exists(PEOPLE_PATH):
        try:
            with open(PEOPLE_PATH, encoding='utf-8') as f:
                data = json.load(f)
            people = data.get('people', {}) if isinstance(data, dict) else {}
        except Exception:
            people = {}
    first_name_owners = {}
    for slug, person in people.items():
        name = (person.get('name') or '').strip()
        if name:
            lookup.setdefault(name.lower(), slug)
            first = name.split()[0].lower()
            first_name_owners.setdefault(first, set()).add(slug)
        for alias in person.get('aliases') or []:
            alias = (alias or '').strip()
            if alias:
                lookup.setdefault(alias.lower(), slug)
    for first, slugs in first_name_owners.items():
        if len(slugs) == 1:
            lookup.setdefault(first, next(iter(slugs)))
    _PERSON_LOOKUP = lookup
    return lookup

def resolve_person_slug(name):
    """Resolve a captured name against the people.json roster (full name /
    alias / unambiguous first name, case-insensitive) -> canonical slug.
    Falls back to bare slugify() on a miss or a missing roster."""
    n = (name or '').strip()
    if not n:
        return slugify(name)
    return _load_person_lookup().get(n.lower()) or slugify(name)

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {'items': {}, 'next_seq': 1, 'last_sweep': None}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)

def next_id(state):
    n = state.get('next_seq', 1)
    state['next_seq'] = n + 1
    return f'WAIT-{n:04d}'

def age_hours(ts):
    return (time.time() - float(ts)) / 3600

def age_str(hours):
    return f'{hours/24:.1f}d' if hours >= 24 else f'{hours:.0f}h'

# ---------------------------------------------------------------- Slack API --

def load_token():
    tok = os.environ.get('SLACK_USER_TOKEN')
    if not tok and os.path.exists(TOKEN_ENV):
        for line in open(TOKEN_ENV):
            line = line.strip()
            if line.startswith('SLACK_USER_TOKEN='):
                tok = line.split('=', 1)[1].strip().strip('"').strip("'")
    if not tok:
        sys.exit('FATAL: SLACK_USER_TOKEN not found (env or slack-connector/token.env)')
    return tok

def slack(method, token, params=None, retries=3):
    params = params or {}
    url = f'https://slack.com/api/{method}?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    for attempt in range(retries):
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:
            if attempt == retries - 1:
                return {'ok': False, 'error': f'request_failed: {e}'}
            time.sleep(2 * (attempt + 1))
            continue
        if resp.get('ok'):
            return resp
        if resp.get('error') == 'ratelimited':
            time.sleep(int(resp.get('retry_after', 10)) if isinstance(resp.get('retry_after'), (int, str)) else 10)
            continue
        return resp
    return {'ok': False, 'error': 'retries_exhausted'}

PERMALINK_RE = re.compile(r'archives/(C[A-Z0-9]+)/p(\d{16})(?:\?thread_ts=([\d.]+))?')

def parse_permalink(permalink):
    """Return (channel_id, ts, thread_ts_or_None) from a Slack permalink."""
    m = PERMALINK_RE.search(permalink or '')
    if not m:
        return None
    cid, raw_ts, thread_ts = m.group(1), m.group(2), m.group(3)
    ts = f'{raw_ts[:10]}.{raw_ts[10:]}'
    return cid, ts, thread_ts

def owner_replied_since(token, source, owner_hint, since_ts):
    """conversations.replies on the source thread: any message after since_ts from
    someone other than You (best-effort owner match; conservative - any non-You
    reply in-thread after `since` counts, since we don't reliably know owner's U-id)."""
    parsed = parse_permalink(source.get('permalink', ''))
    if not parsed:
        return False, None
    cid, ts, thread_ts = parsed
    anchor = thread_ts or ts
    resp = slack('conversations.replies', token, {'channel': cid, 'ts': anchor, 'limit': 200})
    time.sleep(API_PAUSE)
    if not resp.get('ok'):
        return False, None
    msgs = resp.get('messages', [])
    brian_id = os.environ.get('BRIAN_SLACK_ID', '<SLACK_ID>')
    for m in msgs:
        mts = float(m.get('ts', 0))
        if mts <= float(since_ts):
            continue
        if m.get('user') == brian_id:
            continue
        return True, mts
    return False, None

# ------------------------------------------------------------------- sweep --

def cmd_add(args):
    state = load_state()
    since = args.since if args.since else time.time()
    if args.since:
        # accept epoch seconds or ISO-ish; try float first
        try:
            since = float(args.since)
        except ValueError:
            sys.exit(f'--since must be an epoch timestamp, got: {args.since}')
    item_id = next_id(state)
    source = {}
    if args.source:
        source = {'type': 'slack' if 'slack.com' in args.source else 'manual',
                  'permalink': args.source}
    state['items'][item_id] = {
        'id': item_id,
        'owner': args.owner,
        'owner_slug': resolve_person_slug(args.owner),
        'what': args.what,
        'since': since,
        'sla_hours': args.sla_hours,
        'escalate_to': args.escalate_to or '',
        'escalation_path': args.escalation_path or '',
        'source': source,
        'status': 'open',
        'breached_at': None,
        'last_nudge_at': None,
        'first_seen': time.time(),
        'closed_at': None,
        'notes': '',
    }
    save_state(state)
    print(f'added: {item_id} - waiting on {args.owner} for "{args.what}" (SLA {args.sla_hours}h)')

def prune(state):
    cutoff = time.time() - DROPPED_RETENTION_DAYS * 86400
    dead = [iid for iid, it in state['items'].items()
            if it['status'] in ('answered', 'dropped')
            and (it.get('closed_at') or it['first_seen']) < cutoff]
    for iid in dead:
        del state['items'][iid]
    return len(dead)

def cmd_sweep(args):
    state = load_state()
    t0 = time.time()
    n_breached, n_answered = 0, 0
    token = None
    if args.check_slack:
        token = load_token()

    for it in state['items'].values():
        if it['status'] not in ('open', 'breached'):
            continue
        if args.check_slack and it.get('source', {}).get('permalink'):
            replied, _ = owner_replied_since(token, it['source'], it['owner'], it['since'])
            if replied:
                it.update(status='answered', closed_at=time.time(), notes='auto: owner replied in thread')
                n_answered += 1
                continue
        hours = age_hours(it['since'])
        if hours >= it['sla_hours'] and it['status'] == 'open':
            it['status'] = 'breached'
            it['breached_at'] = time.time()
            n_breached += 1

    n_pruned = prune(state)
    state['last_sweep'] = time.time()
    save_state(state)
    open_items = [i for i in state['items'].values() if i['status'] in ('open', 'breached')]
    breached_now = sum(1 for i in open_items if i['status'] == 'breached')
    summary = (f'sweep done in {time.time()-t0:.0f}s: +{n_breached} newly breached, '
               f'{n_answered} auto-answered, {n_pruned} pruned -> {len(open_items)} open '
               f'({breached_now} breached)')
    print(summary)
    if os.path.exists(HEARTBEAT):
        os.system(f'{sys.executable} {HEARTBEAT} --job waiting-watchdog --status ok '
                  f'--summary "{summary[:200]}" >/dev/null 2>&1')

# ------------------------------------------------------------------ report --

def cmd_report(args):
    state = load_state()
    items = [(iid, it) for iid, it in state['items'].items()
             if args.all or it['status'] in ('open', 'breached')]
    if not items:
        print('No open waiting-on items. Watchdog is clean.')
        return

    breached = [(iid, it) for iid, it in items if it['status'] == 'breached']
    others = [(iid, it) for iid, it in items if it['status'] != 'breached']
    breached.sort(key=lambda x: -age_hours(x[1]['since']))
    others.sort(key=lambda x: age_hours(x[1]['sla_hours']) - age_hours(x[1]['since']))

    print(f'## ⏳ Waiting-on Watchdog ({len(items)})\n')
    for iid, it in breached:
        hours = age_hours(it['since'])
        esc = f' -> {it["escalate_to"]}' if it['escalate_to'] else ''
        path = f' via {it["escalation_path"]}' if it['escalation_path'] else ''
        link = it.get('source', {}).get('permalink')
        linktxt = f' [thread]({link})' if link else ''
        print(f'- 🚨 ESCALATE: **{it["owner"]}** silent **{age_str(hours)}** '
              f'(SLA {it["sla_hours"]}h) on {it["what"]}{esc}{path};{linktxt} {iid}')
    for iid, it in others:
        hours = age_hours(it['since'])
        left = it['sla_hours'] - hours
        status_txt = it['status']
        link = it.get('source', {}).get('permalink')
        linktxt = f' [thread]({link})' if link else ''
        if status_txt in ('open',):
            countdown = f'{age_str(max(left,0))} left of {it["sla_hours"]}h SLA'
        else:
            countdown = status_txt
        print(f'- **{it["owner"]}** on {it["what"]} - {countdown}{linktxt} {iid} [{status_txt}]')

# ------------------------------------------------------------------- mutations --

def cmd_close(args):
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    it.update(status='answered', closed_at=time.time())
    save_state(state)
    print(f'closed: {args.item_id}')

def cmd_drop(args):
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    it.update(status='dropped', closed_at=time.time())
    save_state(state)
    print(f'dropped: {args.item_id}')

def cmd_touch(args):
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    now = time.time()
    it.update(since=now, last_nudge_at=now, status='open', breached_at=None)
    save_state(state)
    print(f'touched (nudge sent, SLA clock reset): {args.item_id}')

# -------------------------------------------------------------------- main --

def main():
    p = argparse.ArgumentParser(description='Waiting-on SLA watchdog')
    sub = p.add_subparsers(dest='cmd')

    ap = sub.add_parser('add')
    ap.add_argument('--owner', required=True)
    ap.add_argument('--what', required=True)
    ap.add_argument('--sla-hours', type=float, required=True)
    ap.add_argument('--escalate-to')
    ap.add_argument('--escalation-path')
    ap.add_argument('--source')
    ap.add_argument('--since', help='epoch seconds; default now')

    sp = sub.add_parser('sweep')
    sp.add_argument('--check-slack', action='store_true')

    rp = sub.add_parser('report')
    rp.add_argument('--all', action='store_true')

    cp = sub.add_parser('close')
    cp.add_argument('item_id')

    dp = sub.add_parser('drop')
    dp.add_argument('item_id')

    tp = sub.add_parser('touch')
    tp.add_argument('item_id')

    args = p.parse_args()
    {'add': cmd_add, 'sweep': cmd_sweep, 'report': cmd_report,
     'close': cmd_close, 'drop': cmd_drop, 'touch': cmd_touch}.get(
        args.cmd or 'sweep', cmd_sweep)(args)

if __name__ == '__main__':
    main()
