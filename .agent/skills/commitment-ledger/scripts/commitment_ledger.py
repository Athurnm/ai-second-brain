#!/usr/bin/env python3
"""
commitment_ledger.py - Outbound commitments ledger: things You said he'd do,
tracked from "I'll ..." until actually delivered. Clones the mention_ledger.py
3-layer pattern (see .agent/skills/slack-tracker/scripts/mention_ledger.py):

  Layer 1 (this script, pure Python, cron 3x/day): collect candidates + Fathom
           action items assigned to You (mechanical, high confidence) +
           mechanical thread auto-close.
  Layer 2 (GLM via agy-bridge --task harvest, `extract`): turn cheap-filtered
           Slack "I'll ..." message candidates into structured commitments.
           GLM only extracts/classifies - it never decides open/closed.
  Layer 3 (Claude, morning/evening update): `report` emits briefing-ready
           markdown, embedded verbatim.

Sources:
  1. Fathom - action items assigned to You in recently-synced meetings
     (journal/fathom_registry.json) -> high-confidence items, no LLM needed.
  2. Slack sent messages - search.messages from:<@BRIAN_ID> since watermark,
     cheap regex filter for commitment language -> pending_candidates (NOT
     turned into items during sweep; `extract` does that via agy-bridge).
  3. Auto-close - conversations.replies on a candidate's thread: You later
     posts a completion word or a Drive/Docs link -> closed_by: auto_thread.

State: journal/state/commitments.json
Auth: SLACK_USER_TOKEN from .agent/skills/slack-connector/token.env (xoxp).

Subcommands: sweep (cron default) / extract / add / close / drop / link / unlink / report
"""

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
STATE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'commitments.json')
TOKEN_ENV = os.path.join(BASE_DIR, '.agent', 'skills', 'slack-connector', 'token.env')
AGY_BRIDGE = os.path.join(BASE_DIR, '.agent', 'skills', 'agy-bridge', 'run.py')
FATHOM_CLIENT = os.path.join(BASE_DIR, '.agent', 'skills', 'fathom-connector', 'scripts', 'fathom_client.py')
FATHOM_REGISTRY = os.path.join(BASE_DIR, 'journal', 'fathom_registry.json')
HEARTBEAT = os.path.join(BASE_DIR, '.agent', 'scripts', 'heartbeat.py')
PEOPLE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'people.json')

# Local meeting artifacts (verified against meeting-recorder/watcher.py constants
# 2026-07-11, do not guess): TRANSCRIPTS_DIR = raw local/vexa transcripts,
# MOM_DIR = where the watcher drops MOM drafts (also where /mom saves finals).
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, 'Clients', 'Work', 'meetings', 'transcripts')
MOM_DIR = os.path.join(BASE_DIR, 'Clients', 'Work', 'meetings')
CLIENTS_MEETINGS_GLOB = os.path.join(BASE_DIR, 'Clients', '*', 'meetings', '*.md')

BRIAN_ID_DEFAULT = '<SLACK_ID>'           # verified via auth.test 2026-07-09
BRIAN_EMAIL = 'you@example.com'
BRIAN_NAME_TOKENS = ('brian arfi', 'brian faridhi')   # substring match, case-insensitive

FIRST_RUN_SLACK_LOOKBACK_DAYS = 3          # per spec: bounded first-run lookback
FIRST_RUN_FATHOM_LOOKBACK_DAYS = 3
FIRST_RUN_LOCAL_LOOKBACK_DAYS = 3
CLOSED_RETENTION_DAYS = 14                 # prune done/dropped after this
API_PAUSE = 0.15                           # pacing between Slack calls
FATHOM_LIST_LIMIT = 20                     # bounded: fathom --action list --full page size
MIN_CAPTURE_WORDS = 4                      # noise guard: drop sub-4-word captures

WIB_OFFSET_HOURS = 7

# Cheap mechanical filter for "this Slack message probably makes a commitment".
# Deliberately permissive (extract's LLM pass does the real judgment) but bounded
# so pending_candidates doesn't fill up with noise every sweep.
COMMIT_RE = re.compile(
    r"\b(i'?ll|i will|i'?m going to|i am going to|will send|will share|will follow up|"
    r"will get back|will update|will check|will look into|will circle back|"
    r"let me (send|share|check|get|pull|follow up|dig)|i owe you|i can (send|share|get))\b",
    re.IGNORECASE,
)

