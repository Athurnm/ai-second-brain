#!/usr/bin/env python3
"""command_queue.py — turn the owner's task comments into auto-dispatched headless claude runs.

the owner writes commands as comments on dashboard tickets (stored in tickets.json as
`comments[]` with by:"owner"). Nothing used to execute them — they just sat as
context until a session happened to read the ticket. This closes that gap:

  scan      -> find new by:owner comments, enqueue actionable-looking ones
  dispatch  -> triage each pending command (cheap haiku call) to pick the RIGHT
               model+effort per the CLAUDE.md routing table, then spawn a DETACHED
               `claude -p` worker to actually do the work. --live to really spawn;
               default is a dry-run plan.
  report    -> queue status (pending / dispatched / done / skipped / needs-approval)

State: journal/state/command_queue.json — keyed by "<ticket_id>:<comment_ts>", so a
comment is processed exactly once and re-runs are idempotent.

Safety: workers run in the repo but are instructed to NEVER send an external message
(Slack/email) or overwrite a client Google Doc — anything needing a send is written as
a DRAFT to journal/ai_drafts/ and flagged for the owner. The Slack-send PreToolUse hook
stays active as a backstop. See SKILL.md for the residual-risk note.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

# The AI runner resolves which backend actually answers (Claude when installed,
# agy-bridge otherwise) so this skill degrades instead of dying on a machine
# without the claude CLI. See .agent/scripts/ai_call.py.
sys.path.insert(0, os.path.join(BASE_DIR, '.agent', 'scripts'))
import ai_call  # noqa: E402  (needs BASE_DIR on sys.path first)

TICKETS_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'tickets.json')
QUEUE_PATH = os.path.join(BASE_DIR, 'journal', 'state', 'command_queue.json')
DRAFTS_DIR = os.path.join(BASE_DIR, 'journal', 'ai_drafts')
RUNS_DIR = os.path.join(BASE_DIR, 'journal', 'ai_runs')

MAX_RUNNING = 2          # never more than N concurrent workers
STALE_MIN = 45           # a "running" worker older than this stops blocking a slot

# category -> (model alias, effort label, thinking directive woven into the prompt).
# Mirrors the subagent routing table in CLAUDE.md: cheap+mechanical -> haiku, judgment -> opus.
ROUTING = {
    'harvest':    ('haiku',  'low',    ''),
    'lookup':     ('haiku',  'low',    ''),
    'draft':      ('sonnet', 'medium', 'Think it through before writing.'),
    'review':     ('sonnet', 'medium', 'Think carefully and be adversarial.'),
    'synthesize': ('opus',   'high',   'Think hard: weigh and prioritise before you answer.'),
    'strategize': ('opus',   'high',   'Ultrathink: reason deeply and adversarially before deciding.'),
}
DEFAULT_CATEGORY = 'draft'   # unknown category falls back to a safe mid tier

# comments that are clearly NOT commands — skip without burning a triage call
NON_COMMAND_MARKERS = ('irrelevant', 'gak relevan', 'udah kelar', 'sudah kelar',
                       'udah selesai', 'removed', 'gak perlu', 'gak jadi', 'done',
                       'skip', 'ignore')

def _now_wib():
    return datetime.now(WIB).isoformat(timespec='seconds')

TOKEN_ENV_FILE = os.path.join(os.path.dirname(__file__), '..', 'token.env')

def _child_env():
    """Env for worker/triage runs. Strip parent Claude-Code session markers so the worker
    isn't seen as a nested subagent, BUT keep/inject CLAUDE_CODE_OAUTH_TOKEN — that is the
    subscription (not API-key) long-lived token from `claude setup-token` that lets a
    headless run authenticate in a cron/non-interactive context. Loaded from token.env
    (gitignored) if not already in the environment. See [[reference_headless_claude_auth_gotcha]]."""
    oauth = os.environ.get('CLAUDE_CODE_OAUTH_TOKEN')
    if not oauth and os.path.exists(TOKEN_ENV_FILE):
        try:
            for line in open(TOKEN_ENV_FILE, encoding='utf-8'):
                line = line.strip()
                if line.startswith('CLAUDE_CODE_OAUTH_TOKEN='):
                    oauth = line.split('=', 1)[1].strip().strip('"\'')
                    break
        except OSError:
            pass
    env = ai_call.child_env()   # strips CLAUDECODE + CLAUDE_CODE_* session markers
    if oauth:
        env['CLAUDE_CODE_OAUTH_TOKEN'] = oauth   # re-inject after the strip
    return env

def _load_json(path, fallback):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback

def _save_queue(q):
    q['last_run'] = _now_wib()
    tmp = QUEUE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(q, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, QUEUE_PATH)

def _tickets():
    d = _load_json(TICKETS_PATH, {})
    tix = d.get('tickets', d) if isinstance(d, dict) else d
    if isinstance(tix, dict):
        tix = list(tix.values())
    return [t for t in (tix or []) if isinstance(t, dict)]

def _command_text(comment):
    """A command lives in the comment `text`, or in a `change` of the form 'note  to <cmd>'."""
    txt = (comment.get('text') or '').strip()
    if txt:
        return txt
    ch = (comment.get('change') or '').strip()
    if ch.lower().startswith('note') and ' to ' in ch:
        return ch.split(' to ', 1)[1].strip()
    return ''

def _looks_like_command(text):
    low = text.lower().strip()
    if len(low) < 6:
        return False
    if low.startswith('[agent]'):          # agent reply mis-tagged by:owner — not a command
        return False
    if any(m in low for m in NON_COMMAND_MARKERS) and len(low) < 40:
        return False
    return True

# ─────────────────────────── scan ───────────────────────────

def cmd_scan(_args):
    q = _load_json(QUEUE_PATH, {'items': {}})
    q.setdefault('items', {})
    added = 0
    for t in _tickets():
        tid = t.get('id') or ''
        for c in (t.get('comments') or []):
            if c.get('by') != 'owner':
                continue
            ts = c.get('ts_wib') or ''
            key = f'{tid}:{ts}'
            if key in q['items']:
                continue
            text = _command_text(c)
            if not _looks_like_command(text):
                # record as skipped so we never re-evaluate it
                q['items'][key] = {'key': key, 'ticket_id': tid,
                                   'ticket_title': t.get('title', ''), 'status': t.get('status', ''),
                                   'command': text, 'ts_wib': ts, 'state': 'skipped',
                                   'reason': 'not a command (pre-filter)', 'enqueued_wib': _now_wib()}
                continue
            q['items'][key] = {'key': key, 'ticket_id': tid,
                               'ticket_title': t.get('title', ''), 'status': t.get('status', ''),
                               'command': text, 'ts_wib': ts, 'state': 'pending',
                               'enqueued_wib': _now_wib()}
            added += 1
    _save_queue(q)
    pend = sum(1 for i in q['items'].values() if i['state'] == 'pending')
    print(f'scan: +{added} new command(s); {pend} pending total.')
    return 0

def cmd_baseline(_args):
    """Mark every currently-pending command as baseline (seen, not run) so activation
    doesn't auto-fire the historical backlog — only NEW comments after this dispatch."""
    q = _load_json(QUEUE_PATH, {'items': {}})
    n = 0
    for i in q.get('items', {}).values():
        if i.get('state') == 'pending':
            i.update({'state': 'skipped', 'reason': 'pre-activation baseline',
                      'baselined_wib': _now_wib()})
            n += 1
    _save_queue(q)
    print(f'baseline: {n} backlog command(s) marked seen (not run). New comments dispatch from here on.')
    return 0

