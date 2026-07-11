#!/usr/bin/env python3
"""
premeeting_cards.py - Auto-brief cards for upcoming meetings.

Pure mechanical join, NO LLM calls:
  Work calendar (gcal_manager.py list --json) x people.json (attendee resolution,
  best-effort) x MTG-* tickets (tickets.json, token overlap >=2) x fathom_registry
  (participant/title overlap >=2 -> last time we met) x open items from the
  Slack mention ledger, decisions log, commitments ledger, and waiting-on watchdog
  (all keyed to attendees when resolvable).

Design (2026-07-10, per the 8-component harness upgrade plan):
  - Clone of mention_ledger.py conventions: BASE_DIR from __file__, atomic
    load_state/save_state (.tmp + os.replace), argparse subcommands, graceful
    degradation when a sibling ledger file doesn't exist yet (all 8 components
    are being built in parallel).
  - `generate` is idempotent: reruning for the same date overwrites that date's
    cards + state entry (no duplication).
  - KNOWN GAP: gcal_manager.py's `list --json` output does NOT include an
    `attendees` field (verified by reading the connector source), even though
    the harness-upgrade plan assumed it would. This script degrades gracefully:
    attendee slugs are inferred from (a) an `attendees` field IF a future
    connector version adds it, (b) email addresses found in the event
    description, and (c) known-person name/alias substring matches against the
    event summary + description. See SKILL.md "Gotchas".

Subcommands:
  generate [--date YYYY-MM-DD]   build cards for that WIB date (default: today)
  report [--date YYYY-MM-DD]     briefing-ready markdown index of that date's cards

State: journal/state/premeeting.json
Cards: journal/premeeting/<YYYY-MM-DD>/<HHMM>_<slug>.md
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
STATE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'premeeting.json')
CARDS_DIR = os.path.join(BASE_DIR, 'journal', 'premeeting')

PEOPLE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'people.json')
TICKETS_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'tickets.json')
FATHOM_REGISTRY_PATH = os.path.join(BASE_DIR, 'journal', 'fathom_registry.json')
MENTION_LEDGER_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'slack_mention_ledger.json')
DECISIONS_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'decisions.json')
COMMITMENTS_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'commitments.json')
WAITING_ON_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'waiting_on.json')

GCAL_SCRIPT = os.path.join(BASE_DIR, '.agent', 'skills', 'google-calendar-connector', 'gcal_manager.py')
HEARTBEAT_SCRIPT = os.path.join(BASE_DIR, '.agent', 'scripts', 'heartbeat.py')

WIB = datetime.timezone(datetime.timedelta(hours=7))
CARD_RETENTION_DAYS = 14

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'of', 'to', 'for', 'with', 'on', 'in', 'at',
    'prep', 'run', 'weekly', 'call', 'meeting', 'sync', 'review', 'check',
    'follow', 'up', 'followup', 'discussion', 'session', 'catch', 'held',
    'mandatory', 'rsvp', '1:1', 'walkthrough', 'is', 'are', 'we', 'i', 'our',
}

# ------------------------------------------------------------------ helpers --

def slugify(name):
    s = (name or '').strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

def tokens(text):
    words = re.findall(r'[a-z0-9]+', (text or '').lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f'WARN: failed to parse {path}: {e}', file=sys.stderr)
            return default
    return default

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {'dates': {}, 'last_run': None}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)

def wib_now():
    return datetime.datetime.now(WIB)

def parse_event_dt(value):
    """Parse a Google Calendar start/end string (dateTime or all-day date) to
    an aware datetime in WIB."""
    if not value:
        return None
    try:
        if 'T' in value:
            dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.astimezone(WIB)
        dt = datetime.datetime.strptime(value, '%Y-%m-%d')
        return dt.replace(tzinfo=WIB)
    except Exception:
        return None

# ------------------------------------------------------------- data sources --

def fetch_calendar_events():
    """timeout-wrapped gcal_manager.py list --json (Work profile), per spec.
    Tolerates connector auth failure / missing token -> empty list, no crash."""
    cmd = ['timeout', '180s', sys.executable, GCAL_SCRIPT, 'list',
           '--days-back', '0', '--days-forward', '1', '--profile', 'work', '--json']
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=190)
    except Exception as e:
        print(f'WARN: calendar fetch failed: {e}', file=sys.stderr)
        return []
    if out.returncode != 0:
        print(f'WARN: gcal_manager exit {out.returncode}: {out.stderr[:300]}', file=sys.stderr)
    # stdout may have a status line ahead of the JSON array; find the array.
    text = out.stdout.strip()
    idx = text.find('[')
    if idx == -1:
        return []
    try:
        return json.loads(text[idx:])
    except Exception as e:
        print(f'WARN: could not parse calendar JSON: {e}', file=sys.stderr)
        return []

def load_people():
    """journal/state/people.json is owned by the stakeholders component (5).
    Read-with-fallback: empty dict if it doesn't exist yet."""
    data = load_json(PEOPLE_PATH, {})
    return data.get('people', {}) if isinstance(data, dict) else {}