# Mechanical auto-close signal: You's own later message in the thread contains
# a completion word, or a Drive/Docs link (the deliverable itself).
CLOSE_WORD_RE = re.compile(
    r"\b(done|sent|shared|submitted|delivered|resolved|completed|finished|"
    r"posted|uploaded|updated the doc|here you go|attached)\b", re.IGNORECASE,
)
DRIVE_LINK_RE = re.compile(r"(docs\.google\.com|drive\.google\.com)")

# Mechanical spoken-cue detector for local transcripts/MOM drafts: You says one
# of these phrases mid-meeting to flag "this is my action item" -> capture
# everything after the cue to end of line. re.MULTILINE so `$` anchors per line
# when run against a whole file's text via finditer (not just end of string).
CUE_RE = re.compile(
    r"(?:ini\s+action\s+item\s+(?:gw|gue|saya)|action\s+item\s+(?:gw|gue|saya)\b|"
    r"note[:,]?\s*action\s+item|my\s+action\s+item)\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)

# MOM "Action Items" section detector (mechanical, heading-level aware so a
# nested subheading like "### Work Team" doesn't prematurely end the section -
# only a heading at the SAME or SHALLOWER level than the Action Items heading
# closes it). Matches "## Action Items", "## 3. Action Items", "## ✅ Action
# Items", etc. - decorations before the words are stripped, not matched literally.
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
ACTION_ITEMS_TEXT_RE = re.compile(r'^[\d.\s]*[^\w]*action\s+items?\b', re.IGNORECASE)
BRIAN_OWNER_RE = re.compile(r'\bBrian\b', re.IGNORECASE)

# ------------------------------------------------------------------- state --

def default_state():
    return {
        'next_seq': 1,
        'items': {},
        'slack_search_watermark': 0.0,
        'local_watermark': 0.0,
        'processed_fathom_ids': [],
        'processed_sources': {},        # dedupe map: source-key -> True
        'pending_candidates': [],
        'user_names': {},
        'last_sweep': None,
    }

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
        for k, v in default_state().items():
            state.setdefault(k, v)
        return state
    return default_state()

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)

def slugify(name):
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower()).strip('-')
    return s or 'unknown'

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

def next_id(state):
    seq = state.get('next_seq', 1)
    state['next_seq'] = seq + 1
    return f'COM-{seq:04d}'

def wib_today():
    return (datetime.now(timezone.utc) + timedelta(hours=WIB_OFFSET_HOURS)).date()

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

def thread_ts_from_permalink(permalink):
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(permalink).query)
        return q.get('thread_ts', [None])[0]
    except Exception:
        return None

def resolve_names(state, user_ids, token):
    cache = state.setdefault('user_names', {})
    missing = [u for u in user_ids if u and u.startswith('U') and u not in cache]
    for uid in missing:
        resp = slack('users.info', token, {'user': uid})
        prof = resp.get('user', {}) if resp.get('ok') else {}
        cache[uid] = prof.get('real_name') or prof.get('name') or uid
        time.sleep(API_PAUSE)
    if missing:
        save_state(state)
    return cache

# --------------------------------------------------------------- item ops --

def create_item(state, text, to='', channel=None, channel_name=None, thread_ts=None,
                 permalink='', due=None, project=None, source_type='manual',
                 source_ref='', confidence='medium', priority=None, notes=None):
    iid = next_id(state)
    if priority is None:
        priority = 'YourManager' in (to or '').lower()
    state['items'][iid] = {
        'id': iid, 'text': (text or '')[:600], 'to': to or '',
        'to_slug': resolve_person_slug(to) if to else '',
        'channel': channel, 'channel_name': channel_name,
        'thread_ts': thread_ts, 'permalink': permalink or '',
        'due': due, 'project': project,
        'source': {'type': source_type, 'ref': source_ref or ''},
        'status': 'open', 'confidence': confidence,
        'first_seen': time.time(), 'closed_at': None, 'closed_by': None,
        'priority': bool(priority), 'notes': notes or [],
    }
    return state['items'][iid]