# ─────────────────────────── triage ───────────────────────────

TRIAGE_SYS = (
    "You are a task router. For each command a product-lead wrote on a work ticket, "
    "decide if it is an ACTIONABLE instruction for an AI assistant, its category, and its risk. "
    "Return ONLY a JSON array, one object per input item, no prose. Echo back the item's integer "
    '"idx" exactly. Each object: '
    '{"idx": int, "actionable": bool, "category": one of '
    '["harvest","lookup","draft","review","synthesize","strategize"], '
    '"risk": "safe" or "needs_send", "reason": short str}. '
    "Categories: harvest=bulk read/collect; lookup=find one fact/status; draft=write a doc/reply "
    "from a clear source; review=adversarial check; synthesize=weigh+prioritise+produce a deliverable; "
    "strategize=hard tradeoff/decision. risk=needs_send if fulfilling it clearly requires sending a "
    "Slack/email/external message; otherwise safe. A question, a note-to-self, or 'is this done?' with "
    "no action is actionable=false."
)

def _run_triage(pending):
    """One cheap haiku call classifies the whole pending batch. Returns {key: routing}.
    Keyed on integer idx (not the raw <ticket>:<ts> key) so the model can echo it back
    reliably — a complex key string with colons/timestamps gets mangled on echo."""
    payload = [{'idx': n, 'command': i['command'],
                'ticket_title': i['ticket_title'], 'ticket_status': i['status']}
               for n, i in enumerate(pending)]
    prompt = TRIAGE_SYS + "\n\nCOMMANDS:\n" + json.dumps(payload, ensure_ascii=False)
    spec = ai_call.plan(prompt, task='harvest', model='haiku', output_format='json')
    if spec['backend'] == 'none':
        print(f'triage: no AI backend available ({spec["note"]}); leaving pending.',
              file=sys.stderr)
        return {}
    try:
        r = subprocess.run(spec['argv'], cwd=BASE_DIR, capture_output=True, text=True,
                           timeout=180, env=_child_env())
    except Exception as e:
        print(f'triage: FAILED to run {spec["backend"]} ({e}); leaving pending.', file=sys.stderr)
        return {}
    if r.returncode == ai_call.FALLBACK_EXIT:
        # agy-bridge exhausted its chain and handed back the claude_fallback
        # sentinel. Nothing here can honour it (there is no Claude on this box),
        # so leave the batch pending rather than mis-route it.
        print('triage: backend fell back to Claude but none is installed; leaving pending.',
              file=sys.stderr)
        return {}
    out = r.stdout.strip()
    # --output-format json wraps the result; the model's text is in .result
    text = out
    try:
        wrapper = json.loads(out)
        if isinstance(wrapper, dict) and 'result' in wrapper:
            text = wrapper['result']
    except json.JSONDecodeError:
        pass
    # extract the JSON array from the model text
    start, end = text.find('['), text.rfind(']')
    if start == -1 or end == -1:
        print(f'triage: no JSON array in response; leaving pending. raw={text[:200]!r}', file=sys.stderr)
        return {}
    try:
        arr = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        print(f'triage: bad JSON ({e}); leaving pending.', file=sys.stderr)
        return {}
    # map idx -> the real queue key so callers keep using i['key']
    out = {}
    for o in arr:
        if not isinstance(o, dict):
            continue
        idx = o.get('idx')
        if isinstance(idx, int) and 0 <= idx < len(pending):
            out[pending[idx]['key']] = o
    return out

