#!/usr/bin/env python3
"""
Product Dashboard — Local HTTP Server
Serves the dashboard UI and provides API for reading/writing Dashboard.md,
fetching Google Calendar events, and browsing project files.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, unquote

PORT = int(os.environ.get('DASHBOARD_PORT', '3737'))
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = BASE_DIR / 'Dashboard.md'
PUBLIC_DIR = Path(__file__).resolve().parent / 'public'
CLIENTS_DIR = BASE_DIR / 'Clients'
TOKEN_FILE = BASE_DIR / 'token_calendar.json'
CREDENTIALS_FILE = BASE_DIR / 'credentials.json'
SCRATCH_DIR = BASE_DIR / 'scratch'
AGY_COST_PATH = BASE_DIR / 'dashboard-data' / 'agy_cost_summary.json'
HEARTBEAT_PATH = BASE_DIR / 'dashboard-data' / 'agent_heartbeat.jsonl'
ACTIVE_PROJECTS_PATH = BASE_DIR / 'journal' / 'active_projects.md'
TICKETS_PATH = BASE_DIR / 'journal' / 'state' / 'tickets.json'
INITIATIVES_PATH = BASE_DIR / 'journal' / 'state' / 'initiatives.json'
PORTFOLIO_PATH = BASE_DIR / 'journal' / 'state' / 'portfolio.json'
ACTIONS_QUEUE = BASE_DIR / 'journal' / 'queue' / 'actions.jsonl'
ROUTINES_PATH = BASE_DIR / 'journal' / 'state' / 'routines.json'
INSIGHTS_PATH = BASE_DIR / 'journal' / 'state' / 'insights.json'
RECORDER_DIR = BASE_DIR / 'meeting-recorder'
ACTIVITY_LOG_PATH = BASE_DIR / 'journal' / 'activity_log.jsonl'
FATHOM_REGISTRY_PATH = BASE_DIR / 'journal' / 'fathom_registry.json'
DECISIONS_PATH = BASE_DIR / 'journal' / 'state' / 'decisions.json'
COMMITMENTS_PATH = BASE_DIR / 'journal' / 'state' / 'commitments.json'
WAITING_ON_PATH = BASE_DIR / 'journal' / 'state' / 'waiting_on.json'
OUTCOMES_PATH = BASE_DIR / 'journal' / 'state' / 'outcomes.json'
PEOPLE_PATH = BASE_DIR / 'journal' / 'state' / 'people.json'
PEOPLE_DIR = CLIENTS_DIR / 'Work' / 'People'
PREMEETING_STATE_PATH = BASE_DIR / 'journal' / 'state' / 'premeeting.json'
PREMEETING_DIR = BASE_DIR / 'journal' / 'premeeting'
HARNESS_HEALTH_PATH = BASE_DIR / 'journal' / 'state' / 'harness_health.json'
MEMORY_DIR = Path.home() / '.claude' / 'projects' / '-home-you-antigravity-projects-product-second-brain' / 'memory'
JOB_ACKS_PATH = BASE_DIR / 'journal' / 'state' / 'job_acks.json'
AI_RUNS_DIR = BASE_DIR / 'journal' / 'ai_runs'
AI_DRAFTS_DIR = BASE_DIR / 'journal' / 'ai_drafts'
COMMITMENT_CLI = '.agent/skills/commitment-ledger/scripts/commitment_ledger.py'
# claude CLI: WSL resolves the Windows npm global wrapper (a POSIX sh script that
# runs Linux node against the package on /mnt/c) — verified working headless
# 2026-07-11 (~4s haiku round-trip). which() first so a future native Linux
# install wins automatically; fallback hardcoded for cron-started servers whose
# PATH lacks /mnt/c interop dirs.
CLAUDE_BIN_FALLBACK = '/mnt/c/Users/You/AppData/Roaming/npm/claude'
WIB = timezone(timedelta(hours=7))
VEXA_AUTO_LOG = '/tmp/vexa_auto.log'

# Job -> log file + heartbeat-job-name map for GET /api/job-log. Hardcoded from the
# authoritative CRON_REGISTRY in .agent/skills/harness-health/scripts/harness_health.py
# (heartbeat_job mirrors 'job' for every entry except mention-ledger, which has no
# heartbeat integration yet).
JOB_LOG_MAP = {
    'maintenance': {
        'log_file': str(BASE_DIR / 'scripts' / 'maintenance.log'),
        'heartbeat_job': 'maintenance',
    },
    'dashboard-keepalive': {
        'log_file': str(BASE_DIR / '.agent' / 'scripts' / 'dashboard_keepalive.log'),
        'heartbeat_job': 'dashboard-keepalive',
    },
    'vexa-auto': {
        'log_file': VEXA_AUTO_LOG,
        'heartbeat_job': 'vexa-auto',
    },
    'mention-ledger': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'slack-tracker' / 'ledger_cron.log'),
        'heartbeat_job': None,
    },
    'commitment-ledger': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'commitment-ledger' / 'commitment_ledger_cron.log'),
        'heartbeat_job': 'commitment-ledger',
    },
    'waiting-watchdog': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'waiting-watchdog' / 'waiting_watchdog_cron.log'),
        'heartbeat_job': 'waiting-watchdog',
    },
    'outcomes-loop': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'outcomes-loop' / 'outcomes_loop_cron.log'),
        'heartbeat_job': 'outcomes-loop',
    },
    'premeeting-cards': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'premeeting-cards' / 'premeeting_cron.log'),
        'heartbeat_job': 'premeeting-cards',
    },
    'harness-health': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'harness-health' / 'harness_health_cron.log'),
        'heartbeat_job': 'harness-health',
    },
    'token-tracker': {
        'log_file': str(BASE_DIR / '.agent' / 'skills' / 'token-tracker' / 'token_tracker_cron.log'),
        'heartbeat_job': 'token-tracker',
    },
}

# POST /api/run-job whitelist: job -> argv (relative to BASE_DIR) + its crontab flock
# lockfile (same paths as `crontab -l`, so a manual click can never race the real cron
# firing the same job). mention-ledger is deliberately excluded (sweeps every 3-4min
# already — see _handle_post_run_job). maintenance has no flock in crontab itself
# (cron fires it unguarded); we still lock manual triggers against each other.
LOCK_CONFLICT_CODE = 75  # flock -E <code>: distinguishes "lock busy" from the job's own rc
JOB_RUN_MAP = {
    'outcomes-loop': {
        'argv': ['python3', '.agent/skills/outcomes-loop/scripts/outcomes_loop.py', 'check'],
        'lock': '/tmp/outcomes_loop.lock',
    },
    'harness-health': {
        'argv': ['python3', '.agent/skills/harness-health/scripts/harness_health.py', 'run'],
        'lock': '/tmp/harness_health.lock',
    },
    'commitment-ledger': {
        'argv': ['python3', '.agent/skills/commitment-ledger/scripts/commitment_ledger.py', 'sweep'],
        'lock': '/tmp/commitment_ledger.lock',
    },
    'waiting-watchdog': {
        'argv': ['python3', '.agent/skills/waiting-watchdog/scripts/waiting_watchdog.py', 'sweep'],
        'lock': '/tmp/waiting_watchdog.lock',
    },
    'premeeting-cards': {
        'argv': ['python3', '.agent/skills/premeeting-cards/scripts/premeeting_cards.py', 'generate'],
        'lock': '/tmp/premeeting_cards.lock',
    },
    'maintenance': {
        'argv': ['/bin/bash', 'scripts/maintenance.sh'],
        'lock': '/tmp/maintenance.lock',
    },
    'token-tracker': {
        'argv': ['python3', '.agent/skills/token-tracker/scripts/token_usage.py', 'sweep'],
        'lock': '/tmp/token_tracker.lock',
    },
}

# ── token usage tracker (GET /api/token-usage) ──
TOKEN_USAGE_PATH = BASE_DIR / 'journal' / 'state' / 'token_usage.json'
TOKEN_TRACKER_SCRIPT = BASE_DIR / '.agent' / 'skills' / 'token-tracker' / 'scripts' / 'token_usage.py'
TOKEN_TRACKER_LOG = BASE_DIR / '.agent' / 'skills' / 'token-tracker' / 'token_tracker_cron.log'
TOKEN_USAGE_STALE_SECS = 6 * 3600
TOKEN_USAGE_NOTE = ('Claude = estimasi setara-API (You pakai subscription); '
                    'biaya offload riil ada di agy')

# ═══════════════════════════════════════════
# AI TASK RUNNER (headless claude CLI, detached)
# ═══════════════════════════════════════════
# POST /api/ai-task {kind, ref} spawns a DETACHED `claude -p` run whose stdout+stderr
# stream to journal/ai_runs/<id>.log; a shell sentinel line 'AI_TASK_DONE rc=N' marks
# completion so status is derivable from the log alone (no process table needed).
# Meta lives in journal/ai_runs/<id>.json. Drafts land in journal/ai_drafts/ — the
# prompts forbid any external send (Slack/email/API writes); You reviews drafts.

AI_TASK_SENTINEL = 'AI_TASK_DONE rc='
AI_TASK_MAX_RUNNING = 2
AI_TASK_STALE_MIN = 45          # running runs older than this stop blocking the slots
AI_TASK_KINDS = ('ping', 'commitment', 'fix-job', 'verify-commitments')
BRIAN_SLACK_ID = '<SLACK_ID>'  # verified via auth.test 2026-07-09 (commitment_ledger.py)

def _claude_bin():
    return shutil.which('claude') or CLAUDE_BIN_FALLBACK

def _ai_env():
    """Child env for claude runs: strip the parent Claude-Code session markers so a
    dashboard-spawned run never self-identifies as a nested subagent of whatever
    session (re)started the server. Everything else (PATH, HOME, tokens) passes through."""
    env = dict(os.environ)
    for k in list(env):
        if k == 'CLAUDECODE' or k.startswith(('CLAUDE_CODE_', 'CLAUDE_AGENT_',
                                              'CLAUDE_EFFORT', 'CLAUDE_AUTOCOMPACT')):
            env.pop(k, None)
    return env

def _default_gateway_ip():
    try:
        r = subprocess.run(['sh', '-c', "ip route | awk '/default/{print $3; exit}'"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ''

def _ai_task_spec(kind, ref):
    """(prompt, allowed_tools, model, expected_result_relpath|None) for a kind+ref.
    Raises ValueError with a user-facing message on a bad ref."""
    repo = str(BASE_DIR)
    if kind == 'ping':
        return 'Reply with exactly the word pong.', '', 'haiku', None

    if kind == 'commitment':
        state = json.loads(COMMITMENTS_PATH.read_text(encoding='utf-8'))
        it = (state.get('items') or {}).get(ref)
        if not it:
            raise ValueError(f'commitment {ref!r} not found in commitments.json')
        src = it.get('source') or {}
        source_bits = ' '.join(x for x in [src.get('type', ''), src.get('ref', ''),
                                           it.get('permalink', '')] if x)
        draft_rel = f'journal/ai_drafts/{ref}.md'
        prompt = (
            f"Work in {repo}. "
            f"Commitment {ref}: '{it.get('text', '')}'"
            + (f" owed to {it.get('to')}" if it.get('to') else '')
            + (f" (source: {source_bits})" if source_bits else '') + '. '
            f"Research context in the repo (MOMs in Clients/*/meetings, journal/, Slack "
            f"ledger states in journal/state/) then produce the DELIVERABLE AS A DRAFT in "
            f"{draft_rel}: if it's a message -> a ready-to-send draft in You's plain "
            f"flowing prose (no emoji, no numbered-bold); if a doc -> the doc draft; if "
            f"scheduling -> the proposed invite text. First line of the file: "
            f"'# Draft for {ref} — REVIEW BEFORE SENDING'. NEVER send anything, never "
            f"post to Slack, never call external write APIs."
        )
        return prompt, 'Read,Grep,Glob,Write', 'sonnet', draft_rel

    if kind == 'fix-job':
        if ref in ('vexa-auto', 'vexa-bots'):
            gw = _default_gateway_ip() or '<default-gateway>'
            prompt = (
                f"Work in {repo}. Diagnose the vexa meeting-bot stack: check containers via "
                f"`sg docker -c 'docker ps'` (expect vexa-lite / postgres / minio), tail "
                f"{VEXA_AUTO_LOG}, probe whisper at http://{gw}:8083/ (curl), and check "
                f"meeting-recorder/vexa_state.json recent statuses. You MAY restart the vexa "
                f"docker containers (`sg docker -c 'docker restart vexa-lite'` etc.) and "
                f"re-run `python3 meeting-recorder/vexa_bots.py auto --dry-run`. Do NOT send "
                f"any Slack/email/external message and do NOT edit repo files. Write findings "
                f"+ actions taken + current status to stdout."
            )
            return prompt, 'Read,Grep,Glob,Bash', 'sonnet', None
        entry = JOB_LOG_MAP.get(ref)
        if not entry:
            raise ValueError(f'unknown job {ref!r}; allowed: '
                             + ', '.join(sorted(set(JOB_LOG_MAP) | {'vexa-bots'})))
        run_entry = JOB_RUN_MAP.get(ref)
        cli_hint = (f"Its skill CLI is `{' '.join(run_entry['argv'])}` — remediate ONLY via "
                    f"that skill's own CLI subcommands (try its --help / report subcommand "
                    f"first). " if run_entry else
                    "Remediate ONLY via the owning skill's own CLI subcommands if it has "
                    "any (look under .agent/skills/ and .agent/scripts/); otherwise "
                    "diagnose-only. ")
        hb_hint = (f"latest heartbeat row for job '{entry['heartbeat_job']}' in "
                   f"dashboard-data/agent_heartbeat.jsonl" if entry.get('heartbeat_job')
                   else 'dashboard-data/agent_heartbeat.jsonl (this job has no heartbeat rows)')
        prompt = (
            f"Work in {repo}. The scheduled job '{ref}' is failing or warning on the "
            f"dashboard. Diagnose it: tail its cron log at {entry['log_file']}, read the "
            f"{hb_hint}, and inspect the skill's state file(s) under journal/state/ if any. "
            f"{cli_hint}"
            f"Do NOT send any Slack/email/external message, do NOT edit code, do NOT touch "
            f"crontab. Write findings + actions taken + current status to stdout."
        )
        return prompt, 'Read,Grep,Glob,Bash', 'sonnet', None

    if kind == 'verify-commitments':
        today = datetime.now(WIB).strftime('%Y-%m-%d')
        draft_rel = f'journal/ai_drafts/commitment_verify_{today}.md'
        prompt = (
            f"Work in {repo}. Audit ALL open items in journal/state/commitments.json for "
            f"validity/staleness: for each, look for completion evidence in You's sent "
            f"Slack messages (use `python3 .agent/skills/slack-connector/scripts/"
            f"slack_client.py --action search --query \"from:<@{BRIAN_SLACK_ID}> "
            f"<keywords>\"` — bounded, a few searches max, sleep ~0.3s between calls) and "
            f"in MOMs under Clients/*/meetings newer than the item. Close proven-done ones "
            f"via `python3 {COMMITMENT_CLI} close <id> --note '<evidence>'`, drop "
            f"clearly-invalid/not-a-commitment ones via `python3 {COMMITMENT_CLI} drop "
            f"<id> --note '<why>'`, and write {draft_rel} listing three sections: closed "
            f"(with evidence link), dropped (why), kept-but-suspicious (why, needs You). "
            f"Be conservative: only close on clear evidence. Do NOT send any Slack/email/"
            f"external message; the slack_client search action is read-only and allowed."
        )
        return prompt, 'Read,Grep,Glob,Bash,Write', 'sonnet', draft_rel

    raise ValueError(f'unknown kind {kind!r}; allowed: {", ".join(AI_TASK_KINDS)}')

def _ai_run_read(meta_path):
    """Load one run's meta + derive live status from its log sentinel / pid.
    Persists a derived terminal status back into the meta file (idempotent)."""
    try:
        meta = json.loads(Path(meta_path).read_text(encoding='utf-8'))
    except Exception:
        return None
    log_path = AI_RUNS_DIR / f"{meta.get('id', '')}.log"
    tail = []
    if log_path.exists():
        try:
            tail = log_path.read_text(encoding='utf-8', errors='replace').splitlines()[-30:]
        except Exception:
            tail = []
    if meta.get('status') == 'running':
        sentinel = next((ln for ln in reversed(tail) if ln.startswith(AI_TASK_SENTINEL)), None)
        finished = None
        if sentinel is not None:
            try:
                rc = int(sentinel.split('rc=', 1)[1].strip())
            except (ValueError, IndexError):
                rc = -1
            meta['status'] = 'done' if rc == 0 else 'error'
            meta['rc'] = rc
            finished = True
            # --output-format json runs: the last stdout line before the sentinel
            # is one JSON result object with usage + total_cost_usd. Extract into
            # the meta; pre-JSON text runs just never gain these fields.
            for ln in reversed(tail):
                if not ln.startswith('{'):
                    continue
                try:
                    res = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(res, dict) or ('usage' not in res
                                                 and 'total_cost_usd' not in res):
                    continue
                u = res.get('usage') or {}
                try:
                    meta['tokens_in'] = (int(u.get('input_tokens') or 0)
                                         + int(u.get('cache_creation_input_tokens') or 0)
                                         + int(u.get('cache_read_input_tokens') or 0))
                    meta['tokens_out'] = int(u.get('output_tokens') or 0)
                    if res.get('total_cost_usd') is not None:
                        meta['cost_usd'] = round(float(res['total_cost_usd']), 6)
                except (TypeError, ValueError):
                    pass
                break
        else:
            pid = meta.get('pid')
            alive = False
            if pid:
                try:
                    os.kill(int(pid), 0)
                    alive = True
                except (OSError, ValueError):
                    alive = False
            if not alive:
                meta['status'] = 'error'
                meta['note'] = 'process exited without sentinel (killed or spawn failed)'
                finished = True
        if finished:
            try:
                ts = log_path.stat().st_mtime if log_path.exists() else time.time()
                meta['finished_wib'] = datetime.fromtimestamp(ts, WIB).isoformat(timespec='seconds')
                tmp = str(meta_path) + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(meta, fh, ensure_ascii=False, indent=1)
                os.replace(tmp, meta_path)
            except Exception:
                pass
    # result_path: only surface once the file actually exists on disk
    exp = meta.get('expected_result')
    meta['result_path'] = exp if (exp and (BASE_DIR / exp).exists()) else None
    meta['_tail'] = tail
    return meta

def _ai_runs_all():
    """All runs' meta (status-derived), newest first."""
    if not AI_RUNS_DIR.exists():
        return []
    metas = []
    for p in AI_RUNS_DIR.glob('air-*.json'):
        m = _ai_run_read(p)
        if m:
            metas.append(m)
    metas.sort(key=lambda m: m.get('started_epoch') or 0, reverse=True)
    return metas