# ------------------------------------------------------------- Fathom sweep --

def fathom_list_full(limit):
    try:
        out = subprocess.run(
            [sys.executable, FATHOM_CLIENT, '--action', 'list', '--full', '--limit', str(limit)],
            capture_output=True, text=True, timeout=170)
    except subprocess.TimeoutExpired:
        print('  ! fathom_client.py list timed out', file=sys.stderr)
        return []
    try:
        return json.loads(out.stdout)
    except Exception:
        print(f'  ! fathom_client.py list: unparseable output: {out.stdout[:200]}', file=sys.stderr)
        return []

def load_fathom_registry():
    if not os.path.exists(FATHOM_REGISTRY):
        return {}
    with open(FATHOM_REGISTRY) as f:
        return json.load(f)

def is_brian_assignee(assignee):
    if not isinstance(assignee, dict):
        return False
    email = (assignee.get('email') or '').strip().lower()
    name = (assignee.get('name') or '').strip().lower()
    if email == BRIAN_EMAIL:
        return True
    return any(tok in name for tok in BRIAN_NAME_TOKENS)

def sweep_fathom(state):
    """Registry entries not yet processed -> fathom_client.py --action list --full
    (NOT `get` - confirmed 404 on this deployment's recording IDs 2026-07-10;
    `list --full` DOES carry action_items per meeting, see integration_notes) ->
    action items assigned to You, not yet completed -> high-confidence items."""
    registry = load_fathom_registry()
    processed = set(state.get('processed_fathom_ids', []))
    cutoff = (wib_today() - timedelta(days=FIRST_RUN_FATHOM_LOOKBACK_DAYS)).isoformat()
    unprocessed_recent = [
        rid for rid, meta in registry.items()
        if rid not in processed and isinstance(meta, dict)
        and (meta.get('date_wib') or '') >= cutoff
    ]
    if not unprocessed_recent and processed:
        return 0   # nothing new since last sweep, don't burn a Fathom API call
    limit = max(10, min(FATHOM_LIST_LIMIT, len(unprocessed_recent) + 5)) if unprocessed_recent else 10
    meetings = fathom_list_full(limit)
    new_items = 0
    for m in meetings:
        rid = str(m.get('recording_id') or '')
        if not rid or rid not in registry or rid in processed:
            continue
        processed.add(rid)
        reg_meta = registry.get(rid, {})
        for idx, ai in enumerate(m.get('action_items') or []):
            if ai.get('completed'):
                continue
            if not is_brian_assignee(ai.get('assignee')):
                continue
            key = f'fathom:{rid}:{idx}'
            if key in state['processed_sources']:
                continue
            state['processed_sources'][key] = True
            create_item(
                state, text=ai.get('description', ''), to='',
                permalink=ai.get('recording_playback_url', ''),
                project=reg_meta.get('project'),
                source_type='fathom',
                source_ref=m.get('url') or reg_meta.get('fathom_url', ''),
                confidence='high',
            )
            new_items += 1
    state['processed_fathom_ids'] = sorted(processed)
    return new_items

# -------------------------------------------------------------- Slack sweep --

def sweep_slack_candidates(token, state, brian_id):
    """search.messages from:<@brian_id> since watermark -> cheap regex filter ->
    pending_candidates. Extraction into real items happens in `extract`, not here."""
    wm = float(state.get('slack_search_watermark') or 0)
    if wm == 0:
        wm = time.time() - FIRST_RUN_SLACK_LOOKBACK_DAYS * 86400
    newest = wm
    page, found = 1, 0
    while page <= 5:                       # bounded: a few pages max
        resp = slack('search.messages', token, {
            'query': f'from:<@{brian_id}>', 'sort': 'timestamp', 'sort_dir': 'desc',
            'count': 20, 'page': page})
        if not resp.get('ok'):
            print(f'  ! search.messages: {resp.get("error")}', file=sys.stderr)
            break
        matches = resp.get('messages', {}).get('matches', [])
        if not matches:
            break
        stop = False
        for m in matches:
            ts = float(m.get('ts', 0))
            if ts <= wm:
                stop = True
                break
            newest = max(newest, ts)
            text = m.get('text', '')
            if not COMMIT_RE.search(text):
                continue
            ch = m.get('channel', {})
            key = f"slack:{ch.get('id', '?')}:{m.get('ts')}"
            if key in state['processed_sources']:
                continue
            state['processed_sources'][key] = True
            permalink = m.get('permalink', '')
            state['pending_candidates'].append({
                'ts': m.get('ts'), 'channel': ch.get('id', '?'),
                'channel_name': ch.get('name', '?'), 'text': text[:500],
                'permalink': permalink,
                'thread_ts': thread_ts_from_permalink(permalink),
                'added_at': time.time(),
            })
            found += 1
        pages_total = resp.get('messages', {}).get('paging', {}).get('pages', 1)
        if stop or page >= pages_total:
            break
        page += 1
        time.sleep(API_PAUSE)
    state['slack_search_watermark'] = newest
    return found