# ─────────────────────────── dispatch ───────────────────────────

def _running_workers(q):
    now = time.time()
    out = []
    for i in q['items'].values():
        if i.get('state') != 'dispatched':
            continue
        # reconcile against the run's sentinel/log so a finished worker frees a slot
        rid = i.get('run_id')
        log = os.path.join(RUNS_DIR, f'{rid}.log') if rid else None
        done = False
        if log and os.path.exists(log):
            try:
                with open(log, encoding='utf-8', errors='replace') as fh:
                    tail = fh.read()[-2000:]
                if 'AI_TASK_DONE rc=' in tail:
                    done = True
            except OSError:
                pass
        if done:
            # a finished worker with a draft on disk awaits the owner's review; otherwise just done
            dp = i.get('draft_path')
            has_draft = bool(dp and os.path.exists(os.path.join(BASE_DIR, dp)))
            i['state'] = 'review' if has_draft else 'done'
            i['finished_wib'] = _now_wib()
            continue
        if now - (i.get('started_epoch') or 0) < STALE_MIN * 60:
            out.append(i)
    return out

def _draft_rel(item):
    return f'journal/ai_drafts/cmd_{item["key"].replace(":", "_").replace("/", "_")}.md'

def _worker_prompt(item, category, directive):
    draft_rel = _draft_rel(item)
    return (
        f"You are a DRAFT-ONLY assistant executing a command the owner left on a work ticket. "
        f"Repo: {BASE_DIR}.\n\n"
        f"TICKET: {item['ticket_id']} — {item['ticket_title']} (status: {item['status']})\n"
        f"COMMAND FROM OWNER: {item['command']}\n\n"
        f"{directive}\n\n"
        "Do the RESEARCH end to end: read/search the repo, check Jira/Drive/Fathom/Slack (read-only) as "
        "needed to fully work the command out. Then produce a draft the owner can act on.\n\n"
        "HARD LIMITS — this is an unattended run and you have NO write access to anything except the draft "
        "file below:\n"
        "- NEVER send a Slack message, email, or any external message.\n"
        "- NEVER edit repo files, journal state, tickets, or Google Docs. You cannot — the tools are "
        "restricted — so put EVERYTHING in the draft.\n\n"
        f"Write your output to {draft_rel} as a clean Markdown doc with these sections:\n"
        "  # <ticket_id>: <one-line what this command asked>\n"
        "  ## What I found  — the research result (status, facts, links, Jira/Slack findings)\n"
        "  ## Proposed action — exactly what should happen next; if it's a message to send, give the FULL "
        "ready-to-send draft text + the target channel/person + thread link\n"
        "  ## Needs the owner — the specific approval/decision required, or 'nothing, FYI' if none.\n\n"
        "Your final assistant message must be a 2-3 line summary of that draft."
    )