# ═══════════════════════════════════════════
# SMALL SHARED HELPERS (waiting dedupe, progress, MOM dedupe)
# ═══════════════════════════════════════════

def _resolve_person_slug(name):
    """Mirror of waiting_watchdog.py's roster resolution (people.json full name /
    alias / unambiguous first name, case-insensitive; fallback bare slugify) so the
    server-side dedupe compares the SAME owner_slug the CLI would write."""
    n = (name or '').strip().lower()
    bare = re.sub(r'[^a-z0-9]+', '-', n).strip('-')
    if not n:
        return bare
    lookup = {}
    try:
        people = (json.loads(PEOPLE_PATH.read_text(encoding='utf-8')) or {}).get('people') or {}
    except Exception:
        people = {}
    first_owners = {}
    for slug, person in people.items():
        full = (person.get('name') or '').strip()
        if full:
            lookup.setdefault(full.lower(), slug)
            first_owners.setdefault(full.split()[0].lower(), set()).add(slug)
        for alias in person.get('aliases') or []:
            alias = (alias or '').strip()
            if alias:
                lookup.setdefault(alias.lower(), slug)
    for first, slugs in first_owners.items():
        if len(slugs) == 1:
            lookup.setdefault(first, next(iter(slugs)))
    return lookup.get(n) or bare

def _token_overlap(a, b):
    """Symmetric-ish token overlap in [0,1]: |A∩B| / min(|A|,|B|) — min-based so a
    short re-chase of a long tracked item still registers as the same ask."""
    ta = set(re.findall(r'[a-z0-9]+', (a or '').lower()))
    tb = set(re.findall(r'[a-z0-9]+', (b or '').lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))

_PROGRESS_GIT_CACHE = {'ts': 0.0, 'per_day': None}

def _git_docs_created_per_day():
    """{date: count} of *.md files first ADDED in the last 14 days under Clients/ +
    journal/ (one git call, 10-min cache; each file counted once, at its newest add)."""
    now = time.time()
    if _PROGRESS_GIT_CACHE['per_day'] is not None and now - _PROGRESS_GIT_CACHE['ts'] < 600:
        return _PROGRESS_GIT_CACHE['per_day']
    per_day, seen, cur = {}, set(), None
    try:
        out = subprocess.run(
            ['git', 'log', '--since=14.days', '--diff-filter=A', '--name-only',
             '--date=format:%Y-%m-%d', '--pretty=format:@%ad', '--', 'Clients', 'journal'],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=20).stdout
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if ln.startswith('@'):
                cur = ln[1:]
            elif ln.endswith('.md') and cur and ln not in seen:
                seen.add(ln)
                per_day[cur] = per_day.get(cur, 0) + 1
    except Exception:
        per_day = {}
    _PROGRESS_GIT_CACHE['ts'] = now
    _PROGRESS_GIT_CACHE['per_day'] = per_day
    return per_day

_MOM_DATE_RE = re.compile(
    r'\b\d{4}[-_/]?\d{2}[-_/]?\d{2}\b|'
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s*\d{4})?\b|'
    r'\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s*\d{4})?\b',
    re.IGNORECASE)