# -------------------------------------------------------------- local sweep --

def local_meeting_files():
    """Every local artifact eligible for the cue/owner scan: TRANSCRIPTS_DIR
    (raw local/vexa transcripts), MOM_DIR (Work MOM drafts - same dir the
    watcher + /mom write to), and Clients/*/meetings/*.md (any client's meeting
    notes/MOM, current + future). MOM_DIR already matches the glob pattern;
    a set dedupes the overlap. .md only, per spec (the .txt raw whisper
    sidecars in TRANSCRIPTS_DIR are not scanned)."""
    paths = set()
    for d in (TRANSCRIPTS_DIR, MOM_DIR):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.lower().endswith('.md'):
                    paths.add(os.path.join(d, fn))
    for p in glob.glob(CLIENTS_MEETINGS_GLOB):
        paths.add(p)
    return sorted(paths)

def _heading_text_is_action_items(text):
    return bool(ACTION_ITEMS_TEXT_RE.match(text.strip()))

def extract_mom_action_lines(text):
    """Within each 'Action Items' heading's section (bounded by the next
    heading at the SAME or SHALLOWER level - a deeper subheading like
    '### Work Team' stays inside the section), return every raw line that
    names You as owner (`\\bBrian\\b`, word-boundary - table row, checkbox
    bullet, or plain line, whatever format that MOM happens to use)."""
    lines = text.splitlines()
    n = len(lines)
    out = []
    i = 0
    while i < n:
        hm = HEADING_RE.match(lines[i])
        if hm and _heading_text_is_action_items(hm.group(2)):
            level = len(hm.group(1))
            j = i + 1
            while j < n:
                hm2 = HEADING_RE.match(lines[j])
                if hm2 and len(hm2.group(1)) <= level:
                    break
                j += 1
            for line in lines[i + 1:j]:
                if BRIAN_OWNER_RE.search(line):
                    out.append(line)
            i = j
        else:
            i += 1
    return out

def clean_mom_line(line):
    """Strip markdown table/checkbox/bold decoration from a MOM Action Items
    line so the captured commitment text reads as prose, not raw markdown."""
    s = line.strip()
    s = re.sub(r'^-\s*\[[ xX]\]\s*', '', s)     # checkbox bullet
    s = re.sub(r'^\|\s*', '', s)                 # leading table pipe
    s = re.sub(r'\s*\|\s*$', '', s)              # trailing table pipe
    s = s.replace('|', ' - ')                    # inner table pipes -> separator
    s = s.replace('**', '')                      # bold markers
    return re.sub(r'\s+', ' ', s).strip()