def load_tickets():
    data = load_json(TICKETS_PATH, {})
    return data.get('tickets', []) if isinstance(data, dict) else []

def load_fathom_registry():
    data = load_json(FATHOM_REGISTRY_PATH, {})
    return data if isinstance(data, dict) else {}

def load_mention_ledger():
    data = load_json(MENTION_LEDGER_PATH, {})
    return data.get('items', {}) if isinstance(data, dict) else {}

def load_decisions():
    data = load_json(DECISIONS_PATH, {})
    return data.get('items', {}) if isinstance(data, dict) else {}

def load_commitments():
    data = load_json(COMMITMENTS_PATH, {})
    return data.get('items', {}) if isinstance(data, dict) else {}

def load_waiting_on():
    data = load_json(WAITING_ON_PATH, {})
    return data.get('items', {}) if isinstance(data, dict) else {}

# ------------------------------------------------------------- attendee join --

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

def resolve_attendees(event, people):
    """Best-effort attendee -> people-slug resolution. Degrades gracefully:
    the calendar connector currently does not return an `attendees` field, so
    most of the signal comes from emails in the description and name/alias
    hits in the summary+description text."""
    slugs = set()
    names_seen = set()

    # (a) native attendees field, if a future connector version provides it
    for att in event.get('attendees') or []:
        email = (att.get('email') or '').lower()
        disp = att.get('displayName') or ''
        for slug, person in people.items():
            if email and email in [e.lower() for e in person.get('emails', [])]:
                slugs.add(slug)
            elif disp and disp.lower() == person.get('name', '').lower():
                slugs.add(slug)
        if disp:
            names_seen.add(disp)

    haystack = f"{event.get('summary', '')} {event.get('description', '')}"
    haystack_l = haystack.lower()

    # (b) emails embedded in the description (invite text often lists them)
    found_emails = {m.lower() for m in EMAIL_RE.findall(haystack)}
    for slug, person in people.items():
        if found_emails & {e.lower() for e in person.get('emails', [])}:
            slugs.add(slug)

    # (c) name/alias substring match against summary+description
    for slug, person in people.items():
        candidates = [person.get('name', '')] + person.get('aliases', [])
        for cand in candidates:
            cand = (cand or '').strip()
            if len(cand) >= 3 and cand.lower() in haystack_l:
                slugs.add(slug)
                break

    return slugs

# ------------------------------------------------------------- ticket join --

def related_tickets(event, tickets):
    """MTG-* tickets whose title shares >=2 significant tokens with the event
    summary."""
    ev_tokens = tokens(event.get('summary', ''))
    if not ev_tokens:
        return []
    hits = []
    for t in tickets:
        if not str(t.get('id', '')).startswith('MTG-'):
            continue
        t_tokens = tokens(t.get('title', ''))
        overlap = ev_tokens & t_tokens
        if len(overlap) >= 2:
            hits.append((len(overlap), t))
    hits.sort(key=lambda x: -x[0])
    return [t for _, t in hits]

# ------------------------------------------------------------- fathom join --

def last_time_we_met(event, people, attendee_slugs, registry):
    """Best-effort 'last meeting with these people' lookup: prefer participant
    name overlap (>=2 tokens against attendee full names), fall back to a
    title-token overlap against the event summary (>=2) when attendees could
    not be resolved -- both degrade to 'no match' rather than crash."""
    ev_tokens = tokens(event.get('summary', ''))
    attendee_names = set()
    for slug in attendee_slugs:
        person = people.get(slug, {})
        if person.get('name'):
            attendee_names.add(person['name'].lower())

    best = None
    best_score = 0
    for rec in registry.values():
        participants = {p.lower() for p in rec.get('participants', [])}
        score = 0
        if attendee_names:
            # token overlap between attendee full names and participant names
            for name in attendee_names:
                name_tokens = tokens(name)
                for p in participants:
                    if name_tokens & tokens(p):
                        score += 2
        title_tokens = tokens(rec.get('matched_meeting') or rec.get('raw_title') or '')
        score += len(ev_tokens & title_tokens)
        if score >= 2 and score > best_score:
            best_score = score
            best = rec
    return best