def _norm_mom_title(title):
    """Normalize a MOM title for dedupe: drop the MOM:/date decorations + punctuation
    so 'MOM: B2C Daily Scrum — 2026-07-10' and 'MOM B2C Daily Scrum (July 11)' collapse
    to the same key. Bare numbers (sprint 14 vs 15) deliberately survive."""
    s = (title or '').lower()
    s = re.sub(r'^\s*(mom|meeting\s+minutes?)\b[\s:\-–—]*', '', s)
    s = _MOM_DATE_RE.sub(' ', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return s

# ═══════════════════════════════════════════
# VEXA BOT LIVE HEALTH (real-time service probe)
# ═══════════════════════════════════════════
_VEXA_CACHE = {'ts': 0.0, 'data': None}

def _http_ok(url, timeout=4):
    """True + status if a URL responds at all (any HTTP code = reachable)."""
    try:
        resp = urlopen(Request(url), timeout=timeout)
        return True, resp.getcode()
    except Exception as e:
        code = getattr(e, 'code', None)
        return (code is not None), code

def _probe_vexa():
    """Live Vexa health, cached ~15s so dashboard polling stays cheap."""
    import time
    now = time.time()
    if _VEXA_CACHE['data'] is not None and (now - _VEXA_CACHE['ts']) < 15:
        return _VEXA_CACHE['data']

    out = {'checked_wib': datetime.now(WIB).isoformat(), 'checks': {}}

    # One combined docker call: container state + storage backend + recent storage errors
    container_state = health = backend = ''
    store_errs = None
    try:
        probe = subprocess.run(
            ['sg', 'docker', '-c',
             'docker inspect -f "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}" vexa-lite 2>/dev/null; '
             'echo "@@B@@"; docker exec vexa-lite printenv STORAGE_BACKEND 2>/dev/null; '
             'echo "@@E@@"; docker logs vexa-lite --since 4m 2>&1 | grep -c "storage list failed"'],
            capture_output=True, text=True, timeout=25)
        raw = probe.stdout
        seg = raw.split('@@B@@')
        if seg and '|' in seg[0]:
            container_state, health = (seg[0].strip().split('|', 1) + [''])[:2]
        if len(seg) > 1:
            rest = seg[1].split('@@E@@')
            backend = rest[0].strip()
            if len(rest) > 1:
                try:
                    store_errs = int(rest[1].strip() or 0)
                except ValueError:
                    store_errs = None
    except Exception:
        pass

    running = container_state == 'running'
    out['checks']['container'] = {
        'ok': running, 'state': container_state or 'unknown', 'health': health or 'n/a',
        'label': 'Container', 'detail': f'{container_state or "?"}' + (f' / {health}' if health else ''),
    }
    api_ok, api_code = _http_ok('http://localhost:8056/')
    out['checks']['api'] = {'ok': api_ok, 'label': 'API gateway :8056',
                            'detail': f'HTTP {api_code}' if api_code else 'no response'}

    # whisper.cpp transcription backend on the Windows host (gateway IP:8083)
    gw = ''
    try:
        r = subprocess.run(['sh', '-c', "ip route | awk '/default/{print $3; exit}'"],
                           capture_output=True, text=True, timeout=5)
        gw = r.stdout.strip()
    except Exception:
        pass
    wh_ok, wh_code = _http_ok(f'http://{gw}:8083/') if gw else (False, None)
    out['checks']['whisper'] = {'ok': wh_ok, 'label': 'Whisper :8083',
                                'detail': (f'HTTP {wh_code}' if wh_code else 'no response') + (f' @ {gw}' if gw else '')}

    store_ok = (backend == 'local') or (backend == 's3') or (backend == 'minio' and store_errs == 0)
    if backend == 'minio' and (store_errs is None or store_errs > 0):
        store_ok = False
    sdetail = backend or 'unknown'
    if store_errs:
        sdetail += f' · {store_errs} storage err/4m'
    out['checks']['storage'] = {'ok': bool(store_ok), 'label': 'Storage backend', 'detail': sdetail}

    # MinIO object store — only relevant when backend=minio (persists browser-session + recordings)
    if backend == 'minio':
        mo_ok, mo_code = _http_ok('http://localhost:9000/minio/health/live')
        out['checks']['minio'] = {'ok': mo_ok, 'label': 'MinIO :9000',
                                  'detail': (f'HTTP {mo_code}' if mo_code else 'no response')}

    # Last cron activity + last/live meeting from vexa_state.json
    last_cron = ''
    try:
        with open(VEXA_AUTO_LOG, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        if lines:
            last_cron = lines[-1][:200]
    except Exception:
        pass
    out['last_cron'] = last_cron

    last_meeting = None
    try:
        vpath = RECORDER_DIR / 'vexa_state.json'
        if vpath.exists():
            meetings = json.loads(vpath.read_text(encoding='utf-8')).get('meetings', {})
            if meetings:
                k, m = max(meetings.items(), key=lambda kv: kv[1].get('sent_at', ''))
                st = str(m.get('status', ''))
                last_meeting = {'title': m.get('title', '(untitled)'), 'sent_at': m.get('sent_at', ''),
                                'status': st, 'ok': 'fail' not in st.lower()}
    except Exception:
        pass
    out['last_meeting'] = last_meeting

    checks = out['checks']
    core_ok = (checks['container']['ok'] and checks['api']['ok'] and checks['storage']['ok']
               and checks.get('minio', {}).get('ok', True))
    if core_ok and checks['whisper']['ok']:
        out['overall'] = 'ok'
    elif core_ok:
        out['overall'] = 'degraded'  # core up but transcription backend unreachable
    else:
        out['overall'] = 'down'

    _VEXA_CACHE['ts'] = now
    _VEXA_CACHE['data'] = out
    return out

# ═══════════════════════════════════════════
# GOOGLE CALENDAR (raw HTTP, no deps)
# ═══════════════════════════════════════════

def _refresh_token():
    """Refresh the Google OAuth token using the refresh_token."""
    if not TOKEN_FILE.exists():
        return None

    token_data = json.loads(TOKEN_FILE.read_text())
    refresh_token = token_data.get('refresh_token')
    client_id = token_data.get('client_id')
    client_secret = token_data.get('client_secret')
    token_uri = token_data.get('token_uri', 'https://oauth2.googleapis.com/token')

    if not all([refresh_token, client_id, client_secret]):
        return None

    # Check if token is still valid
    expiry = token_data.get('expiry', '')
    if expiry:
        try:
            expiry_dt = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            if expiry_dt > datetime.now(timezone.utc) + timedelta(minutes=5):
                return token_data.get('token')
        except Exception:
            pass

    # Refresh
    data = urlencode({
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }).encode()

    try:
        req = Request(token_uri, data=data, method='POST')
        resp = urlopen(req, timeout=10)
        result = json.loads(resp.read())
        new_token = result.get('access_token')

        if new_token:
            token_data['token'] = new_token
            expires_in = result.get('expires_in', 3600)
            token_data['expiry'] = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
            TOKEN_FILE.write_text(json.dumps(token_data))
            return new_token
    except Exception as e:
        print(f"  [WARN] Token refresh failed: {e}")
        return None

    return None

def _fetch_work_calendar(days_back=1, days_forward=7):
    """Work calendar via the gcal_manager work profile (subprocess). Tagged account='work'.
    gcal_manager --json returns {start, summary, description} only (no end time)."""
    import subprocess
    try:
        proc = subprocess.run(
            ['python3', '.agent/skills/google-calendar-connector/gcal_manager.py',
             'list', '--profile', 'work', '--json',
             '--days-back', str(days_back), '--days-forward', str(days_forward)],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=70)
        raw = json.loads(proc.stdout or '[]')
    except Exception:
        return []
    today_str = datetime.now().strftime('%Y-%m-%d')
    out = []
    for e in raw:
        start_str = e.get('start', '') or ''
        is_all_day = 'T' not in start_str
        try:
            if is_all_day:
                sdt = datetime.strptime(start_str[:10], '%Y-%m-%d'); tr = 'All day'
            else:
                sdt = datetime.fromisoformat(start_str); tr = sdt.strftime('%H:%M')
        except Exception:
            continue
        date_str = sdt.strftime('%Y-%m-%d')
        out.append({'date': date_str, 'dayName': sdt.strftime('%a'), 'timeRange': tr,
                    'summary': e.get('summary', '(No title)'), 'location': '', 'htmlLink': '',
                    'attendees': [], 'description': (e.get('description', '') or '')[:200],
                    'isAllDay': is_all_day, 'isToday': date_str == today_str, 'account': 'work'})
    return out

def _fetch_calendar_events(days_back=1, days_forward=7):
    """Personal (raw token) + Work (gcal_manager subprocess) events, merged + tagged by account."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    parsed = []
    errors = []
    token = _refresh_token()
    if token:
        now = datetime.now(timezone.utc)
        params = urlencode({
            'timeMin': (now - timedelta(days=days_back)).isoformat(),
            'timeMax': (now + timedelta(days=days_forward)).isoformat(),
            'singleEvents': 'true', 'orderBy': 'startTime', 'maxResults': 100,
        })
        url = f'https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}'
        req = Request(url)
        req.add_header('Authorization', f'Bearer {token}')
        try:
            resp = urlopen(req, timeout=15)
            for e in json.loads(resp.read()).get('items', []):
                start_str = e.get('start', {}).get('dateTime', e.get('start', {}).get('date', ''))
                end_str = e.get('end', {}).get('dateTime', e.get('end', {}).get('date', ''))
                is_all_day = 'T' not in start_str
                if is_all_day:
                    date_str = start_str; time_range = 'All day'
                    start_dt_parsed = datetime.strptime(start_str, '%Y-%m-%d')
                else:
                    start_dt_parsed = datetime.fromisoformat(start_str)
                    end_dt_parsed = datetime.fromisoformat(end_str)
                    date_str = start_dt_parsed.strftime('%Y-%m-%d')
                    time_range = f"{start_dt_parsed.strftime('%H:%M')} - {end_dt_parsed.strftime('%H:%M')}"
                parsed.append({
                    'date': date_str, 'dayName': start_dt_parsed.strftime('%a'), 'timeRange': time_range,
                    'summary': e.get('summary', '(No title)'), 'location': e.get('location', ''),
                    'htmlLink': e.get('htmlLink', ''),
                    'attendees': [a.get('email', '') for a in e.get('attendees', []) if not a.get('self', False)][:5],
                    'description': (e.get('description', '') or '')[:200],
                    'isAllDay': is_all_day, 'isToday': date_str == today_str, 'account': 'personal',
                })
        except Exception as e:
            errors.append(f'personal: {e}')
    else:
        errors.append('personal: no token')

    # Work calendar via the work profile (separate account)
    try:
        parsed.extend(_fetch_work_calendar(days_back, days_forward))
    except Exception as e:
        errors.append(f'work: {e}')

    parsed.sort(key=lambda x: (x['date'], x['timeRange']))
    out = {'events': parsed, 'today': today_str}
    if errors and not parsed:
        out['error'] = '; '.join(errors)
    elif errors:
        out['warning'] = '; '.join(errors)
    return out

# ═══════════════════════════════════════════
# PROJECT FILE BROWSER
# ═══════════════════════════════════════════

# Map project names from Dashboard.md to actual folder paths
PROJECT_PATH_MAP = {
    'strategic roadmap':  'Work/strategy',
    'marketplace cms':    'Work/Marketplace',
    'marketplace':        'Work/Marketplace',
    'example program':          'Work/Example Program',
    'b2c superapp':       'Work/B2C SuperApp',
    'b2c':                'Work/B2C SuperApp',
    'seller portal':      'Work/Seller Portal',
    'ecom solutions':     'Work/Ecommerce',
    'ecommerce':          'Work/Ecommerce',
    'pim':                'Work/PIM',
    'work id':           'Work/Work ID',
    'safaraya':           'Secondary/Safaraya',
    'gogogo':             'Secondary/Gogogo',
    'gogogo ecosystem':   'Secondary/Gogogo',
    'operations platform':'Secondary/Operations Platform',
}

def _scan_projects():
    """Scan Clients/ directory and return project file listing."""
    result = {}
    if not CLIENTS_DIR.exists():
        return result

    for client_dir in sorted(CLIENTS_DIR.iterdir()):
        if not client_dir.is_dir():
            continue
        client_name = client_dir.name  # "Work" or "Secondary"
        result[client_name] = {}

        for project_dir in sorted(client_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            project_name = project_dir.name
            files = []
            for f in sorted(project_dir.rglob('*.md')):
                rel = f.relative_to(project_dir)
                # Classify file type
                fname = f.name.lower()
                ftype = 'doc'
                if 'prd' in fname:
                    ftype = 'prd'
                elif 'backlog' in fname:
                    ftype = 'backlog'
                elif 'roadmap' in fname:
                    ftype = 'roadmap'
                elif 'strategy' in fname:
                    ftype = 'strategy'
                elif 'requirement' in fname:
                    ftype = 'requirement'

                # Read first 2 lines for summary
                try:
                    with open(f, 'r', encoding='utf-8') as fh:
                        lines = [fh.readline().strip() for _ in range(3)]
                    title = ''
                    for ln in lines:
                        if ln.startswith('# '):
                            title = ln[2:].strip()
                            break
                        elif ln.startswith('title:'):
                            title = ln.split(':', 1)[1].strip()
                            break
                    if not title:
                        title = f.stem.replace('_', ' ').replace('-', ' ')
                except Exception:
                    title = f.stem.replace('_', ' ')

                files.append({
                    'name': f.name,
                    'path': str(f),
                    'relPath': str(rel),
                    'type': ftype,
                    'title': title,
                    'size': f.stat().st_size,
                })

            if files:
                result[client_name][project_name] = files

    return result

# ═══════════════════════════════════════════
# HTTP HANDLER
# ═══════════════════════════════════════════

class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom handler that serves static files + API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def end_headers(self):
        # Without this, browsers heuristically cache style.css/app.js and render
        # new markup against an old stylesheet (the "unstyled Portfolio" bug).
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_GET(self):
        if self.path == '/api/dashboard':
            self._handle_get_dashboard()
        elif self.path.startswith('/api/calendar'):
            self._handle_get_calendar()
        elif self.path == '/api/projects':
            self._handle_get_projects()
        elif self.path.startswith('/api/file/'):
            self._handle_get_file()
        elif self.path == '/api/agy-cost':
            self._handle_get_agy_cost()
        elif self.path == '/api/heartbeat':
            self._handle_get_heartbeat()
        elif self.path == '/api/routines':
            self._handle_get_routines()
        elif self.path == '/api/active-projects':
            self._handle_get_active_projects()
        elif self.path == '/api/initiatives':
            self._handle_get_initiatives()
        elif self.path == '/api/portfolio':
            self._handle_get_portfolio()
        elif self.path.startswith('/api/initiative/'):
            self._handle_get_initiative_detail()
        elif self.path.startswith('/api/job-log'):
            self._handle_get_job_log()
        elif self.path == '/api/slack-channels':
            self._handle_get_slack_channels()
        elif self.path == '/api/activity-spark':
            self._handle_get_activity_spark()
        elif self.path == '/api/tracker':
            self._handle_get_tracker()
        elif self.path == '/api/followups':
            self._handle_get_followups()
        elif self.path == '/api/insights':
            self._handle_get_insights()
        elif self.path == '/api/meetings':
            self._handle_get_meetings()
        elif self.path == '/api/changes':
            self._handle_get_changes()
        elif self.path == '/api/slack-harvest':
            self._handle_get_slack_harvest()
        elif self.path == '/api/recorder':
            self._handle_get_recorder()
        elif self.path == '/api/vexa-health':
            self._handle_get_vexa_health()
        elif self.path == '/api/metrics':
            self._handle_get_metrics()
        elif self.path == '/api/harness':
            self._handle_get_harness()
        elif self.path == '/api/harness-map':
            self._handle_get_harness_map()
        elif self.path == '/api/decisions':
            self._handle_get_decisions()
        elif self.path == '/api/commitments':
            self._handle_get_commitments()
        elif self.path == '/api/waiting-on':
            self._handle_get_waiting_on()
        elif self.path == '/api/outcomes':
            self._handle_get_outcomes()
        elif self.path == '/api/stakeholders':
            self._handle_get_stakeholders()
        elif self.path == '/api/premeeting':
            self._handle_get_premeeting()
        elif self.path == '/api/overview':
            self._handle_get_overview()
        elif self.path.startswith('/api/ai-task'):
            self._handle_get_ai_task()
        elif self.path == '/api/token-usage':
            self._handle_token_usage()
        elif self.path == '/api/briefing':
            self._handle_get_briefing()
        elif self.path == '/api/progress':
            self._handle_get_progress()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/toggle':
            self._handle_toggle()
        elif self.path == '/api/action':
            self._handle_action()
        elif self.path == '/api/waiting-add':
            self._handle_post_waiting_add()
        elif self.path == '/api/run-job':
            self._handle_post_run_job()
        elif self.path == '/api/ack-job':
            self._handle_post_ack_job()
        elif self.path == '/api/ai-task':
            self._handle_post_ai_task()
        elif self.path == '/api/commitment-close':
            self._handle_post_commitment_close()
        elif self.path == '/api/waiting-close':
            self._handle_post_waiting_close()
        elif self.path == '/api/commitment-link':
            self._handle_post_commitment_link()
        else:
            self.send_error(404, 'Not Found')

    def _handle_action(self):
        """Apply a Tracker edit to tickets.json (deterministic + atomic-swap) and log the event.
        Body: {id, status?, priority?, note?, project?}. Structured field edits apply directly
        (safe, instant); no LLM/regex on the source file."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            tid = body.get('id')
            doc = json.loads(TICKETS_PATH.read_text(encoding='utf-8'))
            tickets = doc.get('tickets', [])
            creating = False

            # Portfolio hierarchy + Jira-optional fields (additive; shared by create + edit).
            # Empty string ('') means "clear the field" in edit mode; None means "not supplied".
            initiative_id = body.get('initiative_id')
            if isinstance(initiative_id, str):
                initiative_id = initiative_id.strip()
            jira_key = body.get('jira_key')
            if isinstance(jira_key, str):
                jira_key = jira_key.strip()
                if jira_key and not re.match(r'^[A-Z]+-\d+$', jira_key):
                    self._send_json(400, json.dumps({'error': f'invalid jira_key {jira_key!r}, expected format like MP-123'}))
                    return
            parent_id = body.get('parent_id')
            if isinstance(parent_id, str):
                parent_id = parent_id.strip()
                if parent_id and not any(x.get('id') == parent_id for x in tickets):
                    self._send_json(400, json.dumps({'error': f'parent_id {parent_id} not found'}))
                    return
                if parent_id and tid and parent_id == tid:
                    self._send_json(400, json.dumps({'error': 'parent_id cannot be the ticket itself'}))
                    return

            if not tid:
                # create mode: needs a title (e.g. Meeting -> Ticket)
                if not body.get('title'):
                    self._send_json(400, json.dumps({'error': 'missing id (edit) or title (create)'}))
                    return
                creating = True
                nums = [int(x['id'].split('-')[1]) for x in tickets if x.get('id', '').startswith('T-') and x['id'].split('-')[1].isdigit()]
                tid = f"T-{(max(nums) + 1) if nums else 1:03d}"
                t = {'id': tid, 'title': body['title'][:300], 'priority': body.get('priority', 'P1'),
                     'status': body.get('status', 'todo'), 'kind': body.get('kind', 'self'),
                     'owner': body.get('owner', 'You'), 'project': body.get('project', 'Other'),
                     'note': body.get('note', ''), 'due': body.get('due', ''), 'links': body.get('links', []),
                     'initiative_id': (initiative_id or None), 'jira_key': (jira_key or None),
                     'parent_id': (parent_id or None)}
                tickets.append(t)
            else:
                t = next((x for x in tickets if x.get('id') == tid), None)
                if not t:
                    self._send_json(404, json.dumps({'error': f'ticket {tid} not found'}))
                    return
            if creating:
                doc['tickets'] = tickets
                tmp = str(TICKETS_PATH) + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=2)
                json.loads(open(tmp, encoding='utf-8').read())
                os.replace(tmp, TICKETS_PATH)
                try:
                    subprocess.run(['python3', '.agent/scripts/activity_log.py', '--actor', 'brian',
                                    '--action', 'ticket_create', '--project', t.get('project', 'Other'),
                                    '--target', tid, '--summary', f"created {tid}: {t['title'][:80]}"],
                                   cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10)
                except Exception:
                    pass
                # top-level id so callers (e.g. Meeting->Ticket + commitment-link chains)
                # don't have to dig into .ticket.id
                self._send_json(200, json.dumps({'ok': True, 'id': tid, 'ticket': t, 'created': True}))
                return
            changes = []
            for field in ('status', 'priority', 'note', 'project'):
                if field in body and body[field] is not None and body[field] != t.get(field):
                    changes.append(f"{field} {t.get(field)} to {body[field]}")
                    t[field] = body[field]
            # Portfolio hierarchy + Jira-optional fields: set or clear (empty string -> None).
            # Values already validated (jira_key format, parent_id existence) above.
            for field, val in (('initiative_id', initiative_id), ('jira_key', jira_key), ('parent_id', parent_id)):
                if field in body:
                    newval = val if val else None
                    if newval != t.get(field):
                        changes.append(f"{field} {t.get(field)} to {newval}")
                        t[field] = newval
            comment = (body.get('comment') or '').strip()
            if not changes and not comment:
                self._send_json(200, json.dumps({'ok': True, 'ticket': t, 'note': 'no change'}))
                return
            # comment thread = per-ticket context + history (a real info source)
            now_wib = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')
            t.setdefault('comments', [])
            t['comments'].append({'ts_wib': now_wib, 'by': 'brian',
                                  'change': '; '.join(changes), 'text': comment})
            doc['tickets'] = tickets
            # atomic swap: write tmp, validate, replace
            tmp = str(TICKETS_PATH) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=2)
            json.loads(open(tmp, encoding='utf-8').read())  # validate
            os.replace(tmp, TICKETS_PATH)
            # log the event (full-context memory) incl. the reason
            summary = f"{tid}: " + ('; '.join(changes) if changes else 'comment')
            if comment:
                summary += f" | reason: {comment[:120]}"
            try:
                subprocess.run(['python3', '.agent/scripts/activity_log.py', '--actor', 'brian',
                                '--action', 'ticket_edit', '--project', t.get('project', 'Other'),
                                '--target', tid, '--summary', summary],
                               cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10)
            except Exception:
                pass
            self._send_json(200, json.dumps({'ok': True, 'ticket': t, 'changes': changes, 'commented': bool(comment)}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'action failed', 'details': str(e)}))

    def _handle_get_dashboard(self):
        try:
            content = DASHBOARD_PATH.read_text(encoding='utf-8')
            stat = DASHBOARD_PATH.stat()
            last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            self._send_json(200, json.dumps({
                'content': content,
                'lastModified': last_modified
            }))
        except Exception as e:
            self._send_json(500, json.dumps({
                'error': 'Failed to read Dashboard.md', 'details': str(e)
            }))

    def _handle_get_calendar(self):
        try:
            # Parse query params
            days_back = 1
            days_forward = 7
            if '?' in self.path:
                qs = self.path.split('?', 1)[1]
                for param in qs.split('&'):
                    if '=' in param:
                        k, v = param.split('=', 1)
                        if k == 'days_back':
                            days_back = int(v)
                        elif k == 'days_forward':
                            days_forward = int(v)

            result = _fetch_calendar_events(days_back, days_forward)
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({
                'error': 'Calendar error', 'details': str(e)
            }))

    def _handle_get_projects(self):
        try:
            result = _scan_projects()
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({
                'error': 'Failed to scan projects', 'details': str(e)
            }))

    def _handle_get_file(self):
        """Read a file from the Clients directory (for detail view)."""
        try:
            rel_path = unquote(self.path.replace('/api/file/', '', 1))
            
            # Detect if path is already relative to BASE_DIR (includes 'scratch/', 'Clients/'
            # or the premeeting cards dir)
            if rel_path.startswith(('scratch/', 'Clients/', 'journal/premeeting/')):
                file_path = BASE_DIR / rel_path
            else:
                file_path = CLIENTS_DIR / rel_path
                if not file_path.exists():
                    file_path = SCRATCH_DIR / rel_path

            # Security: ensure it's within CLIENTS_DIR, SCRATCH_DIR or the premeeting cards dir
            file_path = file_path.resolve()
            if not (str(file_path).startswith(str(CLIENTS_DIR.resolve())) or str(file_path).startswith(str(SCRATCH_DIR.resolve())) or str(file_path).startswith(str(PREMEETING_DIR.resolve())) or str(file_path) == str(DASHBOARD_PATH.resolve())):
                self._send_json(403, json.dumps({'error': 'Access denied'}))
                return
            if not file_path.exists():
                self._send_json(404, json.dumps({'error': 'File not found'}))
                return

            content = file_path.read_text(encoding='utf-8')
            self._send_json(200, json.dumps({
                'content': content,
                'name': file_path.name,
                'path': str(file_path)
            }))
        except Exception as e:
            self._send_json(500, json.dumps({
                'error': 'Failed to read file', 'details': str(e)
            }))

    def _handle_toggle(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            line_number = data.get('lineNumber')
            new_state = data.get('newState')

            if not isinstance(line_number, int) or new_state not in ['[ ]', '[x]', '[/]']:
                self._send_json(400, json.dumps({
                    'error': 'Invalid lineNumber or newState.'
                }))
                return

            content = DASHBOARD_PATH.read_text(encoding='utf-8')
            lines = content.split('\n')

            if line_number < 1 or line_number > len(lines):
                self._send_json(400, json.dumps({
                    'error': f'Line {line_number} out of range (1-{len(lines)})'
                }))
                return

            idx = line_number - 1
            line = lines[idx]

            checkbox_re = re.compile(r'\[[ x/]\]')
            if not checkbox_re.search(line):
                self._send_json(400, json.dumps({
                    'error': f'Line {line_number} does not contain a checkbox'
                }))
                return

            lines[idx] = checkbox_re.sub(new_state, line, count=1)
            DASHBOARD_PATH.write_text('\n'.join(lines), encoding='utf-8')

            self._send_json(200, json.dumps({
                'success': True,
                'line': lines[idx]
            }))

        except Exception as e:
            self._send_json(500, json.dumps({
                'error': 'Failed to write Dashboard.md', 'details': str(e)
            }))

    def _handle_get_agy_cost(self):
        """Serve the agy-bridge cost/savings summary written by run.py (write_summary),
        additively normalized with spent/saved/savings_pct aliases (from actual_usd/
        saving_usd/saving_pct) for a generic savings panel. Original keys are untouched —
        existing consumers (tab-system.js reads actual_usd/calls/saving_pct/by_model/by_day
        directly) keep working unchanged."""
        try:
            if not AGY_COST_PATH.exists():
                self._send_json(200, json.dumps({
                    'totals': {}, 'by_task': {}, 'by_model': {}, 'by_day': {},
                    'note': 'No agy-bridge usage yet. Run a --task call or probe.py.'
                }))
                return
            data = json.loads(AGY_COST_PATH.read_text(encoding='utf-8'))

            def _augment(row):
                """Add spent/saved/savings_pct aliases in place; null (not fabricated) if the
                source row is missing the underlying field."""
                if not isinstance(row, dict):
                    return row
                row['spent'] = row.get('actual_usd') if row.get('actual_usd') is not None else None
                row['saved'] = row.get('saving_usd') if row.get('saving_usd') is not None else None
                row['savings_pct'] = row.get('saving_pct') if row.get('saving_pct') is not None else None
                return row

            _augment(data.get('totals') or {})
            for section in ('by_task', 'by_model', 'by_day'):
                for row in (data.get(section) or {}).values():
                    _augment(row)
            self._send_json(200, json.dumps(data))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read agy cost summary', 'details': str(e)}))

    def _handle_get_initiatives(self):
        """Active Projects (Linear-style): each initiative + its handle + ticket counts + recent activity."""
        try:
            if not INITIATIVES_PATH.exists():
                self._send_json(200, json.dumps({'initiatives': [], 'note': 'No initiatives.json yet.'}))
                return
            inits = json.loads(INITIATIVES_PATH.read_text(encoding='utf-8')).get('initiatives', [])
            tickets = self._load_tickets() or []
            # recent activity per project from the event log
            events_by_project = {}
            log = BASE_DIR / 'journal' / 'activity_log.jsonl'
            if log.exists():
                for line in log.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    events_by_project.setdefault(e.get('project', 'Other'), []).append(e)
            def _match(tproj, name):
                tp, nm = (tproj or '').lower().strip(), (name or '').lower().strip()
                return bool(tp) and (tp == nm or tp in nm or nm in tp)
            for it in inits:
                proj = it.get('name')
                tk = [t for t in tickets if _match(t.get('project'), proj)]
                it['ticket_counts'] = {
                    'open': sum(1 for t in tk if t.get('status') in ('todo', 'in_progress', 'blocked', 'waiting')),
                    'blocked': sum(1 for t in tk if t.get('status') == 'blocked'),
                    'total': len(tk),
                }
                ev = [e for k, evs in events_by_project.items() if _match(k, proj) for e in evs]
                it['recent_activity'] = list(reversed(ev))[:5]
            self._send_json(200, json.dumps({'initiatives': inits}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read initiatives', 'details': str(e)}))

    def _handle_get_portfolio(self):
        """Top-down portfolio: team -> initiative -> workstream, with ticket-count +
        health roll-up. Tickets join by initiative_id, falling back to project==team."""
        try:
            if not PORTFOLIO_PATH.exists():
                self._send_json(200, json.dumps({'teams': [], 'note': 'No portfolio.json yet.'}))
                return
            data = json.loads(PORTFOLIO_PATH.read_text(encoding='utf-8'))
            teams = data.get('teams', [])
            tickets = self._load_tickets() or []
            open_states = ('todo', 'in_progress', 'blocked', 'waiting')
            health_rank = {'blocked': 3, 'at_risk': 2, 'on_track': 1, 'planning': 0}

            def _match(tproj, name):
                tp, nm = (tproj or '').lower().strip(), (name or '').lower().strip()
                return bool(tp) and (tp == nm or tp in nm or nm in tp)

            for team in teams:
                inits = team.get('initiatives', [])
                for it in inits:
                    iid = it.get('id')
                    # primary: tickets explicitly tagged with this initiative_id
                    tk = [t for t in tickets if t.get('initiative_id') == iid]
                    it['ticket_counts'] = {
                        'open': sum(1 for t in tk if t.get('status') in open_states),
                        'blocked': sum(1 for t in tk if t.get('status') == 'blocked'),
                        'total': len(tk),
                    }
                    it['blocker_count'] = len(it.get('blockers', []))
                # team roll-up
                active = [i for i in inits if i.get('status') != 'planning']
                ranks = [health_rank.get(i.get('health'), 0) for i in active]
                worst = max(ranks) if ranks else 1
                team['health'] = next((k for k, v in health_rank.items() if v == worst), 'on_track')
                team['summary_counts'] = {
                    'active': len(active),
                    'total': len(inits),
                    'blockers': sum(len(i.get('blockers', [])) for i in inits),
                    'tickets_open': sum(i['ticket_counts']['open'] for i in inits),
                }
            self._send_json(200, json.dumps({'teams': teams, 'updated_wib': data.get('updated_wib')}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read portfolio', 'details': str(e)}))

    def _handle_get_initiative_detail(self):
        """GET /api/initiative/<id> — Portfolio drill-down join: initiative meta from
        portfolio.json + its tickets (top-level, each with children by parent_id), sorted
        blocked-first / overdue-first / priority. unlinked_hint helps You find tickets
        that should be tagged with this initiative_id but aren't yet."""
        try:
            raw = self.path.split('/api/initiative/', 1)[1] if '/api/initiative/' in self.path else ''
            init_id = unquote(raw.split('?', 1)[0]).strip('/')
            if not init_id:
                self._send_json(404, json.dumps({'error': 'missing initiative id'}))
                return
            if not PORTFOLIO_PATH.exists():
                self._send_json(404, json.dumps({'error': f'initiative {init_id} not found (no portfolio.json)'}))
                return
            data = json.loads(PORTFOLIO_PATH.read_text(encoding='utf-8'))
            found, team_name = None, None
            for team in data.get('teams', []):
                for it in team.get('initiatives', []):
                    if it.get('id') == init_id:
                        found, team_name = it, team.get('name')
                        break
                if found:
                    break
            if not found:
                self._send_json(404, json.dumps({'error': f'initiative {init_id} not found'}))
                return

            tickets = self._load_tickets() or []
            today = datetime.now(WIB).strftime('%Y-%m-%d')
            prio_rank = {'P0': 0, 'P1': 1, 'P2': 2}

            def _sort_key(t):
                due = t.get('due') or ''
                return (0 if t.get('status') == 'blocked' else 1,
                        0 if (due and due < today) else 1,
                        due or '9999-12-31',
                        prio_rank.get(t.get('priority'), 9))

            by_parent = {}
            for t in tickets:
                pid = t.get('parent_id')
                if pid:
                    by_parent.setdefault(pid, []).append(t)

            top_level = [t for t in tickets if t.get('initiative_id') == init_id and not t.get('parent_id')]
            result_tickets = []
            for t in sorted(top_level, key=_sort_key):
                row = dict(t)
                row['children'] = sorted(by_parent.get(t.get('id'), []), key=_sort_key)
                result_tickets.append(row)

            open_states = ('todo', 'in_progress', 'blocked', 'waiting')
            linked = [t for t in tickets if t.get('initiative_id') == init_id]
            counts = {
                'open': sum(1 for t in linked if t.get('status') in open_states),
                'done': sum(1 for t in linked if t.get('status') == 'done'),
                'blocked': sum(1 for t in linked if t.get('status') == 'blocked'),
                'total': len(linked),
            }

            def _match(tproj, name):
                tp, nm = (tproj or '').lower().strip(), (name or '').lower().strip()
                return bool(tp) and (tp == nm or tp in nm or nm in tp)
            unlinked_hint = sum(1 for t in tickets if not t.get('initiative_id') and
                                (_match(t.get('project'), team_name) or _match(t.get('project'), found.get('name'))))

            self._send_json(200, json.dumps({
                'initiative': {
                    'id': found.get('id'), 'name': found.get('name'), 'team': team_name,
                    'health': found.get('health'),
                    'summary': found.get('now') or found.get('one_liner'),
                    'blockers': found.get('blockers', []),
                },
                'tickets': result_tickets,
                'counts': counts,
                'unlinked_hint': unlinked_hint,
                'note': None,
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build initiative detail', 'details': str(e)}))

    def _load_tickets(self):
        if not TICKETS_PATH.exists():
            return None
        return json.loads(TICKETS_PATH.read_text(encoding='utf-8')).get('tickets', [])

    def _handle_get_slack_channels(self):
        """Channel-name -> ID map (merged from the two connector registries) + team id,
        so the frontend can render Slack deep links (app.slack.com/client/<team>/<id>)."""
        try:
            channels = {}
            mgr = BASE_DIR / '.agent' / 'skills' / 'slack-channel-manager' / 'channels.json'
            if mgr.exists():
                for cid, name in json.loads(mgr.read_text(encoding='utf-8')).get('work', {}).items():
                    channels[name.lstrip('#')] = cid
            trk = BASE_DIR / '.agent' / 'skills' / 'slack-tracker' / 'channels.json'
            if trk.exists():
                for group in json.loads(trk.read_text(encoding='utf-8')).get('work', {}).values():
                    for ch in group:
                        channels.setdefault(ch['name'].lstrip('#'), ch['id'])
            self._send_json(200, json.dumps({'team_id': 'TT28HE9SR', 'channels': channels}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read slack channels', 'details': str(e)}))

    def _handle_get_activity_spark(self):
        """Events per day (last 14 days, WIB) from the activity log, for the header sparkline."""
        try:
            from datetime import datetime, timedelta, timezone
            wib = timezone(timedelta(hours=7))
            today = datetime.now(wib).date()
            days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
            counts = {d: 0 for d in days}
            log = BASE_DIR / 'journal' / 'activity_log.jsonl'
            if log.exists():
                for line in log.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line).get('ts_wib', '')[:10]
                    except json.JSONDecodeError:
                        continue
                    if d in counts:
                        counts[d] += 1
            self._send_json(200, json.dumps({'days': [{'date': d, 'count': counts[d]} for d in days]}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build activity spark', 'details': str(e)}))

    def _tracker_payload(self):
        """Shared payload for /api/tracker and /api/overview (behavior identical)."""
        tickets = self._load_tickets()
        if tickets is None:
            return {'tickets': [], 'counts': {},
                    'note': 'No tickets.json yet. Run the tracker migration / /daily-update.'}
        open_states = ('todo', 'in_progress', 'blocked', 'waiting')
        rank = {'P0': 0, 'P1': 1, 'P2': 2}
        order = {'blocked': 0, 'in_progress': 1, 'todo': 2, 'waiting': 3, 'done': 4}
        tickets_sorted = sorted(
            tickets, key=lambda t: (order.get(t.get('status'), 9), rank.get(t.get('priority'), 9), t.get('id', '')))
        today = datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m-%d')
        is_open = lambda t: t.get('status') in open_states
        counts = {
            'open': sum(1 for t in tickets if is_open(t)),
            'p0_open': sum(1 for t in tickets if is_open(t) and t.get('priority') == 'P0'),
            'i_owe_p0': sum(1 for t in tickets if t.get('kind') == 'self' and t.get('status') in ('todo', 'in_progress') and t.get('priority') == 'P0'),
            'waiting_on_others': sum(1 for t in tickets if t.get('kind') in ('delegated', 'outbound') and t.get('status') != 'done'),
            'blocked': sum(1 for t in tickets if t.get('status') == 'blocked'),
            'in_progress': sum(1 for t in tickets if t.get('status') == 'in_progress'),
            'due_today': sum(1 for t in tickets if is_open(t) and t.get('due') == today),
            'overdue': sum(1 for t in tickets if is_open(t) and t.get('due') and t.get('due') < today),
            'done': sum(1 for t in tickets if t.get('status') == 'done'),
        }
        return {'tickets': tickets_sorted, 'counts': counts, 'today': today}

    def _handle_get_tracker(self):
        """Linear-style ticket list + actionable top-bar counts, from tickets.json."""
        try:
            self._send_json(200, json.dumps(self._tracker_payload()))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read tracker', 'details': str(e)}))

    def _handle_get_followups(self):
        """Three actionable follow-up groups from tickets.json."""
        try:
            tickets = self._load_tickets() or []
            groups = {
                'i_owe': [t for t in tickets if t.get('kind') == 'self' and t.get('status') in ('todo', 'in_progress', 'blocked')],
                'they_owe_me': [t for t in tickets if t.get('kind') == 'delegated' and t.get('status') != 'done'],
                'waiting_reply': [t for t in tickets if t.get('kind') == 'outbound' and t.get('status') != 'done'],
            }
            self._send_json(200, json.dumps(groups))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read followups', 'details': str(e)}))

    def _handle_get_insights(self):
        """Cached meeting takeaways + action items (built by build_insights.py via GLM)."""
        try:
            if INSIGHTS_PATH.exists():
                self._send_json(200, INSIGHTS_PATH.read_text(encoding='utf-8'))
            else:
                self._send_json(200, json.dumps({'meetings': [],
                                                 'note': 'No insights cache yet. Run: python3 .agent/scripts/build_insights.py'}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read insights', 'details': str(e)}))

    def _handle_get_meetings(self):
        """Insights tab: recent meetings from journal/fathom_registry.json (structured)."""
        try:
            path = BASE_DIR / 'journal' / 'fathom_registry.json'
            rows = []
            if path.exists():
                reg = json.loads(path.read_text(encoding='utf-8'))
                items = reg.values() if isinstance(reg, dict) else reg
                for r in items:
                    rows.append({
                        'date': r.get('date_wib', ''), 'time': r.get('time_wib', ''),
                        'meeting': r.get('matched_meeting') or r.get('raw_title', '(untitled)'),
                        'client': r.get('client', ''), 'project': r.get('project', ''),
                        'duration': r.get('duration', ''), 'url': r.get('fathom_url', ''),
                    })
            rows.sort(key=lambda x: (x['date'], x['time']), reverse=True)
            # Dedupe the same meeting captured twice: Fathom + the Vexa/local bot
            # land as SEPARATE registry entries (same WIB date + title, start
            # within minutes, one usually missing fathom_url). Rows merge into
            # one: url from whichever capture has it, longest duration wins.
            # Same-title meetings >20 min apart stay separate (a real re-run).
            def _mins(t):
                try:
                    h, m = str(t).split(':')[:2]
                    return int(h) * 60 + int(m)
                except (ValueError, TypeError):
                    return None

            def _dur_min(d):
                m = re.search(r'\d+', str(d or ''))
                return int(m.group()) if m else 0

            def _tkey(s):
                return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()

            deduped = []
            for r in rows:
                twin = next((k for k in deduped
                             if k['date'] == r['date'] and _tkey(k['meeting']) == _tkey(r['meeting'])
                             and _mins(k['time']) is not None and _mins(r['time']) is not None
                             and abs(_mins(k['time']) - _mins(r['time'])) <= 20), None)
                if twin is None:
                    deduped.append(r)
                    continue
                if r.get('url') and not twin.get('url'):
                    twin['url'] = r['url']
                if _dur_min(r.get('duration')) > _dur_min(twin.get('duration')):
                    twin['duration'] = r['duration']
            self._send_json(200, json.dumps({'meetings': deduped[:25]}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read meetings', 'details': str(e)}))

    def _handle_get_changes(self):
        """Changes tab: recent git commits + files changed (always fresh, no daily-update dependency)."""
        import subprocess
        try:
            log = subprocess.run(['git', 'log', '-15', '--pretty=format:%h\t%ad\t%s', '--date=format:%Y-%m-%d %H:%M'],
                                 cwd=str(BASE_DIR), capture_output=True, text=True, timeout=15).stdout
            commits = []
            for line in log.splitlines():
                parts = line.split('\t', 2)
                if len(parts) == 3:
                    commits.append({'hash': parts[0], 'date': parts[1], 'subject': parts[2]})
            changed = subprocess.run(['git', 'diff', '--stat', 'HEAD~5', 'HEAD'],
                                     cwd=str(BASE_DIR), capture_output=True, text=True, timeout=15).stdout
            self._send_json(200, json.dumps({'commits': commits, 'recent_files_stat': changed.strip()[:2000]}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read git changes', 'details': str(e)}))

    def _handle_get_slack_harvest(self):
        """Slack tab: the Slack section from the latest daily_update_*.md harvest."""
        try:
            files = [BASE_DIR / 'daily_update_evening.md', BASE_DIR / 'daily_update_morning.md']
            files = [f for f in files if f.exists()]
            if not files:
                self._send_json(200, json.dumps({'content': '', 'note': 'No daily_update harvest file yet.'}))
                return
            latest = max(files, key=lambda f: f.stat().st_mtime)
            text = latest.read_text(encoding='utf-8')
            lines = text.splitlines()
            # extract from the first "## Slack" header to the next "## " header
            out, capture = [], False
            for ln in lines:
                if ln.startswith('## Slack'):
                    capture = True
                elif ln.startswith('## ') and capture:
                    break
                if capture:
                    out.append(ln)
            mtime = datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
            self._send_json(200, json.dumps({'content': '\n'.join(out), 'source': latest.name, 'lastModified': mtime}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read slack harvest', 'details': str(e)}))

    def _handle_get_active_projects(self):
        """Serve the curated active-projects markdown (journal/active_projects.md)."""
        try:
            if ACTIVE_PROJECTS_PATH.exists():
                content = ACTIVE_PROJECTS_PATH.read_text(encoding='utf-8')
                last_modified = datetime.fromtimestamp(ACTIVE_PROJECTS_PATH.stat().st_mtime).isoformat()
                self._send_json(200, json.dumps({'content': content, 'lastModified': last_modified}))
            else:
                self._send_json(200, json.dumps({'content': '', 'lastModified': None,
                                                 'note': 'journal/active_projects.md not found'}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read active projects', 'details': str(e)}))

    def _heartbeat_latest(self):
        """Latest heartbeat row per job (append-order file -> last match wins).
        Shared by /api/routines, /api/harness-map, run-job/ack-job state joins."""
        latest = {}
        if HEARTBEAT_PATH.exists():
            for line in HEARTBEAT_PATH.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                latest[r.get('job')] = r
        return latest

    def _job_acks(self):
        """job -> epoch of the manual 'Ack' click (journal/state/job_acks.json)."""
        if not JOB_ACKS_PATH.exists():
            return {}
        try:
            return json.loads(JOB_ACKS_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}

    @staticmethod
    def _fail_acked(job, hb_row, acks):
        """The canonical ack-vs-fail-ts join: True iff this job's manual ack epoch
        landed at/after the failing heartbeat row's own ts. A NEWER failure after
        the ack makes the job live again. Only meaningful for a failing row —
        callers decide the row is failing first."""
        try:
            fail_ts = datetime.fromisoformat(hb_row.get('ts_wib')).timestamp()
        except Exception:
            return False
        ack_ts = acks.get(job)
        return ack_ts is not None and ack_ts >= fail_ts

    def _job_verdict(self, job, latest_hb, acks):
        """(status, summary) for a job's latest heartbeat row, collapsed to the
        harness-map's 4-state vocabulary: 'ok' | 'warn' (needs_reauth OR an
        acked failure) | 'fail' (unacked failure) | 'idle' (no heartbeat row —
        honesty rule: unknown is never fabricated green)."""
        r = latest_hb.get(job)
        if not r:
            return 'idle', None
        status = str(r.get('status', 'ok')).lower()
        is_ok = status in ('ok', 'success', 'done')
        needs_reauth = bool(r.get('needs_reauth'))
        summary = r.get('summary')
        if is_ok:
            return ('warn' if needs_reauth else 'ok'), summary
        return ('warn' if self._fail_acked(job, r, acks) else 'fail'), summary

    @staticmethod
    def _age_state(age_h, warn_h, dead_mult=3):
        """Generic 3-tier freshness verdict from an age in hours: ok / warn / fail.
        'idle' is for the caller to return when age_h itself is unknown (no signal),
        never invented here — the honesty rule lives at the call site."""
        if age_h is None:
            return 'idle'
        if age_h <= warn_h:
            return 'ok'
        if age_h <= warn_h * dead_mult:
            return 'warn'
        return 'fail'

    def _latest_activity_ts(self, keywords):
        """Epoch ts of the most recent activity_log event whose action or summary
        contains any of `keywords` (case-insensitive) — cheap proxy for Claude-session
        outputs (mom / weekly-report) that have no dedicated state file of their own."""
        if not ACTIVITY_LOG_PATH.exists():
            return None
        latest = None
        for line in ACTIVITY_LOG_PATH.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            hay = f"{e.get('action', '')} {e.get('summary', '')}".lower()
            if any(k in hay for k in keywords):
                try:
                    ts = datetime.fromisoformat(e.get('ts_wib')).timestamp()
                except Exception:
                    continue
                if latest is None or ts > latest:
                    latest = ts
        return latest

    def _handle_get_routines(self):
        """Intended scheduled routines + their last run (from the heartbeat log) +
        a state-aware verdict: 'ok' | 'fail' | 'reauth' | 'no-data'. 'reauth' is its
        own state (status=ok but needs_reauth=true) — NEVER folded into 'fail'.
        'acked' is only meaningful for state='fail': true once a manual Ack
        (journal/state/job_acks.json) landed at/after that failing row's own ts —
        a NEW failure after the ack makes it live again.
        The payload also carries the raw top-level ack map (acks: {job: epoch})
        so the client can apply the SAME ack-vs-fail-ts join to heartbeat-only
        jobs (e.g. vexa-bots) that have no registered routine entry."""
        try:
            routines = []
            if ROUTINES_PATH.exists():
                routines = json.loads(ROUTINES_PATH.read_text(encoding='utf-8')).get('routines', [])
            last = self._heartbeat_latest()
            acks = self._job_acks()
            for r in routines:
                lr = last.get(r.get('job'))
                r['last_run'] = lr
                if not lr:
                    r['state'] = 'no-data'
                    r['acked'] = False
                    continue
                status = str(lr.get('status', 'ok')).lower()
                is_ok = status in ('ok', 'success', 'done')
                needs_reauth = bool(lr.get('needs_reauth'))
                if is_ok and needs_reauth:
                    r['state'] = 'reauth'
                    r['acked'] = False
                elif is_ok:
                    r['state'] = 'ok'
                    r['acked'] = False
                else:
                    r['state'] = 'fail'
                    r['acked'] = self._fail_acked(r.get('job'), lr, acks)
            self._send_json(200, json.dumps({'routines': routines, 'acks': acks}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read routines', 'details': str(e)}))

    def _handle_post_run_job(self):
        """POST /api/run-job {job} — whitelisted manual trigger (JOB_RUN_MAP). Acquires
        the SAME flock crontab uses (non-blocking) so a manual click can never race the
        real cron firing concurrently -> 409 if already running. 180s timeout; returns
        the combined stdout+stderr tail (last 25 lines) + rc + elapsed seconds regardless
        of success/failure — the caller (tab-system.js) decides how to render it."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            job = (body.get('job') or '').strip()
            if job == 'mention-ledger':
                self._send_json(400, json.dumps({
                    'error': 'mention-ledger is not manually triggerable',
                    'note': 'it already sweeps every 3-4 min via cron — a manual run would '
                             'race the next scheduled tick for no benefit',
                }))
                return
            entry = JOB_RUN_MAP.get(job)
            if not entry:
                self._send_json(404, json.dumps({
                    'error': f'unknown job {job!r}', 'allowed': sorted(JOB_RUN_MAP.keys()),
                }))
                return
            cmd = ['flock', '-n', '-E', str(LOCK_CONFLICT_CODE), entry['lock']] + entry['argv']
            t0 = time.time()
            timed_out = False
            try:
                proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True,
                                      text=True, timeout=180)
                out = (proc.stdout or '') + (proc.stderr or '')
                rc = proc.returncode
            except subprocess.TimeoutExpired as e:
                out = (e.stdout or '') + (e.stderr or '')
                rc = -1
                timed_out = True
            took_s = round(time.time() - t0, 1)
            if rc == LOCK_CONFLICT_CODE:
                self._send_json(409, json.dumps({'error': 'already running'}))
                return
            tail = out.splitlines()[-25:]
            result = {'ok': rc == 0, 'rc': rc, 'tail': tail, 'took_s': took_s}
            if timed_out:
                result['note'] = 'timed out after 180s (job may still be running in the background)'
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'run-job failed', 'details': str(e)}))

    def _handle_post_ack_job(self):
        """POST /api/ack-job {job} — records 'You has seen this failure' as an epoch
        timestamp (atomic .tmp+replace). /api/routines then reports acked:true for that
        job as long as no NEWER failure has landed since."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            job = (body.get('job') or '').strip()
            if not job:
                self._send_json(400, json.dumps({'error': 'missing job'}))
                return
            acks = self._job_acks()
            acks[job] = time.time()
            JOB_ACKS_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(JOB_ACKS_PATH) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(acks, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, JOB_ACKS_PATH)
            self._send_json(200, json.dumps({'ok': True, 'job': job, 'ts': acks[job]}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'ack-job failed', 'details': str(e)}))

    def _handle_get_heartbeat(self):
        """Serve recent routine/agent heartbeat rows (observability for scheduled jobs)."""
        try:
            rows = []
            if HEARTBEAT_PATH.exists():
                for line in HEARTBEAT_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            # latest status per job + the last 50 rows
            latest = {}
            for r in rows:
                latest[r.get('job', '?')] = r
            self._send_json(200, json.dumps({
                'latest': list(latest.values()),
                'recent': rows[-50:],
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read heartbeat', 'details': str(e)}))

    def _handle_get_recorder(self):
        """Meeting-capture pipeline: Vexa bot sends + local recorder runs + resulting MOM files."""
        try:
            out = {'vexa': [], 'local': [], 'moms': []}
            vexa_path = RECORDER_DIR / 'vexa_state.json'
            if vexa_path.exists():
                meetings = json.loads(vexa_path.read_text(encoding='utf-8')).get('meetings', {})
                for key, m in meetings.items():
                    status = str(m.get('status', ''))
                    out['vexa'].append({
                        'key': key, 'platform': key.split('/')[0],
                        'title': m.get('title', '(untitled)'),
                        'sent_at': m.get('sent_at', ''), 'status': status,
                        'ok': 'fail' not in status.lower(),
                    })
                out['vexa'].sort(key=lambda x: x['sent_at'], reverse=True)
            local_path = RECORDER_DIR / 'state.json'
            if local_path.exists():
                processed = json.loads(local_path.read_text(encoding='utf-8')).get('processed', {})
                for wav, r in processed.items():
                    def _rel(p):
                        if not p:
                            return None
                        try:
                            return str(Path(p).resolve().relative_to(BASE_DIR))
                        except ValueError:
                            return None
                    out['local'].append({
                        'file': Path(wav).name, 'rec_id': r.get('rec_id', ''),
                        'transcript': _rel(r.get('transcript')), 'mom': _rel(r.get('mom')),
                        'status': str(r.get('status', '')), 'ts': r.get('ts', ''),
                    })
                out['local'].sort(key=lambda x: x['ts'], reverse=True)
            # MOM / meeting-notes files across all clients (excluding raw transcripts)
            for meet_dir in CLIENTS_DIR.glob('*/meetings'):
                for f in meet_dir.glob('*.md'):
                    title = f.stem.replace('_', ' ')
                    try:
                        for ln in f.read_text(encoding='utf-8').splitlines()[:5]:
                            if ln.startswith('# '):
                                title = ln[2:].strip()
                                break
                    except Exception:
                        pass
                    out['moms'].append({
                        'name': f.name, 'title': title,
                        'relPath': str(f.relative_to(BASE_DIR)),
                        'client': meet_dir.parent.name,
                        'mtime': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
            out['moms'].sort(key=lambda x: x['mtime'], reverse=True)
            # dedupe re-generated MOMs of the same meeting (title differs only by
            # MOM:/date decoration): newest kept, versions:N added when >1
            deduped, by_key = [], {}
            for m in out['moms']:
                key = _norm_mom_title(m.get('title') or m.get('name') or '')
                if not key:
                    key = m.get('name') or m.get('relPath')
                if key in by_key:
                    by_key[key]['versions'] = by_key[key].get('versions', 1) + 1
                else:
                    by_key[key] = m
                    deduped.append(m)
            out['moms'] = deduped[:40]
            self._send_json(200, json.dumps(out))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read recorder state', 'details': str(e)}))

    def _handle_get_vexa_health(self):
        """Real-time Vexa bot service health: container, API, storage, whisper, live/last meeting."""
        try:
            self._send_json(200, json.dumps(_probe_vexa()))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'vexa health probe failed', 'details': str(e)}))

    def _freshness_payload(self, now=None):
        """Shared freshness verdicts for /api/metrics and /api/overview (behavior identical)."""
        if now is None:
            now = datetime.now(WIB)
        fresh = []
        for label, path, warn_h in [
            ('Dashboard.md', DASHBOARD_PATH, 24),
            ('tickets.json (tracker)', TICKETS_PATH, 24),
            ('portfolio.json', PORTFOLIO_PATH, 48),
            ('insights.json (meeting takeaways)', INSIGHTS_PATH, 96),
            ('fathom_registry.json', FATHOM_REGISTRY_PATH, 48),
            ('daily_update_morning.md', BASE_DIR / 'daily_update_morning.md', 30),
            ('daily_update_evening.md', BASE_DIR / 'daily_update_evening.md', 30),
            ('agy cost summary', AGY_COST_PATH, 96),
        ]:
            if path.exists():
                mt = datetime.fromtimestamp(path.stat().st_mtime, WIB)
                age_h = (now - mt) / timedelta(hours=1)
                fresh.append({'label': label, 'mtime': mt.isoformat(timespec='minutes'),
                              'age_h': round(age_h, 1), 'warn_h': warn_h,
                              'state': 'fresh' if age_h <= warn_h else ('stale' if age_h <= warn_h * 3 else 'dead')})
            else:
                fresh.append({'label': label, 'mtime': None, 'age_h': None, 'warn_h': warn_h, 'state': 'missing'})
        return fresh

    def _handle_get_overview(self):
        """One fetch for the Today tab: shared payload helpers + top-N slices.
        Shape: {generated_wib, today, tracker{counts,top<=8}, waiting{counts,escalations<=6},
        decisions{counts,due<=5}, commitments{counts,due<=5,last_sweep}, premeeting,
        activity(last 10), freshness, heartbeat{ok,fail}}."""
        try:
            now = datetime.now(WIB)
            today = now.strftime('%Y-%m-%d')

            # tracker: top <=8 — overdue oldest-first, then due-today, then open P0s
            trk = self._tracker_payload()
            tickets = trk.get('tickets') or []
            open_states = ('todo', 'in_progress', 'blocked', 'waiting')
            is_open = lambda t: t.get('status') in open_states
            overdue = sorted([t for t in tickets if is_open(t) and t.get('due') and t['due'] < today],
                             key=lambda t: t.get('due') or '')
            due_today = [t for t in tickets if is_open(t) and t.get('due') == today]
            p0 = [t for t in tickets if is_open(t) and t.get('priority') == 'P0']
            top, seen = [], set()
            for t in overdue + due_today + p0:
                tid = t.get('id')
                if tid in seen:
                    continue
                seen.add(tid)
                top.append(t)
                if len(top) >= 8:
                    break

            # waiting: escalations <=6 — breached, or open with <24h left on the SLA
            wai = self._waiting_payload()
            escalations = [it for it in (wai.get('items') or [])
                           if it.get('status') == 'breached' or
                           (it.get('status') == 'open' and it.get('remaining_hours') is not None
                            and it['remaining_hours'] < 24)][:6]

            # decisions / commitments: open items due-first (payload lists are pre-sorted)
            dec = self._decisions_payload()
            dec_due = [it for it in (dec.get('items') or []) if it.get('status') == 'open'][:5]
            dec_counts = dict(dec.get('counts') or {})
            dec_counts['due'] = sum(1 for it in (dec.get('items') or [])
                                    if it.get('status') == 'open' and it.get('deadline'))
            com = self._commitments_payload()
            com_due = [it for it in (com.get('items') or []) if it.get('status') == 'open'][:5]
            com_counts = dict(com.get('counts') or {})
            com_counts['due'] = sum(1 for it in (com.get('items') or [])
                                    if it.get('status') == 'open' and it.get('due'))

            # meeting_actions: open commitments sourced from a meeting (fathom recording or
            # the local recorder, whichever fired the commitment sweep), surfaced separately
            # since these are meeting-follow-up asks (not necessarily dated 'due' items).
            # 'meeting-local' source.type is landing via a concurrent commitment-sweep change —
            # coded defensively since it may not exist in commitments.json yet.
            seven_days_ago_epoch = now.timestamp() - 7 * 24 * 3600
            meeting_actions = []
            for it in (com.get('items') or []):
                if it.get('status') != 'open':
                    continue
                src = it.get('source') or {}
                stype = src.get('type')
                if stype not in ('fathom', 'meeting-local'):
                    continue
                fs = it.get('first_seen')
                if fs is None or fs < seven_days_ago_epoch:
                    continue
                meeting_actions.append({
                    'id': it.get('id'), 'text': it.get('text'), 'to': it.get('to'),
                    'source_type': stype, 'source_ref': src.get('ref'),
                    'permalink': it.get('permalink'), 'first_seen': fs,
                    'ticket_id': it.get('ticket_id'),
                })
            meeting_actions.sort(key=lambda x: x.get('first_seen') or 0, reverse=True)
            meeting_actions = meeting_actions[:6]

            # last 10 activity events, newest first
            activity = []
            if ACTIVITY_LOG_PATH.exists():
                for line in ACTIVITY_LOG_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        activity.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            activity = list(reversed(activity[-10:]))

            # heartbeat summary (drives the System-tab red dot: fail > 0 = jobs failing).
            # Ack-aware: a failure acked at/after its own ts (job_acks.json) counts as
            # 'acked', NOT 'fail' — same join /api/routines uses, so the red dot / tile
            # never points at a row that renders muted "acked".
            hb = {'ok': 0, 'fail': 0, 'acked': 0}
            if HEARTBEAT_PATH.exists():
                latest = {}
                for line in HEARTBEAT_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        latest[r.get('job', '?')] = r
                    except json.JSONDecodeError:
                        pass
                acks = self._job_acks()
                for job, r in latest.items():
                    ok = str(r.get('status', 'ok')).lower() in ('ok', 'success', 'done')
                    hb['ok' if ok else ('acked' if self._fail_acked(job, r, acks) else 'fail')] += 1

            self._send_json(200, json.dumps({
                'generated_wib': now.isoformat(timespec='seconds'),
                'today': today,
                'tracker': {'counts': trk.get('counts') or {}, 'top': top},
                'waiting': {'counts': wai.get('counts') or {}, 'escalations': escalations,
                            'last_sweep': wai.get('last_sweep')},
                'decisions': {'counts': dec_counts, 'due': dec_due},
                'commitments': {'counts': com_counts, 'due': com_due,
                                'last_sweep': com.get('last_sweep')},
                'meeting_actions': meeting_actions,
                'premeeting': self._premeeting_payload(),
                'activity': activity,
                'freshness': self._freshness_payload(now),
                'heartbeat': hb,
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build overview', 'details': str(e)}))

    def _handle_get_metrics(self):
        """Health tab: output + pipeline metrics for You and the AI harness."""
        try:
            now = datetime.now(WIB)
            today = now.date()
            days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
            d7 = set(days[-7:])
            d30 = set(days)

            # ── activity log aggregates ──
            events = []
            if ACTIVITY_LOG_PATH.exists():
                for line in ACTIVITY_LOG_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            per_day = {d: {'total': 0, 'agent': 0, 'brian': 0} for d in days}
            by_action_7, by_action_30 = {}, {}
            by_actor_7 = {'agent': 0, 'brian': 0}
            for e in events:
                d = (e.get('ts_wib') or '')[:10]
                act = e.get('action', 'other')
                actor = e.get('actor', 'agent')
                if d in per_day:
                    per_day[d]['total'] += 1
                    per_day[d][actor if actor in ('agent', 'brian') else 'agent'] += 1
                if d in d30:
                    by_action_30[act] = by_action_30.get(act, 0) + 1
                if d in d7:
                    by_action_7[act] = by_action_7.get(act, 0) + 1
                    if actor in by_actor_7:
                        by_actor_7[actor] += 1

            # ── ticket throughput ──
            tickets = self._load_tickets() or []
            open_states = ('todo', 'in_progress', 'blocked', 'waiting')
            today_str = today.isoformat()
            done_7d = 0
            for t in tickets:
                for cm in t.get('comments', []):
                    if 'to done' in (cm.get('change') or '') and (cm.get('ts_wib') or '')[:10] in d7:
                        done_7d += 1
                        break
            created_7d = sum(1 for e in events if e.get('action') == 'ticket_create' and (e.get('ts_wib') or '')[:10] in d7)
            overdue = [t for t in tickets if t.get('status') in open_states and t.get('due') and t.get('due') < today_str]
            stale_overdue = sum(1 for t in overdue if (today - datetime.strptime(t['due'], '%Y-%m-%d').date()).days >= 3)
            ticket_stats = {
                'open': sum(1 for t in tickets if t.get('status') in open_states),
                'done_total': sum(1 for t in tickets if t.get('status') == 'done'),
                'done_7d': done_7d, 'created_7d': created_7d,
                'overdue': len(overdue), 'stale_overdue_3d': stale_overdue,
            }

            # ── git output (docs created / revised) ──
            git_stats = {}
            try:
                def _git(*args):
                    return subprocess.run(['git'] + list(args), cwd=str(BASE_DIR),
                                          capture_output=True, text=True, timeout=15).stdout
                git_stats['commits_7d'] = int(_git('rev-list', '--count', '--since=7.days', 'HEAD').strip() or 0)
                added = _git('log', '--since=7.days', '--diff-filter=A', '--name-only', '--pretty=format:', '--', 'Clients')
                revised = _git('log', '--since=7.days', '--diff-filter=M', '--name-only', '--pretty=format:', '--', 'Clients')
                git_stats['docs_created_7d'] = len({f for f in added.splitlines() if f.endswith('.md')})
                git_stats['docs_revised_7d'] = len({f for f in revised.splitlines() if f.endswith('.md')})
            except Exception:
                git_stats = {'commits_7d': 0, 'docs_created_7d': 0, 'docs_revised_7d': 0}

            # ── meeting-capture health ──
            cap = {'vexa_ok_7d': 0, 'vexa_fail_7d': 0, 'local_7d': 0, 'moms_7d': 0}
            vexa_path = RECORDER_DIR / 'vexa_state.json'
            if vexa_path.exists():
                for m in json.loads(vexa_path.read_text(encoding='utf-8')).get('meetings', {}).values():
                    if (m.get('sent_at') or '')[:10] in d7:
                        cap['vexa_fail_7d' if 'fail' in str(m.get('status', '')).lower() else 'vexa_ok_7d'] += 1
            local_path = RECORDER_DIR / 'state.json'
            if local_path.exists():
                for r in json.loads(local_path.read_text(encoding='utf-8')).get('processed', {}).values():
                    if (r.get('ts') or '')[:10] in d7:
                        cap['local_7d'] += 1
            for meet_dir in CLIENTS_DIR.glob('*/meetings'):
                for f in meet_dir.glob('*.md'):
                    if datetime.fromtimestamp(f.stat().st_mtime, WIB).date().isoformat() in d7:
                        cap['moms_7d'] += 1

            # ── data freshness (staleness monitor) ──
            fresh = self._freshness_payload(now)

            # ── routine heartbeat health (ack-aware, same join as /api/overview:
            # an acked failure counts as 'acked', never 'fail') ──
            hb = {'ok': 0, 'fail': 0, 'acked': 0, 'jobs': []}
            if HEARTBEAT_PATH.exists():
                latest = {}
                for line in HEARTBEAT_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        latest[r.get('job', '?')] = r
                    except json.JSONDecodeError:
                        pass
                acks = self._job_acks()
                for job, r in latest.items():
                    ok = str(r.get('status', 'ok')).lower() in ('ok', 'success', 'done')
                    acked = (not ok) and self._fail_acked(job, r, acks)
                    hb['ok' if ok else ('acked' if acked else 'fail')] += 1
                    hb['jobs'].append({'job': job, 'ok': ok, 'acked': acked,
                                       'ts': r.get('ts') or r.get('ts_wib', '')})

            self._send_json(200, json.dumps({
                'generated_wib': now.isoformat(timespec='seconds'),
                'activity': {'per_day': [{'date': d, **per_day[d]} for d in days],
                             'by_action_7d': by_action_7, 'by_action_30d': by_action_30,
                             'by_actor_7d': by_actor_7, 'total_30d': sum(v['total'] for v in per_day.values())},
                'tickets': ticket_stats, 'git': git_stats, 'capture': cap,
                'freshness': fresh, 'heartbeat': hb,
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build metrics', 'details': str(e)}))

    def _handle_get_harness(self):
        """Harness tab: live inventory of the harness (commands, agents, skills, scripts,
        memory, state stores) so the architecture map always reflects the repo."""
        try:
            def _md_desc(f, limit=110):
                try:
                    txt = f.read_text(encoding='utf-8')
                except Exception:
                    return ''
                m = re.search(r'^description:\s*(.+)$', txt, re.M)
                if m:
                    return m.group(1).strip().strip('"')[:limit]
                for ln in txt.splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith(('---', '#')):
                        return ln[:limit]
                    if ln.startswith('# '):
                        return ln[2:][:limit]
                return ''
            commands = sorted([{'name': f.stem, 'desc': _md_desc(f)}
                               for f in (BASE_DIR / '.claude' / 'commands').glob('*.md')], key=lambda x: x['name'])
            agents = sorted([{'name': f.stem, 'desc': _md_desc(f)}
                             for f in (BASE_DIR / '.claude' / 'agents').glob('*.md')], key=lambda x: x['name'])
            skills = sorted([d.name for d in (BASE_DIR / '.agent' / 'skills').iterdir() if d.is_dir()])
            scripts = sorted([f.name for f in (BASE_DIR / '.agent' / 'scripts').iterdir()
                              if f.is_file() and f.suffix in ('.py', '.sh')])
            memory_files = sorted([f.stem for f in MEMORY_DIR.glob('*.md') if f.name != 'MEMORY.md']) if MEMORY_DIR.exists() else []
            hooks = []
            settings = BASE_DIR / '.claude' / 'settings.json'
            if settings.exists():
                try:
                    for event, entries in (json.loads(settings.read_text(encoding='utf-8')).get('hooks') or {}).items():
                        for grp in entries:
                            for h in grp.get('hooks', []):
                                m2 = re.search(r'([\w.-]+\.(?:sh|py))', str(h.get('command', '')))
                                hooks.append({'event': event, 'name': m2.group(1) if m2 else event})
                except Exception:
                    pass
            state_files = []
            for p in [DASHBOARD_PATH, TICKETS_PATH, PORTFOLIO_PATH, INSIGHTS_PATH,
                      FATHOM_REGISTRY_PATH, ACTIVITY_LOG_PATH, HEARTBEAT_PATH,
                      BASE_DIR / 'journal' / 'todo.md', BASE_DIR / 'journal' / 'master_followup_tracker.md']:
                if p.exists():
                    state_files.append({'name': p.name, 'kb': round(p.stat().st_size / 1024, 1)})
            # Health review summary (harness-health skill) — surfaced here, no separate tab
            health_review = {'note': 'No harness_health.json yet. Run: python3 .agent/skills/harness-health/scripts/harness_health.py run'}
            if HARNESS_HEALTH_PATH.exists():
                try:
                    hh = json.loads(HARNESS_HEALTH_PATH.read_text(encoding='utf-8'))
                    findings = hh.get('findings') or []
                    by_sev = {}
                    for fi in findings:
                        sev = fi.get('severity', 'info')
                        by_sev[sev] = by_sev.get(sev, 0) + 1
                    reports = sorted((BASE_DIR / 'journal' / 'harness_health').glob('*.md'))
                    sev_rank = {'fail': 0, 'warn': 1, 'info': 2}
                    findings_sorted = sorted(findings, key=lambda f: sev_rank.get(f.get('severity'), 3))[:40]
                    health_review = {
                        'last_run': hh.get('last_run'),
                        'findings_total': len(findings),
                        'by_severity': by_sev,
                        'latest_report': str(reports[-1].relative_to(BASE_DIR)) if reports else None,
                        'findings': findings_sorted,
                    }
                except Exception as e2:
                    health_review = {'note': f'harness_health.json unreadable: {e2}'}
            self._send_json(200, json.dumps({
                'commands': commands, 'agents': agents, 'skills': skills, 'scripts': scripts,
                'memory_count': len(memory_files), 'memory_files': memory_files,
                'hooks': hooks, 'state_files': state_files,
                'health_review': health_review,
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build harness map', 'details': str(e)}))

    def _handle_get_harness_map(self):
        """GET /api/harness-map — the curated architecture map (Indra input -> Refleks
        cron -> Otak Claude sessions -> Memori state -> Tangan gated actions). Status is
        composed live, server-side, from the cheapest signal already on disk for each
        node (heartbeat verdict for cron jobs, freshness/staleness age for state files,
        activity-log recency for Claude-session outputs). Honesty rule: 'idle' means no
        cheap signal exists yet — never a fabricated green."""
        try:
            now = datetime.now(WIB)
            latest_hb = self._heartbeat_latest()
            acks = self._job_acks()
            fresh_list = self._freshness_payload(now)
            fresh_by_label = {f['label']: f for f in fresh_list}
            FRESH_MAP = {'fresh': 'ok', 'stale': 'warn', 'dead': 'fail', 'missing': 'idle'}

            def job_node(node_id, label, desc, job=None):
                status, _summary = self._job_verdict(job or node_id, latest_hb, acks)
                return {'id': node_id, 'label': label, 'desc': desc, 'status': status,
                        'ref': {'kind': 'job', 'id': job or node_id}}

            def none_node(node_id, label, desc, status='idle'):
                return {'id': node_id, 'label': label, 'desc': desc, 'status': status,
                        'ref': {'kind': 'none', 'id': None}}

            def freshness_node(node_id, label, desc, fresh_label, context):
                f = fresh_by_label.get(fresh_label)
                if not f:
                    return none_node(node_id, label, desc)
                status = FRESH_MAP.get(f.get('state'), 'idle')
                return {'id': node_id, 'label': label, 'desc': desc, 'status': status,
                        'ref': {'kind': 'freshness', 'id': fresh_label, 'age_h': f.get('age_h'),
                                'mtime': f.get('mtime'), 'state': f.get('state'), 'context': context}}

            # ── Indra: input ──
            # slack-sweep: mention_ledger.json's own last_sweep epoch — mention-ledger has
            # no heartbeat integration (JOB_LOG_MAP heartbeat_job=None), so we read the
            # same state-file signal harness-health's own staleness check uses.
            slack_status = 'idle'
            ledger_path = BASE_DIR / 'journal' / 'state' / 'slack_mention_ledger.json'
            if ledger_path.exists():
                try:
                    ls = json.loads(ledger_path.read_text(encoding='utf-8')).get('last_sweep')
                    age_h = (now.timestamp() - float(ls)) / 3600 if ls else None
                    slack_status = self._age_state(age_h, warn_h=1, dead_mult=4)
                except Exception:
                    slack_status = 'idle'
            slack_node = {'id': 'slack-sweep', 'label': 'Slack sweep', 'status': slack_status,
                          'desc': 'Mention/DM ledger sweep, every 30 min',
                          'ref': {'kind': 'job', 'id': 'mention-ledger'}}

            gmail_node = none_node('gmail-sweep', 'Gmail sweep',
                                    'SOP-driven Gmail sweep in morning/evening update — no cron')

            # calendar: piggyback on the maintenance heartbeat's own "X/Y services
            # healthy" ratio text — already-parsed, no separate token probe needed.
            cal_status = 'idle'
            maint_hb = latest_hb.get('maintenance')
            if maint_hb and maint_hb.get('summary'):
                m = re.search(r'(\d+)/(\d+)', maint_hb['summary'])
                if m:
                    x, y = int(m.group(1)), int(m.group(2))
                    cal_status = 'ok' if (y and x == y) else ('warn' if y else 'idle')
            calendar_node = {'id': 'calendar', 'label': 'Calendar', 'status': cal_status,
                              'desc': 'Google Calendar (Work + personal) token health',
                              'ref': {'kind': 'job', 'id': 'maintenance'}}

            meet_status, _ = self._job_verdict('vexa-auto', latest_hb, acks)
            meetings_node = {'id': 'meetings', 'label': 'Meetings (Vexa + Fathom)', 'status': meet_status,
                              'desc': 'Bot auto-join + local recorder + Fathom sync',
                              'ref': {'kind': 'job', 'id': 'vexa-auto'}}

            # jira: freshness of whichever daily_update_*.md is newer (both carry a
            # "## Work Jira Sprint Progress" section) — keep it simple, no separate probe.
            du_candidates = [(BASE_DIR / 'daily_update_morning.md', 'daily_update_morning.md'),
                             (BASE_DIR / 'daily_update_evening.md', 'daily_update_evening.md')]
            du_existing = [(p, lbl) for p, lbl in du_candidates if p.exists()]
            if du_existing:
                p, lbl = max(du_existing, key=lambda x: x[0].stat().st_mtime)
                f = fresh_by_label.get(lbl)
                jira_status = FRESH_MAP.get(f.get('state'), 'idle') if f else 'idle'
                jira_ref = {'kind': 'file', 'id': str(p.relative_to(BASE_DIR))}
            else:
                jira_status, jira_ref = 'idle', {'kind': 'none', 'id': None}
            jira_node = {'id': 'jira', 'label': 'Jira', 'status': jira_status,
                         'desc': 'Sprint progress pulled into the daily harvest', 'ref': jira_ref}

            indra_nodes = [slack_node, gmail_node, calendar_node, meetings_node, jira_node]

            # ── Refleks: cron mekanis ──
            refleks_defs = [
                ('mention-ledger', 'Mention ledger', 'Slack mention/DM ledger sweep, */30 min'),
                ('commitment-ledger', 'Commitment ledger', 'Commitments sweep + extract, 3x/day'),
                ('waiting-watchdog', 'Waiting watchdog', 'Waiting-on SLA watchdog, hourly'),
                ('premeeting-cards', 'Pre-meeting cards', 'Pre-meeting cards, weekdays 12:32 WIB'),
                ('outcomes-loop', 'Outcomes loop', 'Outcomes metrics check, weekly Mon 13:05'),
                ('harness-health', 'Harness health', 'Harness health review, monthly'),
                ('maintenance', 'Maintenance', 'OAuth token refresh sweep, daily 13:00'),
                ('vexa-auto', 'Vexa auto', 'Vexa bot auto-join tick, */5 min'),
                ('dashboard-keepalive', 'Dashboard keepalive', 'Keepalive ping, hourly'),
            ]
            refleks_nodes = []
            for jid, label, desc in refleks_defs:
                if jid == 'mention-ledger':
                    # same state-file signal as the indra slack-sweep node above — no
                    # heartbeat row exists for this job (duplicated verdict is
                    # cheap and keeps this loop uniform with the other 8 jobs).
                    refleks_nodes.append({'id': jid, 'label': label, 'desc': desc,
                                          'status': slack_status, 'ref': {'kind': 'job', 'id': jid}})
                else:
                    refleks_nodes.append(job_node(jid, label, desc))

            # ── Otak: Claude sessions ──
            def du_node(node_id, label, du_label, du_path):
                f = fresh_by_label.get(du_label)
                if not f or not du_path.exists():
                    return none_node(node_id, label, f'{label} briefing — no run yet')
                age_h = f.get('age_h')
                # spec: <=36h ok, else warn (no separate dead tier for these two)
                status = self._age_state(age_h, warn_h=36, dead_mult=1) if age_h is not None else 'idle'
                return {'id': node_id, 'label': label, 'desc': f'{label} briefing', 'status': status,
                        'ref': {'kind': 'file', 'id': str(du_path.relative_to(BASE_DIR))}}

            morning_node = du_node('morning-update', 'Morning update', 'daily_update_morning.md',
                                    BASE_DIR / 'daily_update_morning.md')
            evening_node = du_node('evening-update', 'Evening update', 'daily_update_evening.md',
                                    BASE_DIR / 'daily_update_evening.md')

            def activity_node(node_id, label, desc, keywords, warn_h):
                ts = self._latest_activity_ts(keywords)
                age_h = (now.timestamp() - ts) / 3600 if ts else None
                status = self._age_state(age_h, warn_h=warn_h, dead_mult=4) if age_h is not None else 'idle'
                return {'id': node_id, 'label': label, 'desc': desc, 'status': status,
                        'ref': {'kind': 'none', 'id': None}}

            mom_node = activity_node('mom', 'MOM', 'Meeting minutes, generated per meeting',
                                      ['mom'], warn_h=24 * 7)
            weekly_node = activity_node('weekly-report', 'Weekly report',
                                         'Work weekly report for YourManager, Mon ~09:00 WIB',
                                         ['weekly report', 'weekly-report'], warn_h=24 * 9)
            otak_nodes = [morning_node, evening_node, mom_node, weekly_node]

            # ── Memori: state ──
            hh_staleness = {}
            if HARNESS_HEALTH_PATH.exists():
                try:
                    hh_staleness = {s.get('name'): s for s in
                                     (json.loads(HARNESS_HEALTH_PATH.read_text(encoding='utf-8')).get('staleness') or [])}
                except Exception:
                    hh_staleness = {}

            def staleness_node(node_id, label, desc, name, context):
                s = hh_staleness.get(name)
                if not s:
                    return none_node(node_id, label, desc)
                status = FRESH_MAP.get(s.get('state'), 'idle')
                return {'id': node_id, 'label': label, 'desc': desc, 'status': status,
                        'ref': {'kind': 'freshness', 'id': name, 'age_h': s.get('age_hours'),
                                'mtime': None, 'state': s.get('state'), 'context': context}}

            tickets_node = freshness_node('tickets', 'Tickets', 'Ticket tracker (tickets.json)',
                                           'tickets.json (tracker)',
                                           'Updated by dashboard actions + enrich_tickets.py')
            commitments_node = staleness_node('commitments', 'Commitments', 'Things You owes others',
                                               'commitments', 'Refresh via commitment_ledger.py sweep')
            waiting_node = staleness_node('waiting_on', 'Waiting on', 'Things others owe You',
                                           'waiting_on', 'Refresh via waiting_watchdog.py sweep')
            decisions_node = staleness_node('decisions', 'Decisions', 'Open decision log',
                                             'decisions', 'Captured via decision_log.py — no freshness SLA (exempt)')

            # people.json: no upstream freshness/staleness signal — direct mtime, generous
            # thresholds (roster changes rarely, unlike the minutely/hourly cron ledgers).
            people_status, people_age = 'idle', None
            if PEOPLE_PATH.exists():
                people_age = (now.timestamp() - PEOPLE_PATH.stat().st_mtime) / 3600
                people_status = self._age_state(people_age, warn_h=24 * 7, dead_mult=3)
            people_node = {'id': 'people', 'label': 'People', 'desc': 'Stakeholder roster',
                            'status': people_status,
                            'ref': {'kind': 'freshness', 'id': 'people.json', 'age_h': people_age,
                                    'mtime': None, 'state': None,
                                    'context': 'Refresh via stakeholders.py render --all'}}

            portfolio_node = freshness_node('portfolio', 'Portfolio', 'Team/initiative rollups',
                                             'portfolio.json', 'Refresh via .agent/scripts/portfolio_render.py')
            fathom_node = freshness_node('fathom-registry', 'Fathom registry', 'Recording index',
                                          'fathom_registry.json', 'Refresh via scripts/fathom_registry_sync.py')

            # memory-dir: freshest .md mtime among harness memory files (MEMORY.md index
            # itself excluded — it's the table of contents, not a content update signal).
            mem_status, mem_age = 'idle', None
            if MEMORY_DIR.exists():
                mem_files = [f for f in MEMORY_DIR.glob('*.md') if f.name != 'MEMORY.md']
                if mem_files:
                    newest = max(f.stat().st_mtime for f in mem_files)
                    mem_age = (now.timestamp() - newest) / 3600
                    mem_status = self._age_state(mem_age, warn_h=24 * 14, dead_mult=3)
            memory_node = {'id': 'memory-dir', 'label': 'Memory',
                            'desc': 'Claude harness memory (grows via /learn)', 'status': mem_status,
                            'ref': {'kind': 'freshness', 'id': 'memory-dir', 'age_h': mem_age,
                                    'mtime': None, 'state': None, 'context': 'Grows via the /learn skill'}}

            memori_nodes = [tickets_node, commitments_node, waiting_node, decisions_node,
                             people_node, portfolio_node, fathom_node, memory_node]

            # ── Tangan: gated actions — always 'gated', that IS their status ──
            tangan_defs = [
                ('slack-post', 'Slack post', 'Send as You via slack_client.py — approval-gated'),
                ('gdocs', 'GDocs', 'Create/update Google Docs — approval-gated for client-facing docs'),
                ('calendar-create', 'Calendar create', 'Create/update calendar events — approval-gated'),
                ('jira-create', 'Jira create', 'Create/transition Jira issues — approval-gated'),
                ('whatsapp', 'WhatsApp', 'Send a WhatsApp DM via the wa-for-pm bridge — approval-gated'),
            ]
            tangan_nodes = [{'id': nid, 'label': label, 'desc': desc, 'status': 'gated',
                             'ref': {'kind': 'none', 'id': None}} for nid, label, desc in tangan_defs]

            groups = [
                {'key': 'indra', 'label': 'Indra — input', 'nodes': indra_nodes},
                {'key': 'refleks', 'label': 'Refleks — cron mekanis', 'nodes': refleks_nodes},
                {'key': 'otak', 'label': 'Otak — Claude sessions', 'nodes': otak_nodes},
                {'key': 'memori', 'label': 'Memori — state', 'nodes': memori_nodes},
                {'key': 'tangan', 'label': 'Tangan — aksi (gated)', 'nodes': tangan_nodes},
            ]
            self._send_json(200, json.dumps({'groups': groups}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build harness map', 'details': str(e)}))

    def _handle_get_job_log(self):
        """GET /api/job-log?job=<name> — failing-job drill-down: tail the cron job's log file
        + its most recent agent_heartbeat.jsonl row. Job->log map is hardcoded from the
        authoritative CRON_REGISTRY in harness-health/scripts/harness_health.py."""
        try:
            qs = self.path.split('?', 1)[1] if '?' in self.path else ''
            params = {}
            for part in qs.split('&'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    params[k] = unquote(v)
            job = params.get('job', '')
            entry = JOB_LOG_MAP.get(job)
            if not entry:
                self._send_json(404, json.dumps({'error': f'unknown job {job!r}',
                                                 'known_jobs': sorted(JOB_LOG_MAP.keys())}))
                return
            log_path = Path(entry['log_file'])
            tail, note = [], None
            if log_path.exists():
                try:
                    tail = log_path.read_text(encoding='utf-8', errors='ignore').splitlines()[-40:]
                except Exception as e2:
                    note = f'log unreadable: {e2}'
            else:
                note = 'log file not found'
            last_heartbeat = None
            hb_job = entry.get('heartbeat_job')
            if hb_job and HEARTBEAT_PATH.exists():
                for line in HEARTBEAT_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if r.get('job') == hb_job:
                        last_heartbeat = r  # file is append-order -> last match wins (most recent)
            self._send_json(200, json.dumps({
                'job': job, 'log_file': str(log_path), 'tail': tail,
                'last_heartbeat': last_heartbeat, 'note': note,
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read job log', 'details': str(e)}))

    # ── New-ledger endpoints (decision-log / commitment-ledger / waiting-watchdog /
    #    outcomes-loop / stakeholders / premeeting-cards), Stage B 2026-07-10 ──

    def _load_ledger_state(self, path):
        """Shared reader for journal/state/*.json ledger files. None = file missing."""
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def _decisions_payload(self):
        """Shared payload for /api/decisions and /api/overview (behavior identical)."""
        state = self._load_ledger_state(DECISIONS_PATH)
        if state is None:
            return {'items': [], 'counts': {},
                    'note': 'No decisions.json yet. Capture one via decision_log.py add.'}
        items = list((state.get('items') or {}).values())
        today = datetime.now(WIB).strftime('%Y-%m-%d')
        is_overdue = lambda it: (it.get('status') == 'open' and it.get('deadline') and it['deadline'] < today)
        status_rank = {'open': 0, 'decided': 1, 'superseded': 2}
        items.sort(key=lambda it: (status_rank.get(it.get('status'), 3),
                                   0 if is_overdue(it) else 1,
                                   it.get('deadline') or '9999-12-31', it.get('id', '')))
        counts = {
            'open': sum(1 for it in items if it.get('status') == 'open'),
            'overdue': sum(1 for it in items if is_overdue(it)),
            'decided': sum(1 for it in items if it.get('status') == 'decided'),
        }
        return {'items': items, 'counts': counts, 'today': today}

    def _handle_get_decisions(self):
        """Decisions tab: decision-log ledger (journal/state/decisions.json)."""
        try:
            self._send_json(200, json.dumps(self._decisions_payload()))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read decisions', 'details': str(e)}))

    def _commitments_payload(self):
        """Shared payload for /api/commitments and /api/overview (behavior identical)."""
        state = self._load_ledger_state(COMMITMENTS_PATH)
        if state is None:
            return {'items': [], 'counts': {},
                    'note': 'No commitments.json yet. Run: commitment_ledger.py sweep'}
        items = list((state.get('items') or {}).values())
        for it in items:
            it.setdefault('ticket_id', None)   # uniform shape pre-link (see `link` CLI)
        today = datetime.now(WIB).strftime('%Y-%m-%d')
        is_open = lambda it: it.get('status') == 'open'
        is_overdue = lambda it: (is_open(it) and it.get('due') and it['due'] < today)
        items.sort(key=lambda it: (0 if is_open(it) else 1,
                                   0 if is_overdue(it) else 1,
                                   it.get('due') or '9999-12-31', it.get('id', '')))
        counts = {
            'open': sum(1 for it in items if is_open(it)),
            'overdue': sum(1 for it in items if is_overdue(it)),
            'pending_candidates': len(state.get('pending_candidates') or []),
        }
        return {'items': items, 'counts': counts, 'today': today,
                'last_sweep': state.get('last_sweep')}

    def _handle_get_commitments(self):
        """Ledgers tab: commitment-ledger (journal/state/commitments.json) — things You owes others."""
        try:
            self._send_json(200, json.dumps(self._commitments_payload()))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read commitments', 'details': str(e)}))

    def _waiting_payload(self):
        """Shared payload for /api/waiting-on and /api/overview (behavior identical)."""
        state = self._load_ledger_state(WAITING_ON_PATH)
        if state is None:
            return {'items': [], 'counts': {},
                    'note': 'No waiting_on.json yet. Run: waiting_watchdog.py add'}
        import time as _time
        now = _time.time()
        items = []
        for it in (state.get('items') or {}).values():
            it = dict(it)
            try:
                it['remaining_hours'] = round((float(it.get('since') or now) +
                                               float(it.get('sla_hours') or 0) * 3600 - now) / 3600, 1)
            except (TypeError, ValueError):
                it['remaining_hours'] = None
            items.append(it)
        status_rank = {'breached': 0, 'open': 1, 'answered': 2, 'dropped': 3}
        items.sort(key=lambda it: (status_rank.get(it.get('status'), 9),
                                   it.get('remaining_hours') if it.get('remaining_hours') is not None else 1e9))
        counts = {
            'open': sum(1 for it in items if it.get('status') == 'open'),
            'breached': sum(1 for it in items if it.get('status') == 'breached'),
        }
        return {'items': items, 'counts': counts, 'last_sweep': state.get('last_sweep')}

    def _handle_get_waiting_on(self):
        """Ledgers tab: waiting-watchdog (journal/state/waiting_on.json) — things others owe You."""
        try:
            self._send_json(200, json.dumps(self._waiting_payload()))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read waiting-on', 'details': str(e)}))

    def _handle_post_waiting_add(self):
        """POST /api/waiting-add — one-click 'chase': shells out to the waiting-watchdog CLI
        (single writer for waiting_on.json) so the file stays consistent with the cron sweep,
        rather than the dashboard editing the JSON directly. Body: {owner, what, sla_hours,
        escalate_to?, escalation_path?, source_url?}."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            owner = (body.get('owner') or '').strip()
            what = (body.get('what') or '').strip()
            sla_hours = body.get('sla_hours')
            if not owner or not what or sla_hours in (None, ''):
                self._send_json(400, json.dumps({'error': 'owner, what, sla_hours are required'}))
                return
            try:
                sla_hours = float(sla_hours)
            except (TypeError, ValueError):
                self._send_json(400, json.dumps({'error': 'sla_hours must be a number'}))
                return
            # dedupe guard (chase double-fire): if an open/breached item already tracks
            # the same owner + essentially the same ask (>=60% token overlap on `what`),
            # refuse with the existing id instead of minting a duplicate escalation.
            wstate = self._load_ledger_state(WAITING_ON_PATH) or {}
            owner_slug = _resolve_person_slug(owner)
            for it in (wstate.get('items') or {}).values():
                if it.get('status') not in ('open', 'breached'):
                    continue
                if it.get('owner_slug') != owner_slug:
                    continue
                if _token_overlap(what, it.get('what')) >= 0.6:
                    self._send_json(409, json.dumps({'error': 'already chasing',
                                                     'id': it.get('id')}))
                    return
            cmd = ['python3', '.agent/skills/waiting-watchdog/scripts/waiting_watchdog.py', 'add',
                   '--owner', owner, '--what', what, '--sla-hours', str(sla_hours)]
            if body.get('escalate_to'):
                cmd += ['--escalate-to', str(body['escalate_to'])]
            if body.get('escalation_path'):
                cmd += ['--escalation-path', str(body['escalation_path'])]
            if body.get('source_url'):
                cmd += ['--source', str(body['source_url'])]
            proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                self._send_json(500, json.dumps({'error': 'waiting_watchdog add failed',
                                                 'details': (proc.stderr or proc.stdout or '')[:400]}))
                return
            m = re.search(r'\b(WAIT-\d+)\b', proc.stdout or '')
            if not m:
                self._send_json(500, json.dumps({'error': 'could not parse new WAIT id from CLI output',
                                                 'details': (proc.stdout or '')[:400]}))
                return
            self._send_json(200, json.dumps({'ok': True, 'id': m.group(1)}))
        except subprocess.TimeoutExpired:
            self._send_json(500, json.dumps({'error': 'waiting_watchdog add timed out'}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'waiting-add failed', 'details': str(e)}))

    def _handle_get_outcomes(self):
        """Ledgers tab: outcomes-loop (journal/state/outcomes.json) — shipped features vs success metrics."""
        try:
            state = self._load_ledger_state(OUTCOMES_PATH)
            if state is None:
                self._send_json(200, json.dumps({'features': [], 'needs_reauth': False,
                                                 'note': 'No outcomes.json yet. Run: outcomes_loop.py add-feature'}))
                return
            features = list((state.get('features') or {}).values())
            features.sort(key=lambda f: (0 if f.get('status') == 'active' else 1, f.get('shipped_on') or ''), reverse=False)
            self._send_json(200, json.dumps({'features': features,
                                             'needs_reauth': bool(state.get('needs_reauth')),
                                             'last_check': state.get('last_check')}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read outcomes', 'details': str(e)}))

    def _handle_get_stakeholders(self):
        """People tab: glob Clients/Work/People/*.md joined with people.json roster +
        live open-item counts per slug from the three sibling ledgers."""
        try:
            roster = {}
            if PEOPLE_PATH.exists():
                roster = (json.loads(PEOPLE_PATH.read_text(encoding='utf-8')).get('people') or {})
            commitments = self._load_ledger_state(COMMITMENTS_PATH) or {}
            waiting = self._load_ledger_state(WAITING_ON_PATH) or {}
            decisions = self._load_ledger_state(DECISIONS_PATH) or {}
            com_items = list((commitments.get('items') or {}).values())
            wait_items = list((waiting.get('items') or {}).values())
            dec_items = list((decisions.get('items') or {}).values())
            pages = {f.name: f for f in PEOPLE_DIR.glob('*.md')} if PEOPLE_DIR.exists() else {}
            people = []
            for slug, p in roster.items():
                page = pages.pop(p.get('page') or '', None)
                people.append({
                    'slug': slug, 'name': p.get('name'), 'role': p.get('role'),
                    'team': p.get('team'), 'slack_id': p.get('slack_id'),
                    'page': p.get('page'),
                    'relPath': str(page.relative_to(BASE_DIR)) if page else None,
                    'page_mtime': datetime.fromtimestamp(page.stat().st_mtime).isoformat() if page else None,
                    'open_commitments': sum(1 for it in com_items
                                            if it.get('status') == 'open' and it.get('to_slug') == slug),
                    'waiting_on': sum(1 for it in wait_items
                                      if it.get('status') in ('open', 'breached') and it.get('owner_slug') == slug),
                    'open_decisions': sum(1 for it in dec_items
                                          if it.get('status') == 'open' and
                                          (it.get('decider_slug') == slug or slug in (it.get('stakeholder_slugs') or []))),
                })
            # pages on disk that aren't in the roster (orphans — surfaced, not hidden)
            for name, f in sorted(pages.items()):
                people.append({'slug': None, 'name': f.stem.replace('_', ' '), 'role': None, 'team': None,
                               'slack_id': None, 'page': name,
                               'relPath': str(f.relative_to(BASE_DIR)),
                               'page_mtime': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                               'open_commitments': 0, 'waiting_on': 0, 'open_decisions': 0})
            people.sort(key=lambda x: (-(x['open_commitments'] + x['waiting_on'] + x['open_decisions']),
                                       x['name'] or ''))
            note = None
            if not roster:
                note = 'No people.json roster yet. Run: stakeholders.py list (bootstraps the roster).'
            self._send_json(200, json.dumps({'people': people, 'note': note}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read stakeholders', 'details': str(e)}))

    def _premeeting_payload(self):
        """Shared payload for /api/premeeting and /api/overview (behavior identical)."""
        today = datetime.now(WIB).strftime('%Y-%m-%d')
        day_dir = PREMEETING_DIR / today
        meta = {}
        if PREMEETING_STATE_PATH.exists():
            try:
                meta = ((json.loads(PREMEETING_STATE_PATH.read_text(encoding='utf-8'))
                         .get('dates') or {}).get(today) or {})
            except Exception:
                meta = {}
        cards = []
        if day_dir.exists():
            by_file = {c.get('file'): c for c in (meta.get('cards') or []) if isinstance(c, dict)}
            for f in sorted(day_dir.glob('*.md')):
                title = f.stem
                try:
                    for ln in f.read_text(encoding='utf-8').splitlines()[:5]:
                        if ln.startswith('# '):
                            title = ln[2:].strip()
                            break
                except Exception:
                    pass
                row = {'file': f.name, 'title': title,
                       'relPath': str(f.relative_to(BASE_DIR))}
                extra = by_file.get(f.name) or by_file.get(str(f.relative_to(BASE_DIR)))
                if extra:
                    for k in ('time_wib', 'attendee_slugs', 'n_decisions', 'n_pings',
                              'n_you_owe', 'n_they_owe', 'n_tickets', 'has_last_meeting'):
                        if k in extra:
                            row[k] = extra[k]
                cards.append(row)
        note = None
        if not cards:
            note = (f'No pre-meeting cards for {today} yet. '
                    'Run: python3 .agent/skills/premeeting-cards/scripts/premeeting_cards.py generate')
        return {'date': today, 'cards': cards,
                'last_run': meta.get('generated_at') or None, 'note': note}

    def _handle_get_premeeting(self):
        """Decisions tab (cards strip): today's pre-meeting cards from journal/premeeting/<date>/."""
        try:
            self._send_json(200, json.dumps(self._premeeting_payload()))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to read premeeting cards', 'details': str(e)}))

    # ── AI task runner + briefing + progress (E1 dashboard v4, 2026-07-11) ──

    def _handle_post_ai_task(self):
        """POST /api/ai-task {kind, ref} — spawn a DETACHED headless `claude -p` run
        (stdout+stderr -> journal/ai_runs/<id>.log, sentinel 'AI_TASK_DONE rc=N').
        Guards: max 2 running; one per (kind,ref). Returns {ok, id} immediately."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            kind = (body.get('kind') or '').strip()
            ref = (body.get('ref') or '').strip()
            if kind not in AI_TASK_KINDS:
                self._send_json(400, json.dumps({'error': f'unknown kind {kind!r}',
                                                 'allowed': list(AI_TASK_KINDS)}))
                return
            if kind == 'verify-commitments':
                ref = 'all'
            if kind == 'ping' and not ref:
                ref = 'ping'
            if not ref:
                self._send_json(400, json.dumps({'error': 'missing ref'}))
                return

            # validate the ref / build the spec FIRST so a bad ref is always a 400,
            # even when the runner is at capacity
            try:
                prompt, tools, model, expected_result = _ai_task_spec(kind, ref)
            except ValueError as ve:
                self._send_json(400, json.dumps({'error': str(ve)}))
                return
            except Exception as se:
                self._send_json(500, json.dumps({'error': 'failed to build task spec',
                                                 'details': str(se)}))
                return

            # concurrency guard (stale >45min runs stop blocking the slots)
            now = time.time()
            running = [m for m in _ai_runs_all() if m.get('status') == 'running'
                       and (now - (m.get('started_epoch') or 0)) < AI_TASK_STALE_MIN * 60]
            dup = next((m for m in running if m.get('kind') == kind and m.get('ref') == ref), None)
            if dup:
                self._send_json(409, json.dumps({'error': 'already running for this kind+ref',
                                                 'id': dup.get('id')}))
                return
            if len(running) >= AI_TASK_MAX_RUNNING:
                self._send_json(409, json.dumps({
                    'error': f'max {AI_TASK_MAX_RUNNING} ai-tasks already running',
                    'running': [m.get('id') for m in running]}))
                return

            AI_RUNS_DIR.mkdir(parents=True, exist_ok=True)
            AI_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
            epoch = int(now)
            while (AI_RUNS_DIR / f'air-{epoch}-{kind}.json').exists():
                epoch += 1   # same-second same-kind spawn: keep ids unique, format stable
            run_id = f'air-{epoch}-{kind}'
            log_path = AI_RUNS_DIR / f'{run_id}.log'
            meta_path = AI_RUNS_DIR / f'{run_id}.json'

            # --output-format json: stdout ends with ONE JSON result object carrying
            # usage + total_cost_usd; the finalizer parses it into the meta
            # (tokens_in/tokens_out/cost_usd). Old text runs simply lack the fields.
            argv = [_claude_bin(), '-p', prompt, '--model', model,
                    '--output-format', 'json']
            if tools:
                argv += ['--allowedTools', tools]
            # sentinel via sh wrapper: completion + rc derivable from the log alone
            shell_cmd = shlex.join(argv) + '; echo AI_TASK_DONE rc=$?'
            log_fh = open(log_path, 'w', encoding='utf-8')
            try:
                proc = subprocess.Popen(
                    ['sh', '-c', shell_cmd], cwd=str(BASE_DIR),
                    stdout=log_fh, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, start_new_session=True, env=_ai_env())
            finally:
                log_fh.close()   # child holds its own fd; parent must not leak one per run

            meta = {'id': run_id, 'kind': kind, 'ref': ref, 'status': 'running',
                    'started_wib': datetime.now(WIB).isoformat(timespec='seconds'),
                    'started_epoch': now, 'pid': proc.pid, 'model': model,
                    'allowed_tools': tools, 'expected_result': expected_result,
                    'log': str(log_path.relative_to(BASE_DIR))}
            tmp = str(meta_path) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, meta_path)
            self._send_json(200, json.dumps({'ok': True, 'id': run_id}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'ai-task spawn failed', 'details': str(e)}))

    def _handle_get_ai_task(self):
        """GET /api/ai-task?id=<id> -> one run's status + last 30 log lines.
        GET /api/ai-task?list=1 -> last 10 runs (meta only)."""
        try:
            qs = self.path.split('?', 1)[1] if '?' in self.path else ''
            params = {}
            for part in qs.split('&'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    params[k] = unquote(v)
            if params.get('list'):
                runs = []
                for m in _ai_runs_all()[:10]:
                    runs.append({k: m.get(k) for k in
                                 ('id', 'kind', 'ref', 'status', 'started_wib',
                                  'finished_wib', 'rc', 'result_path', 'model',
                                  'tokens_in', 'tokens_out', 'cost_usd')})
                self._send_json(200, json.dumps({'runs': runs}))
                return
            run_id = (params.get('id') or '').strip()
            if not re.match(r'^air-\d+-[a-z-]+$', run_id):
                self._send_json(400, json.dumps({'error': 'missing or malformed id'}))
                return
            meta_path = AI_RUNS_DIR / f'{run_id}.json'
            if not meta_path.exists():
                self._send_json(404, json.dumps({'error': f'run {run_id} not found'}))
                return
            m = _ai_run_read(meta_path)
            if not m:
                self._send_json(500, json.dumps({'error': 'run meta unreadable'}))
                return
            self._send_json(200, json.dumps({
                'id': m.get('id'), 'kind': m.get('kind'), 'ref': m.get('ref'),
                'status': m.get('status'), 'started_wib': m.get('started_wib'),
                'finished_wib': m.get('finished_wib'), 'rc': m.get('rc'),
                'note': m.get('note'), 'tail': m.get('_tail') or [],
                'result_path': m.get('result_path'),
                'tokens_in': m.get('tokens_in'), 'tokens_out': m.get('tokens_out'),
                'cost_usd': m.get('cost_usd')}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'ai-task status failed', 'details': str(e)}))

    def _handle_token_usage(self):
        """GET /api/token-usage — the aggregate block of journal/state/token_usage.json
        (30d token+cost estimates per task type, by model, by day). State missing →
        {note} graceful. Last sweep older than 6h → trigger a detached background
        sweep (flock-guarded, same lock as the cron line) and serve the stale
        aggregate with refreshing:true."""
        try:
            if not TOKEN_USAGE_PATH.exists():
                self._send_json(200, json.dumps({
                    'note': TOKEN_USAGE_NOTE, 'aggregate': None,
                    'error': 'no token_usage.json yet — run token_usage.py sweep'}))
                return
            state = json.loads(TOKEN_USAGE_PATH.read_text(encoding='utf-8'))
            # Flatten the aggregate to top level: the UI contract expects
            # window_days/totals/by_task_type/by_model/by_day as top-level keys
            # (keep 'aggregate' too for any other consumer).
            agg = state.get('aggregate') or {}
            payload = {
                **agg,
                'note': TOKEN_USAGE_NOTE,
                'last_sweep': state.get('last_sweep'),
                'sweep_seconds': state.get('sweep_seconds'),
                'aggregate': state.get('aggregate'),
            }
            last_epoch = state.get('last_sweep_epoch') or 0
            if time.time() - last_epoch > TOKEN_USAGE_STALE_SECS:
                payload['refreshing'] = True
                try:
                    cmd = ('flock -n /tmp/token_tracker.lock '
                           + shlex.join(['python3', str(TOKEN_TRACKER_SCRIPT), 'sweep'])
                           + f' >> {shlex.quote(str(TOKEN_TRACKER_LOG))} 2>&1')
                    subprocess.Popen(['sh', '-c', cmd], cwd=str(BASE_DIR),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
                except Exception:
                    payload['refreshing'] = False
            self._send_json(200, json.dumps(payload))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'token-usage failed',
                                             'details': str(e)}))

    def _handle_post_commitment_link(self):
        """POST /api/commitment-link {commitment_id, ticket_id} — link a COM item to a
        tracker ticket via the ledger CLI (single writer). Empty/null ticket_id = unlink."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            cid = (body.get('commitment_id') or '').strip()
            tid = (body.get('ticket_id') or '').strip() if body.get('ticket_id') else ''
            if not cid:
                self._send_json(400, json.dumps({'error': 'missing commitment_id'}))
                return
            if tid:
                argv = ['python3', COMMITMENT_CLI, 'link', cid, '--ticket', tid]
            else:
                argv = ['python3', COMMITMENT_CLI, 'unlink', cid]
            proc = subprocess.run(argv, cwd=str(BASE_DIR), capture_output=True,
                                  text=True, timeout=30)
            if proc.returncode != 0:
                out = (proc.stderr or proc.stdout or '')[:300]
                status = 404 if 'not found' in out else 500
                self._send_json(status, json.dumps({'error': 'commitment-link failed',
                                                    'details': out}))
                return
            self._send_json(200, json.dumps({'ok': True, 'commitment_id': cid,
                                             'ticket_id': tid or None}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'commitment-link failed', 'details': str(e)}))

    def _handle_post_commitment_close(self):
        """POST /api/commitment-close {id, action: 'close'|'drop', note?} — close/drop a
        COM item from the UI via the ledger CLI (single writer)."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            cid = (body.get('id') or '').strip()
            action = (body.get('action') or 'close').strip()
            if not cid or action not in ('close', 'drop'):
                self._send_json(400, json.dumps({'error': 'need id + action close|drop'}))
                return
            argv = ['python3', COMMITMENT_CLI, action, cid]
            note = (body.get('note') or '').strip()
            if note:
                argv += ['--note', note[:200]]
            proc = subprocess.run(argv, cwd=str(BASE_DIR), capture_output=True,
                                  text=True, timeout=30)
            if proc.returncode != 0:
                out = (proc.stderr or proc.stdout or '')[:300]
                self._send_json(404 if 'not found' in out else 500,
                                json.dumps({'error': f'{action} failed', 'details': out}))
                return
            self._send_json(200, json.dumps({'ok': True, 'id': cid, 'action': action}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'commitment-close failed', 'details': str(e)}))

    def _handle_post_waiting_close(self):
        """POST /api/waiting-close {id, action: 'close'|'drop'|'touch'} — resolve/nudge a
        WAIT item from the UI via the watchdog CLI (single writer)."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            wid = (body.get('id') or '').strip()
            action = (body.get('action') or 'close').strip()
            if not wid or action not in ('close', 'drop', 'touch'):
                self._send_json(400, json.dumps({'error': 'need id + action close|drop|touch'}))
                return
            watchdog_cli = str(BASE_DIR / '.agent' / 'skills' / 'waiting-watchdog' /
                               'scripts' / 'waiting_watchdog.py')
            proc = subprocess.run(['python3', watchdog_cli, action, wid],
                                  cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                out = (proc.stderr or proc.stdout or '')[:300]
                self._send_json(404 if 'not found' in out else 500,
                                json.dumps({'error': f'{action} failed', 'details': out}))
                return
            self._send_json(200, json.dumps({'ok': True, 'id': wid, 'action': action}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'waiting-close failed', 'details': str(e)}))

    def _handle_get_briefing(self):
        """GET /api/briefing — newest Pagi + Malam sections from Dashboard.md (file is
        reverse-chron, so first matching header of each kind = newest). latest = the one
        appearing first in the file; each markdown capped at 6000 chars."""
        try:
            lines = DASHBOARD_PATH.read_text(encoding='utf-8').splitlines()
            sections, current = [], None
            for ln in lines:
                if ln.startswith('## '):
                    if current:
                        sections.append(current)
                        current = None
                    kind = None
                    if '🌅' in ln or re.search(r'\bPagi\b', ln):
                        kind = 'pagi'
                    elif '🌙' in ln or re.search(r'\bMalam\b', ln):
                        kind = 'malam'
                    if kind:
                        current = {'kind': kind, 'title': ln[3:].strip(), 'lines': [ln]}
                elif current is not None:
                    current['lines'].append(ln)
            if current:
                sections.append(current)

            def pack(s):
                if not s:
                    return None
                return {'kind': s['kind'], 'title': s['title'],
                        'markdown': '\n'.join(s['lines']).strip()[:6000]}

            latest = sections[0] if sections else None
            other = next((s for s in sections[1:] if latest and s['kind'] != latest['kind']),
                         None) if latest else None
            self._send_json(200, json.dumps({'latest': pack(latest), 'other': pack(other)}))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build briefing', 'details': str(e)}))

    def _handle_get_progress(self):
        """GET /api/progress — Today-tab momentum series, last 14 days each as
        [{date, count}]: done_tickets (activity log: action containing 'done' OR a
        ticket_edit whose summary moved a status 'to done' — the real done signal),
        docs_created (git adds of *.md under Clients/+journal/, cached 10 min),
        meetings (fathom_registry date_wib), commitments_closed (commitments.json
        closed_at). Missing sources -> empty arrays, never fabricated zeros."""
        try:
            now = datetime.now(WIB)
            today = now.date()
            days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
            dayset = set(days)
            d7 = set(days[-7:])

            def series(counts):
                return [{'date': d, 'count': counts.get(d, 0)} for d in days]

            def total7(counts):
                return sum(c for d, c in counts.items() if d in d7)

            # done tickets from the activity log
            done_counts, have_log = {}, ACTIVITY_LOG_PATH.exists()
            if have_log:
                for line in ACTIVITY_LOG_PATH.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    d = (e.get('ts_wib') or '')[:10]
                    if d not in dayset:
                        continue
                    act = (e.get('action') or '').lower()
                    if 'done' in act or (act == 'ticket_edit' and
                                         'to done' in (e.get('summary') or '')):
                        done_counts[d] = done_counts.get(d, 0) + 1

            # docs created (git, cached)
            docs_counts = {d: c for d, c in _git_docs_created_per_day().items() if d in dayset}

            # meetings from the fathom registry
            meet_counts, have_reg = {}, FATHOM_REGISTRY_PATH.exists()
            if have_reg:
                try:
                    reg = json.loads(FATHOM_REGISTRY_PATH.read_text(encoding='utf-8'))
                    rows = reg.values() if isinstance(reg, dict) else reg
                    for r in rows:
                        d = (r.get('date_wib') or '')[:10]
                        if d in dayset:
                            meet_counts[d] = meet_counts.get(d, 0) + 1
                except Exception:
                    have_reg = False

            # commitments closed (closed_at epoch -> WIB date)
            com_counts, have_com = {}, COMMITMENTS_PATH.exists()
            if have_com:
                try:
                    st = json.loads(COMMITMENTS_PATH.read_text(encoding='utf-8'))
                    for it in (st.get('items') or {}).values():
                        ca = it.get('closed_at')
                        if not ca:
                            continue
                        d = datetime.fromtimestamp(float(ca), WIB).date().isoformat()
                        if d in dayset:
                            com_counts[d] = com_counts.get(d, 0) + 1
                except Exception:
                    have_com = False

            self._send_json(200, json.dumps({
                'generated_wib': now.isoformat(timespec='seconds'),
                'days': days,
                'done_tickets': series(done_counts) if have_log else [],
                'docs_created': series(docs_counts),
                'meetings': series(meet_counts) if have_reg else [],
                'commitments_closed': series(com_counts) if have_com else [],
                'totals': {
                    'done_7d': total7(done_counts),
                    'meetings_7d': total7(meet_counts),
                    'docs_7d': total7(docs_counts),
                    'commitments_closed_7d': total7(com_counts),
                },
            }))
        except Exception as e:
            self._send_json(500, json.dumps({'error': 'Failed to build progress', 'details': str(e)}))

    def _send_json(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def log_message(self, format, *args):
        if '/api/' in (args[0] if args else ''):
            print(f"  API  {args[0]}")

def main():
    # ThreadingHTTPServer: each request/connection gets its own thread, so one slow or
    # keep-alive browser connection can't freeze the whole dashboard (the old single-threaded
    # HTTPServer hung all tabs when one connection blocked).
    server = ThreadingHTTPServer(('0.0.0.0', PORT), DashboardHandler)
    server.daemon_threads = True
    print(f"\n  🚀 Dashboard running at http://localhost:{PORT}\n")
    print(f"  Reading from: {DASHBOARD_PATH}")
    print(f"  Calendar:     {'✅ token found' if TOKEN_FILE.exists() else '❌ no token'}")
    print(f"  Projects:     {CLIENTS_DIR}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()

if __name__ == '__main__':
    main()