def _spawn_worker(item, category):
    model, effort, directive = ROUTING.get(category, ROUTING[DEFAULT_CATEGORY])
    os.makedirs(RUNS_DIR, exist_ok=True)
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    epoch = int(time.time())
    safe_key = item['key'].replace(':', '-').replace('/', '-')
    run_id = f'cmd-{epoch}-{safe_key}'
    while os.path.exists(os.path.join(RUNS_DIR, f'{run_id}.json')):
        epoch += 1
        run_id = f'cmd-{epoch}-{safe_key}'
    log_path = os.path.join(RUNS_DIR, f'{run_id}.log')
    prompt = _worker_prompt(item, category, directive)
    # DRAFT-ONLY whitelist (the owner's chosen autonomy level): read + research freely, but the
    # only WRITE allowed is into journal/ai_drafts/. No Edit, no arbitrary Bash, no ticket
    # mutation, no send tools, no Jira/Drive write tools — a worker can never touch client
    # state unattended. It produces a draft/plan the owner applies. See SKILL.md.
    tools = (
        'Read,Grep,Glob,WebFetch,WebSearch,Write(journal/ai_drafts/**),'
        'mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql,'
        'mcp__claude_ai_Atlassian__getJiraIssue,'
        'mcp__claude_ai_Atlassian__search,mcp__claude_ai_Atlassian__fetch,'
        'mcp__claude_ai_Fathom__*,'
        'mcp__claude_ai_Google_Drive__search_files,'
        'mcp__claude_ai_Google_Drive__read_file_content,'
        'mcp__claude_ai_Google_Drive__get_file_metadata,'
        'mcp__claude_ai_Slack__slack_search_public_and_private,'
        'mcp__claude_ai_Slack__slack_read_thread,mcp__claude_ai_Slack__slack_read_channel')
    spec = ai_call.plan(prompt, model=model, output_format='json', allowed_tools=tools)
    if spec['backend'] == 'none':
        # No model can run this. Say so and leave the item pending; a half-spawned
        # worker that never writes a draft is worse than a deferred one.
        print(f'  SKIP  {item["key"]:<22} no AI backend ({spec["note"]})')
        return None
    shell_cmd = shlex.join(spec['argv']) + '; echo AI_TASK_DONE rc=$?'
    with open(log_path, 'w', encoding='utf-8') as log_fh:
        proc = subprocess.Popen(['sh', '-c', shell_cmd], cwd=BASE_DIR,
                                stdout=log_fh, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True,
                                env=_child_env())
    item.update({'state': 'dispatched', 'run_id': run_id, 'model': model,
                 'backend': spec['backend'],
                 'effort': effort, 'category': category, 'pid': proc.pid,
                 'started_epoch': time.time(), 'dispatched_wib': _now_wib(),
                 'draft_path': _draft_rel(item),
                 'log': os.path.relpath(log_path, BASE_DIR)})
    return run_id, model, effort