# --------------------------------------------------------------- card build --

def build_card(event, people, tickets, registry, mention_items, decisions,
                commitments, waiting_items):
    start_dt = parse_event_dt(event.get('start'))
    time_wib = start_dt.strftime('%H:%M') if start_dt else '--:--'
    title = event.get('summary', '(No title)')

    attendee_slugs = resolve_attendees(event, people)
    attendees = [people[s] for s in attendee_slugs if s in people]

    fathom_hit = last_time_we_met(event, people, attendee_slugs, registry)

    slack_ids = {p.get('slack_id') for p in attendees if p.get('slack_id')}
    pings = [it for it in mention_items.values()
             if it.get('status') == 'open' and it.get('author') in slack_ids]

    open_decisions = [d for d in decisions.values()
                       if d.get('status') == 'open'
                       and (set(d.get('stakeholder_slugs', [])) & attendee_slugs)]

    you_owe_them = [c for c in commitments.values()
                     if c.get('status') == 'open' and c.get('to_slug') in attendee_slugs]

    they_owe_you = [w for w in waiting_items.values()
                      if w.get('status') in ('open', 'breached')
                      and w.get('owner_slug') in attendee_slugs]

    tix = related_tickets(event, tickets)

    lines = []
    lines.append(f'# {time_wib} WIB — {title}')
    lines.append('')
    lines.append('## Attendees')
    if attendees:
        for p in attendees:
            role = f" ({p.get('role')})" if p.get('role') else ''
            lines.append(f"- {p.get('name', '(unknown)')}{role}")
    else:
        lines.append('- (not resolvable from calendar payload — see SKILL.md gap note)')
    lines.append('')

    lines.append('## Last time we met')
    if fathom_hit:
        title_str = fathom_hit.get('matched_meeting') or fathom_hit.get('raw_title') or '(untitled)'
        lines.append(f"- {fathom_hit.get('date_wib', '?')} — {title_str} "
                      f"([Fathom]({fathom_hit.get('fathom_url', '')}))")
    else:
        lines.append('- No prior meeting matched.')
    lines.append('')

    lines.append('## You owe them')
    if you_owe_them:
        for c in you_owe_them:
            due = f" (due {c.get('due')})" if c.get('due') else ''
            lines.append(f"- {c.get('text', '(no text)')}{due} `{c.get('id')}`")
    else:
        lines.append('- Nothing open.')
    lines.append('')

    lines.append('## They owe you')
    if they_owe_you:
        for w in they_owe_you:
            flag = '🚨 ' if w.get('status') == 'breached' else ''
            lines.append(f"- {flag}{w.get('what', '(no detail)')} (since {w.get('since', '?')}) `{w.get('id')}`")
    else:
        lines.append('- Nothing open.')
    lines.append('')

    lines.append('## Open decisions')
    if open_decisions:
        for d in open_decisions:
            deadline = f" (deadline {d.get('deadline')})" if d.get('deadline') else ''
            lines.append(f"- {d.get('title', '(untitled)')}{deadline} `{d.get('id')}`")
    else:
        lines.append('- None open.')
    lines.append('')

    lines.append('## Unanswered pings')
    if pings:
        for it in pings:
            text = re.sub(r'\s+', ' ', it.get('text', ''))[:160]
            lines.append(f"- {it.get('channel_name', '?')} — {text}")
    else:
        lines.append('- None.')
    lines.append('')

    lines.append('## Related tickets')
    if tix:
        for t in tix:
            lines.append(f"- {t.get('id')} — {t.get('title')} [{t.get('status')}]")
    else:
        lines.append('- None matched.')
    lines.append('')

    return '\n'.join(lines), {
        'title': title, 'time_wib': time_wib,
        'attendee_slugs': sorted(attendee_slugs),
        'n_decisions': len(open_decisions), 'n_pings': len(pings),
        'n_you_owe': len(you_owe_them), 'n_they_owe': len(they_owe_you),
        'n_tickets': len(tix), 'has_last_meeting': bool(fathom_hit),
    }

# --------------------------------------------------------------------- prune --

def heartbeat(job, status, summary):
    try:
        subprocess.run([sys.executable, HEARTBEAT_SCRIPT, '--job', job, '--status', status,
                        '--summary', summary], capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f'  ! heartbeat failed (non-fatal): {e}', file=sys.stderr)