def sweep_local(state):
    """Mechanical, no-LLM: scan local transcripts + MOM drafts for (1) You's
    spoken action-item cues (CUE_RE) and (2) MOM 'Action Items' section rows
    that name You as owner. Only files touched since `local_watermark`
    (first run: 3-day lookback, matching the Fathom/Slack sources). Dedupe is
    per-line via a content hash so re-touching a file (e.g. a later /mom edit)
    only picks up genuinely new lines."""
    wm = float(state.get('local_watermark') or 0)
    if wm == 0:
        wm = time.time() - FIRST_RUN_LOCAL_LOOKBACK_DAYS * 86400
    newest = wm
    new_items = 0
    for path in local_meeting_files():
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime <= wm:
            continue
        newest = max(newest, mtime)
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except Exception:
            continue
        relpath = os.path.relpath(path, BASE_DIR)

        candidates = []   # (raw_line_for_hash, captured_text)
        for m in CUE_RE.finditer(text):
            captured = re.sub(r'^[:\-]+\s*', '', m.group(1).strip())
            if len(captured.split()) < MIN_CAPTURE_WORDS:
                continue
            line_start = text.rfind('\n', 0, m.start()) + 1
            line_end = text.find('\n', m.end())
            if line_end == -1:
                line_end = len(text)
            candidates.append((text[line_start:line_end], captured[:300]))

        for raw_line in extract_mom_action_lines(text):
            cleaned = clean_mom_line(raw_line)
            if len(cleaned.split()) < MIN_CAPTURE_WORDS:
                continue
            candidates.append((raw_line, cleaned[:300]))

        for raw_line, captured in candidates:
            line_hash = hashlib.sha1(raw_line.encode('utf-8', 'replace')).hexdigest()[:12]
            key = f'local:{relpath}:{line_hash}'
            if key in state['processed_sources']:
                continue
            state['processed_sources'][key] = True
            create_item(
                state, text=captured, to='',
                permalink=relpath, source_type='meeting-local',
                source_ref=relpath, confidence='high',
            )
            new_items += 1
    state['local_watermark'] = newest
    return new_items

# --------------------------------------------------------------- auto-close --

def sweep_auto_close(token, state):
    """Mechanical only: for open items with a channel+thread_ts, check if You
    posted a later message containing a completion word or a Drive/Docs link."""
    closed = 0
    for it in state['items'].values():
        if it['status'] != 'open' or not it.get('channel') or not it.get('thread_ts'):
            continue
        resp = slack('conversations.replies', token,
                     {'channel': it['channel'], 'ts': it['thread_ts'], 'limit': 100})
        time.sleep(API_PAUSE)
        if not resp.get('ok'):
            continue
        anchor_ts = float(it.get('ts') or it['thread_ts'])
        for msg in resp.get('messages', []):
            if msg.get('user') != BRIAN_ID_DEFAULT:
                continue
            if float(msg.get('ts', 0)) <= anchor_ts:
                continue
            text = msg.get('text', '')
            if CLOSE_WORD_RE.search(text) or DRIVE_LINK_RE.search(text):
                it.update(status='done', closed_at=time.time(), closed_by='auto_thread')
                closed += 1
                break
    return closed

def heartbeat(job, status, summary):
    try:
        subprocess.run([sys.executable, HEARTBEAT, '--job', job, '--status', status,
                        '--summary', summary], capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f'  ! heartbeat failed (non-fatal): {e}', file=sys.stderr)

def prune(state):
    cutoff = time.time() - CLOSED_RETENTION_DAYS * 86400
    dead = [iid for iid, it in state['items'].items()
            if it['status'] in ('done', 'dropped')
            and (it.get('closed_at') or it['first_seen']) < cutoff]
    for iid in dead:
        del state['items'][iid]
    # bound pending_candidates growth: drop anything extract should have consumed
    # long ago (>14d unconsumed = stale, likely superseded)
    cand_cutoff = time.time() - CLOSED_RETENTION_DAYS * 86400
    state['pending_candidates'] = [c for c in state['pending_candidates']
                                   if c.get('added_at', 0) >= cand_cutoff]
    return len(dead)

# -------------------------------------------------------------------- sweep --

def cmd_sweep(args):
    try:
        token = load_token()
        auth = slack('auth.test', token)
        brian_id = auth.get('user_id') or BRIAN_ID_DEFAULT
        state = load_state()
        t0 = time.time()
        n_fathom = sweep_fathom(state)
        n_cand = sweep_slack_candidates(token, state, brian_id)
        n_local = sweep_local(state)
        n_closed = sweep_auto_close(token, state)
        n_pruned = prune(state)
        state['last_sweep'] = time.time()
        save_state(state)
        open_items = [i for i in state['items'].values() if i['status'] == 'open']
        summary = (f'+{n_fathom} fathom, +{n_cand} slack candidates, +{n_local} local-meeting, '
                   f'{n_closed} auto-closed, {n_pruned} pruned -> {len(open_items)} OPEN')
        print(f'sweep done in {time.time()-t0:.0f}s: {summary}, '
              f'{len(state["pending_candidates"])} pending extraction')
        heartbeat('commitment-ledger', 'ok', summary)
    except SystemExit:
        raise
    except Exception as e:
        heartbeat('commitment-ledger', 'fail', str(e)[:280])
        raise