def cmd_dispatch(args):
    q = _load_json(QUEUE_PATH, {'items': {}})
    q.setdefault('items', {})
    pending = [i for i in q['items'].values() if i['state'] == 'pending']
    if args.limit:
        pending = pending[:args.limit]
    if not pending:
        print('dispatch: nothing pending.')
        return 0

    routing = _run_triage(pending)
    slots = MAX_RUNNING - len(_running_workers(q))
    planned, spawned = [], 0
    for i in pending:
        rt = routing.get(i['key'])
        if not rt:
            continue  # triage failed for this one; leave pending for next run
        if not rt.get('actionable'):
            i.update({'state': 'skipped', 'reason': rt.get('reason', 'not actionable'),
                      'category': rt.get('category', ''), 'triaged_wib': _now_wib()})
            continue
        cat = rt.get('category') if rt.get('category') in ROUTING else DEFAULT_CATEGORY
        model, effort, _ = ROUTING[cat]
        needs = rt.get('risk') == 'needs_send'
        planned.append((i, cat, model, effort, needs, rt.get('reason', '')))

    for i, cat, model, effort, needs, reason in planned:
        tag = ' [needs approval: draft-only]' if needs else ''
        if not args.live:
            print(f'  PLAN  {i["key"]:<22} {cat:<11} {model}/{effort}{tag}  · {i["command"][:70]}')
            continue
        if spawned >= slots:
            print(f'  DEFER {i["key"]:<22} (slots full, {MAX_RUNNING} running) — stays pending')
            continue
        spawn = _spawn_worker(i, cat)
        if not spawn:
            continue      # no backend; _spawn_worker already reported it, item stays pending
        rid, m, e = spawn
        spawned += 1
        print(f'  SPAWN {i["key"]:<22} {cat:<11} {m}/{e}  run={rid}{tag}')

    _save_queue(q)
    if not args.live and planned:
        print(f'\ndry-run: {len(planned)} would dispatch. Re-run with --live to spawn.')
    return 0

# ─────────────────────────── report ───────────────────────────

def cmd_ack(args):
    """Mark a reviewed draft acknowledged (review -> done), so it clears the approval list."""
    q = _load_json(QUEUE_PATH, {'items': {}})
    hit = q.get('items', {}).get(args.key)
    if not hit:
        # allow ack by ticket_id if unique among review items
        matches = [i for i in q.get('items', {}).values()
                   if i.get('ticket_id') == args.key and i.get('state') == 'review']
        if len(matches) == 1:
            hit = matches[0]
    if not hit:
        print(f'ack: no review item for {args.key!r}.')
        return 1
    hit['state'] = 'done'
    hit['acked_wib'] = _now_wib()
    _save_queue(q)
    print(f'ack: {hit["ticket_id"]} draft acknowledged.')
    return 0

def cmd_report(_args):
    q = _load_json(QUEUE_PATH, {'items': {}})
    # reconcile running->review/done before reporting
    _running_workers(q)
    _save_queue(q)
    items = list(q.get('items', {}).values())
    by = {}
    for i in items:
        by.setdefault(i['state'], []).append(i)
    print(f'## 🤖 Command queue — {len(items)} total (last run {q.get("last_run","?")})\n')
    if by.get('review'):
        print(f'### 📋 Awaiting your approval ({len(by["review"])})')
        for i in sorted(by['review'], key=lambda x: x.get('ts_wib', '')):
            print(f'- **{i["ticket_id"]}** {i["command"][:70]}  → [{i.get("draft_path","")}]')
        print()
    for state in ('dispatched', 'pending', 'done', 'skipped'):
        rows = by.get(state, [])
        if not rows:
            continue
        print(f'### {state} ({len(rows)})')
        for i in sorted(rows, key=lambda x: x.get('ts_wib', '')):
            extra = ''
            if state == 'dispatched':
                extra = f'  [{i.get("model","?")}/{i.get("effort","?")} · {i.get("run_id","")}]'
            elif i.get('category'):
                extra = f'  ({i.get("category")})'
            print(f'- **{i["ticket_id"]}** {i["command"][:80]}{extra}')
        print()
    return 0

def main():
    ap = argparse.ArgumentParser(description='Auto-dispatch the owner task-comment commands to headless claude runs.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('scan', help='enqueue new by:owner command comments')
    sub.add_parser('baseline', help='mark current backlog seen-but-not-run (do once at activation)')
    dp = sub.add_parser('dispatch', help='triage + spawn workers (dry-run unless --live)')
    dp.add_argument('--live', action='store_true', help='actually spawn workers')
    dp.add_argument('--limit', type=int, default=0, help='cap how many pending to process')
    sub.add_parser('report', help='queue status')
    ak = sub.add_parser('ack', help='mark a reviewed draft acknowledged (review -> done)')
    ak.add_argument('key', help='queue key (<ticket>:<ts>) or a unique ticket id')
    args = ap.parse_args()
    return {'scan': cmd_scan, 'baseline': cmd_baseline, 'dispatch': cmd_dispatch,
            'report': cmd_report, 'ack': cmd_ack}[args.cmd](args)

if __name__ == '__main__':
    sys.exit(main())