def prune_old_cards():
    if not os.path.isdir(CARDS_DIR):
        return
    cutoff = (wib_now() - datetime.timedelta(days=CARD_RETENTION_DAYS)).strftime('%Y-%m-%d')
    for name in os.listdir(CARDS_DIR):
        path = os.path.join(CARDS_DIR, name)
        if not os.path.isdir(path):
            continue
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', name) and name < cutoff:
            for f in os.listdir(path):
                try:
                    os.remove(os.path.join(path, f))
                except OSError:
                    pass
            try:
                os.rmdir(path)
            except OSError:
                pass

# -------------------------------------------------------------------- main --

def cmd_generate(args):
    target_date = args.date or wib_now().strftime('%Y-%m-%d')
    try:
        events = fetch_calendar_events()
        people = load_people()
        tickets = load_tickets()
        registry = load_fathom_registry()
        mention_items = load_mention_ledger()
        decisions = load_decisions()
        commitments = load_commitments()
        waiting_items = load_waiting_on()

        day_events = []
        for ev in events:
            dt = parse_event_dt(ev.get('start'))
            if dt and dt.strftime('%Y-%m-%d') == target_date:
                day_events.append((dt, ev))
        day_events.sort(key=lambda x: x[0])

        day_dir = os.path.join(CARDS_DIR, target_date)
        os.makedirs(day_dir, exist_ok=True)
        # idempotent regen: clear any existing cards for this date before rewriting
        for f in os.listdir(day_dir):
            if f.endswith('.md'):
                try:
                    os.remove(os.path.join(day_dir, f))
                except OSError:
                    pass

        written = []
        for dt, ev in day_events:
            slug = slugify(ev.get('summary', 'meeting'))[:40] or 'meeting'
            fname = f"{dt.strftime('%H%M')}_{slug}.md"
            content, meta = build_card(ev, people, tickets, registry, mention_items,
                                        decisions, commitments, waiting_items)
            fpath = os.path.join(day_dir, fname)
            tmp = fpath + '.tmp'
            with open(tmp, 'w') as f:
                f.write(content)
            os.replace(tmp, fpath)
            written.append({'file': os.path.join('journal', 'premeeting', target_date, fname), **meta})

        state = load_state()
        state['dates'][target_date] = {'generated_at': time.time(), 'cards': written}
        state['last_run'] = time.time()
        save_state(state)

        prune_old_cards()

        print(f'generated {len(written)} card(s) for {target_date} -> {day_dir}')
        for w in written:
            print(f"  - {w['time_wib']} {w['title']} ({w['file']})")
        heartbeat('premeeting-cards', 'ok', f'{len(written)} cards for {target_date}')
        return written
    except Exception as e:
        heartbeat('premeeting-cards', 'fail', str(e)[:280])
        raise

def cmd_report(args):
    target_date = args.date or wib_now().strftime('%Y-%m-%d')
    state = load_state()
    entry = state.get('dates', {}).get(target_date)
    if not entry or not entry.get('cards'):
        print(f'No pre-meeting cards for {target_date}. Run `generate` first.')
        return
    print(f'## 📋 Pre-meeting cards — {target_date} ({len(entry["cards"])})\n')
    for c in entry['cards']:
        flags = []
        if c.get('n_decisions'):
            flags.append(f"{c['n_decisions']} open decision(s)")
        if c.get('n_pings'):
            flags.append(f"{c['n_pings']} unanswered ping(s)")
        if c.get('n_you_owe'):
            flags.append(f"{c['n_you_owe']} you owe")
        if c.get('n_they_owe'):
            flags.append(f"{c['n_they_owe']} they owe")
        if c.get('n_tickets'):
            flags.append(f"{c['n_tickets']} related ticket(s)")
        flag_str = f" — {', '.join(flags)}" if flags else ''
        attendees_str = ', '.join(c.get('attendee_slugs', [])) or 'unresolved attendees'
        print(f"- **{c['time_wib']}** {c['title']} ({attendees_str}){flag_str} — [{c['file']}]({c['file']})")

def main():
    p = argparse.ArgumentParser(description='Pre-meeting brief cards (mechanical join, no LLM)')
    sub = p.add_subparsers(dest='cmd')
    gp = sub.add_parser('generate')
    gp.add_argument('--date', help='YYYY-MM-DD (default: today WIB)')
    rp = sub.add_parser('report')
    rp.add_argument('--date', help='YYYY-MM-DD (default: today WIB)')
    args = p.parse_args()
    {'generate': cmd_generate, 'report': cmd_report}.get(args.cmd or 'generate', cmd_generate)(args)

if __name__ == '__main__':
    main()