# ------------------------------------------------------------------ extract --

def cmd_extract(args):
    """Batch pending_candidates through GLM (agy-bridge harvest). GLM only
    extracts structure (to/due/is_commitment) - it never decides open/closed."""
    state = load_state()
    candidates = state.get('pending_candidates', [])
    if not candidates:
        print('no pending candidates, nothing to extract')
        return
    batch = candidates[:args.limit]
    prompt = (
        'You are a mechanical outbound-commitment extractor for You (Work PM). '
        'Each line below is a Slack message You SENT. For EACH line, output ONE JSON '
        'line: {"ts":"<ts>", "is_commitment": true|false, "to": "<name You is '
        'committing to, or empty>", "due": "<YYYY-MM-DD or null>", "text": "<short '
        'restatement of what You committed to do, max 20 words>"}. '
        'is_commitment=true ONLY if You is promising a future action to someone '
        '(e.g. "I\'ll send you the PRD tomorrow"). Questions, acknowledgments, and '
        'statements about the past are is_commitment=false. Output ONLY JSON lines, no prose.\n\n'
        + '\n'.join(json.dumps({'ts': c['ts'], 'channel': c['channel_name'],
                                'text': c['text']}, ensure_ascii=False) for c in batch)
    )
    tmp_dir = os.path.join(BASE_DIR, 'journal', 'state')
    prompt_path = os.path.join(tmp_dir, 'commitment_extract_prompt.txt')
    with open(prompt_path, 'w') as f:
        f.write(prompt)
    out = subprocess.run([sys.executable, AGY_BRIDGE, '--task', 'harvest',
                          '--prompt-file', prompt_path, '--timeout', '180'],
                         capture_output=True, text=True)
    if out.returncode == 3:
        print('FALLBACK_TO_CLAUDE: agy-bridge exhausted its chain; '
              f'{len(batch)} candidates left pending for Claude to extract manually.')
        print(out.stdout.strip())
        return   # rc 3 is NOT a failure - candidates stay pending, exit 0
    if out.returncode != 0 or not out.stdout.strip():
        print(f'extract failed (rc={out.returncode}); candidates kept for retry.\n'
              f'{out.stderr[:500]}', file=sys.stderr)
        sys.exit(1)
    created, by_ts = 0, {c['ts']: c for c in batch}
    consumed_ts = set()
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts = row.get('ts')
        cand = by_ts.get(ts)
        if not cand:
            continue
        consumed_ts.add(ts)
        if not row.get('is_commitment'):
            continue
        create_item(
            state, text=row.get('text') or cand['text'], to=row.get('to', '') or '',
            channel=cand['channel'], channel_name=cand['channel_name'],
            thread_ts=cand.get('thread_ts'), permalink=cand.get('permalink', ''),
            due=row.get('due') or None, source_type='slack',
            source_ref=cand.get('permalink', ''), confidence='medium',
        )
        created += 1
    # remove consumed candidates (matched by the LLM, whether or not they became
    # a commitment); anything the LLM silently dropped stays pending for next run
    state['pending_candidates'] = [c for c in state['pending_candidates']
                                    if c['ts'] not in consumed_ts]
    save_state(state)
    print(f'extract: {len(batch)} candidates -> {created} new commitments, '
          f'{len(consumed_ts)} triaged, {len(state["pending_candidates"])} still pending')

# ---------------------------------------------------------------------- CLI --

def cmd_add(args):
    state = load_state()
    it = create_item(
        state, text=args.text, to=args.to or '', due=args.due, project=args.project,
        source_type='manual', source_ref=args.source or '', confidence='high',
        priority=args.priority,
    )
    save_state(state)
    print(f"added: {it['id']}")

def cmd_close(args):
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    it.update(status='done', closed_at=time.time(), closed_by='manual')
    if args.note:
        it.setdefault('notes', []).append(args.note)
    save_state(state)
    print(f'closed: {args.item_id}')

def cmd_drop(args):
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    it.update(status='dropped', closed_at=time.time(), closed_by='manual')
    if args.note:
        it.setdefault('notes', []).append(args.note)
    save_state(state)
    print(f'dropped: {args.item_id}')

def cmd_link(args):
    """Link a commitment to a tracker ticket (tickets.json T-id) so the dashboard
    can show which commitments already have a ticket ('Jadiin ticket' follow-up)."""
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    it['ticket_id'] = args.ticket
    save_state(state)
    print(f"linked: {args.item_id} -> {args.ticket}")

def cmd_unlink(args):
    state = load_state()
    it = state['items'].get(args.item_id)
    if not it:
        sys.exit(f'item not found: {args.item_id}')
    it['ticket_id'] = None
    save_state(state)
    print(f'unlinked: {args.item_id}')

def age_str(ts):
    h = (time.time() - float(ts)) / 3600
    return f'{h/24:.1f}d' if h >= 24 else f'{h:.0f}h'

def cmd_report(args):
    state = load_state()
    items = list(state['items'].values())
    if not args.all:
        items = [it for it in items if it['status'] == 'open']
    if not items:
        print('No open commitments. Ledger is clean.')
        return
    today = wib_today()

    def overdue(it):
        if not it.get('due') or it['status'] != 'open':
            return False
        try:
            return datetime.strptime(it['due'], '%Y-%m-%d').date() < today
        except Exception:
            return False

    def sort_key(it):
        if it['status'] != 'open':
            return (2, 0, -it.get('closed_at', 0))
        if overdue(it):
            return (0, 0, it['due'])
        if it.get('due'):
            return (1, 0, it['due'])
        return (1, 1, -it['first_seen'])

    items.sort(key=sort_key)
    print(f'## 📌 Outbound Commitments ({sum(1 for i in items if i["status"] == "open")} open)\n')
    for it in items:
        if it['status'] != 'open':
            continue
        flag = '🔥 ' if it['priority'] else ''
        od = ' ⚠️ OVERDUE' if overdue(it) else ''
        due_s = f" (due {it['due']})" if it.get('due') else ''
        to_s = f" -> {it['to']}" if it.get('to') else ''
        link = f" [ref]({it['permalink']})" if it.get('permalink') else ''
        conf = it['confidence']
        print(f"- {flag}**{it['text']}**{to_s}{due_s}{od} · {age_str(it['first_seen'])} old · "
              f"{conf} conf{link}  `{it['id']}` [{it['source']['type']}]")
    closed = [it for it in items if it['status'] != 'open']
    if args.all and closed:
        print(f'\n### Closed ({len(closed)})\n')
        for it in closed:
            print(f"- ~~{it['text']}~~ · {it['status']} by {it.get('closed_by', '?')}  `{it['id']}`")

# -------------------------------------------------------------------- main --

def main():
    p = argparse.ArgumentParser(description='Outbound commitments ledger')
    sub = p.add_subparsers(dest='cmd')

    sub.add_parser('sweep')

    ep = sub.add_parser('extract')
    ep.add_argument('--limit', type=int, default=25)

    ap = sub.add_parser('add')
    ap.add_argument('--text', required=True)
    ap.add_argument('--to', default='')
    ap.add_argument('--due', default=None)
    ap.add_argument('--project', default=None)
    ap.add_argument('--source', default=None)
    ap.add_argument('--priority', action='store_true', default=None)

    cp = sub.add_parser('close')
    cp.add_argument('item_id')
    cp.add_argument('--note', default=None)

    dp = sub.add_parser('drop')
    dp.add_argument('item_id')
    dp.add_argument('--note', default=None)

    lp = sub.add_parser('link')
    lp.add_argument('item_id')
    lp.add_argument('--ticket', required=True)

    ulp = sub.add_parser('unlink')
    ulp.add_argument('item_id')

    rp = sub.add_parser('report')
    rp.add_argument('--all', action='store_true')

    args = p.parse_args()
    {'sweep': cmd_sweep, 'extract': cmd_extract, 'add': cmd_add,
     'close': cmd_close, 'drop': cmd_drop, 'report': cmd_report,
     'link': cmd_link, 'unlink': cmd_unlink,
     }.get(args.cmd or 'sweep', cmd_sweep)(args)

if __name__ == '__main__':
    main()
