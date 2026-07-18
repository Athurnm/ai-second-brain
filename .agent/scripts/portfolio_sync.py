#!/usr/bin/env python3
"""
portfolio_sync.py -- keep journal/state/portfolio.json genuinely fresh.

Why this exists: the dashboard "Portfolio" card grades freshness off the mtime of
portfolio.json (48h warn). Nothing ever wrote that file -- portfolio_render.py only
reads it and writes the journal/portfolio.md mirror -- so the card drifted to "dead"
and the card's own hint ("refresh via portfolio_render.py") could never fix it.

Two passes:

  1. MECHANICAL (always, deterministic, no model): rebuild each initiative's auto
     blockers from waiting_on.json -- open/breached items carrying an initiative_id.
     Human-written blockers (auto != True) are preserved untouched. Health is only
     ever raised, never lowered: a human's "blocked" is never downgraded here.

     tickets.json is deliberately NOT a blocker source. No ticket is ever status
     "blocked" (all 115 are done/todo/waiting/monitor); its "waiting" rows are chase
     items awaiting someone's reply, which is a monitor, not a blocker. Promoting
     those would secondary healthy initiatives red off a pending sign-off.

  2. NARRATIVE (--narrative, GLM via agy-bridge): keep the `now` line current for the
     initiatives whose evidence moved. The line is split in two:

         now = now_base (human sentence, never rewritten) + now_auto (blocker clause)

     GLM is only ever asked for now_auto, from the open evidence alone; the code does
     the joining. The base is never sent for rewriting, so it cannot be eroded -- the
     first version asked for a full rewrite and silently dropped live context that no
     evidence had resolved. When the last open item clears, now_auto is dropped and the
     line falls back to the base on its own. Bounded by --max-narrative. On any doubt
     (fallback sentinel, empty answer, bridge failure) the existing text stands and the
     initiative is flagged needs_review -- the script never invents progress.

Freshness contract: updated_wib + mtime are only stamped when this run actually
verified the file against the ledgers. A run that cannot read the ledgers exits
non-zero WITHOUT touching the file, so a broken pipeline shows up as a dead card
instead of a green lie.

Usage:
    python3 .agent/scripts/portfolio_sync.py                  # mechanical pass + render
    python3 .agent/scripts/portfolio_sync.py --narrative      # + GLM `now` refresh
    python3 .agent/scripts/portfolio_sync.py --dry-run        # report, write nothing
    python3 .agent/scripts/portfolio_sync.py --check          # validate linkage only
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATE = BASE_DIR / 'journal' / 'state'
PORTFOLIO_PATH = STATE / 'portfolio.json'
WAITING_PATH = STATE / 'waiting_on.json'
RENDER_SCRIPT = BASE_DIR / '.agent' / 'scripts' / 'portfolio_render.py'
AGY_BRIDGE = BASE_DIR / '.agent' / 'skills' / 'agy-bridge' / 'run.py'

WIB = timezone(timedelta(hours=7))
HEALTH_RANK = {'planning': 0, 'on_track': 1, 'at_risk': 2, 'blocked': 3}
RANK_HEALTH = {v: k for k, v in HEALTH_RANK.items()}

# The clause has to name every open item, so its budget scales with how many there are.
# A flat cap made the model self-truncate mid-name ("...pricing offer ke Mr.") once an
# initiative carried more than a couple of items.
CLAUSE_BASE_CHARS = 220
CLAUSE_PER_ITEM_CHARS = 90
CLAUSE_MAX_CHARS = 700

def clause_budget(n_items):
    return min(CLAUSE_MAX_CHARS, CLAUSE_BASE_CHARS + CLAUSE_PER_ITEM_CHARS * n_items)

def now_wib():
    return datetime.now(WIB)

def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write_json_atomic(path, data):
    """Write via temp file + replace so a crash mid-write can't truncate the state file."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

def iter_items(container):
    """waiting_on.json keys items by id; tickets.json uses a list. Accept both."""
    if isinstance(container, dict):
        return list(container.values())
    return list(container or [])

def collect_evidence(waiting):
    """Map initiative_id -> the waiting-on rows that justify a blocker. Rows without an
    initiative_id are skipped on purpose: guessing the link from prose would put
    invented blockers on the board."""
    ev = {}
    for w in iter_items(waiting.get('items')):
        init = w.get('initiative_id')
        if not init or w.get('status') not in ('open', 'breached'):
            continue
        since = w.get('since')
        since_str = (datetime.fromtimestamp(since, WIB).strftime('%Y-%m-%d')
                     if isinstance(since, (int, float)) else str(since or '-'))
        ev.setdefault(init, []).append({
            'what': w.get('what', '').strip(),
            'owner': w.get('owner') or '-',
            'since': since_str,
            'source': w.get('id'),
            'auto': True,
        })
    return ev

def sync_initiative(init, evidence, breached_inits):
    """Rebuild auto blockers + raise health. Returns a list of change descriptions."""
    changes = []
    manual = [b for b in init.get('blockers', []) if not b.get('auto')]
    old_auto = {b.get('source') for b in init.get('blockers', []) if b.get('auto')}
    new_auto = {b['source'] for b in evidence}

    if old_auto != new_auto:
        added = sorted(new_auto - old_auto)
        gone = sorted(old_auto - new_auto)
        if added:
            changes.append(f"blocker+ {', '.join(added)}")
        if gone:
            changes.append(f"blocker- {', '.join(gone)}")
    init['blockers'] = manual + list(evidence)

    # A BREACHED waiting-on item is evidence the initiative is at_risk -- someone blew
    # an SLA on something it depends on. An open-but-within-SLA item is just normal
    # work in flight and moves nothing. "blocked" is never set from here: that is a
    # judgment call about whether work has actually stopped, which the ledger can't see.
    # Health only ever rises: a human's downgrade stands until a human revisits it.
    if init.get('status') != 'planning' and init['id'] in breached_inits:
        cur = HEALTH_RANK.get(init.get('health'), 0)
        if cur < HEALTH_RANK['at_risk']:
            init['health'] = 'at_risk'
            changes.append(f"health {RANK_HEALTH[cur]} -> at_risk (breached SLA)")
    return changes

def narrative_prompt(init, evidence):
    """Ask ONLY for the blocker clause. The human/base sentence is never sent for
    rewriting, so the model has no opportunity to erode it -- an earlier version asked
    for a full rewrite and quietly dropped live context ("SAB go-live gated image CR")
    that no evidence had resolved."""
    lines = [
        "You summarise what an initiative is currently waiting on, in one clause.",
        "",
        f"Initiative: {init.get('name')} ({init.get('id')})",
        f"One-liner: {init.get('one_liner', '-')}",
        "",
        "It is waiting on exactly these open items:",
    ]
    for b in evidence:
        lines.append(f"- [{b['source']}] {b['what']} (owner {b['owner']}, since {b['since']})")
    lines += [
        "",
        "Write ONE clause naming what is being waited on, to be appended after an",
        "existing status sentence.",
        "HARD RULES:",
        "- Use ONLY facts from the items above. Invent nothing: no new dates,",
        "  percentages, ticket numbers, or names.",
        f"- Cover every item above, compressed. Under {clause_budget(len(evidence))}"
        " characters, one sentence.",
        "- Never cut off mid-thought to fit. If it is tight, shorten each item to its",
        "  essence instead -- a trailing fragment is worse than a terse clause.",
        "- Mixed Indonesian/English PM register, e.g."
        " 'Blocked: nunggu Finance sign-off X (Teammate 1-2 hari) + Legal confirm Y.'",
        "- Start with a capital letter. No leading conjunction.",
        "",
        "Reply with the clause only. No preamble, no quotes, no markdown.",
    ]
    return '\n'.join(lines)

def call_glm(prompt, timeout=120):
    """Return the model's text, or None when the caller must keep the existing line.
    agy-bridge exit 3 = fallback sentinel (no non-Claude model available); this job is
    explicitly not worth a Claude call, so a sentinel means 'leave it alone'."""
    fd, tmp = tempfile.mkstemp(suffix='.txt', prefix='portfolio_now.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(prompt)
        proc = subprocess.run(
            [sys.executable, str(AGY_BRIDGE), '--task', 'draft', '--prompt-file', tmp],
            capture_output=True, text=True, timeout=timeout, cwd=str(BASE_DIR))
    except subprocess.TimeoutExpired:
        return None
    finally:
        Path(tmp).unlink(missing_ok=True)

    if proc.returncode != 0:
        return None
    text = (proc.stdout or '').strip()
    if not text or text.startswith('{'):  # sentinel or empty
        return None
    return text

# Compared against the last token with surrounding punctuation stripped, so entries here
# carry no dots: "...offer ke Mr." normalises to "mr".
DANGLING_TAIL = frozenset((
    'mr', 'mrs', 'ms', 'dr', 'dan', 'and', 'atau', 'or', '+', '&', 'ke', 'di', 'dari',
    'the', 'a', 'of', 'to', 'for', 'with', 'nunggu', 'eg', 'incl', 'vs', 'sama', 'buat',
))

def plausible_clause(text, budget):
    """Guard rails on the model's answer. Empty, multi-line, or over-budget means the
    bridge returned something that is not the clause we asked for. A clause ending on a
    dangling word ("...offer ke Mr.") is the model truncating itself to fit -- publishing
    that reads as a fact cut in half, so reject and let the retry path handle it."""
    if not text:
        return False
    text = text.strip()
    if not text or '\n' in text or len(text) > budget + 40:
        return False
    tokens = text.split()
    last = tokens[-1].strip('.,;:+&-').lower() if tokens else ''
    return bool(last) and last not in DANGLING_TAIL

def base_now(init):
    """The human-authored sentence. Captured once, then never rewritten -- the auto
    clause is regenerated around it, so a resolved blocker disappears on its own
    without any model touching the base text."""
    if 'now_base' not in init:
        base = init.get('now') or ''
        # First run on an initiative whose `now` already carries an auto clause: split
        # it back off so the base doesn't absorb a stale blocker sentence forever.
        auto = init.get('now_auto')
        if auto and base.endswith(auto):
            base = base[:-len(auto)]
        init['now_base'] = base.strip()
    return init['now_base']

def compose_now(base, clause):
    if not clause:
        return base
    if not base:
        return clause
    sep = '' if base.endswith(('.', '!', '?')) else '.'
    return f"{base}{sep} {clause}"

def run_narrative(targets, dry_run, limit):
    touched, flagged, rejected = [], [], []
    for init, evidence in targets[:limit]:
        answer = call_glm(narrative_prompt(init, evidence))
        if answer is None:
            init['needs_review'] = True
            flagged.append(init['id'])
            continue
        if not plausible_clause(answer, clause_budget(len(evidence))):
            # Junk back: the existing line stands. Say so -- a silent skip is
            # indistinguishable from "nothing to report" and hides a failing bridge.
            init['needs_review'] = True
            rejected.append(f"{init['id']} ({len(answer.strip())} chars)")
            continue
        if not dry_run:
            base = base_now(init)
            clause = answer.strip()
            init['now_auto'] = clause
            init['now'] = compose_now(base, clause)
            init['now_updated_wib'] = now_wib().isoformat(timespec='minutes')
            init.pop('needs_review', None)
        touched.append(init['id'])
    return touched, flagged, rejected

def clear_stale_clause(init):
    """No open evidence left -> drop the auto clause and fall back to the base sentence.
    This is what makes the line self-cleaning: blockers leave when they are resolved."""
    if init.get('now_auto'):
        init['now'] = base_now(init)
        init.pop('now_auto', None)
        return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--narrative', action='store_true',
                    help='also refresh `now` lines via GLM for initiatives with new evidence')
    ap.add_argument('--max-narrative', type=int, default=8,
                    help='cap GLM calls per run (default 8)')
    ap.add_argument('--dry-run', action='store_true', help='report changes, write nothing')
    ap.add_argument('--check', action='store_true',
                    help='validate portfolio/ledger linkage only, no write')
    ap.add_argument('--no-render', action='store_true', help='skip the portfolio.md mirror')
    args = ap.parse_args()

    for path in (PORTFOLIO_PATH, WAITING_PATH):
        if not path.exists():
            print(f"ERROR: {path} not found -- refusing to stamp freshness", file=sys.stderr)
            return 1
    try:
        portfolio = load_json(PORTFOLIO_PATH)
        waiting = load_json(WAITING_PATH)
    except json.JSONDecodeError as e:
        print(f"ERROR: state file invalid JSON: {e}", file=sys.stderr)
        return 1

    inits = [i for t in portfolio.get('teams', []) for i in t.get('initiatives', [])]
    by_id = {i['id']: i for i in inits}
    evidence = collect_evidence(waiting)
    breached_inits = {w.get('initiative_id') for w in iter_items(waiting.get('items'))
                      if w.get('status') == 'breached' and w.get('initiative_id')}

    orphans = sorted(set(evidence) - set(by_id))
    if args.check:
        linked = sum(len(v) for k, v in evidence.items() if k in by_id)
        print(f"OK: {len(inits)} initiative(s), {linked} linked ledger row(s)")
        unlinked_w = sum(1 for w in iter_items(waiting.get('items'))
                         if w.get('status') in ('open', 'breached') and not w.get('initiative_id'))
        print(f"NOTE: {unlinked_w} open waiting-on item(s) carry no initiative_id (not auto-tracked)")
        if orphans:
            print(f"WARN: evidence for unknown initiative id(s): {', '.join(orphans)}")
        return 0
    if orphans:
        print(f"WARN: ignoring evidence for unknown initiative id(s): {', '.join(orphans)}",
              file=sys.stderr)

    # An initiative still in `planning` that has a live SLA item hanging off it is almost
    # always a mis-link, not real news -- nobody breaches an SLA on work not started.
    # Surface it instead of quietly reshaping the board around a bad link.
    suspect = [i['id'] for i in inits
               if i.get('status') == 'planning' and evidence.get(i['id'])]
    for sid in suspect:
        srcs = ', '.join(b['source'] for b in evidence[sid])
        print(f"WARN: {sid} is status=planning but carries live ledger item(s) {srcs} -- "
              f"check the link", file=sys.stderr)

    changed, targets = [], []
    for init in inits:
        ev = evidence.get(init['id'], [])
        before_now_evidence = {b.get('source') for b in init.get('blockers', []) if b.get('auto')}
        deltas = sync_initiative(init, ev, breached_inits)
        if not ev and clear_stale_clause(init):
            deltas.append('now: auto clause cleared (nothing open)')
        if deltas:
            changed.append(f"{init['id']}: {'; '.join(deltas)}")
        # Narrative is worth a model call where the evidence moved, or where a previous
        # run owed a clause and never delivered one (bridge down, answer rejected) --
        # without that retry an initiative rejected once would keep its stale line
        # forever, since its evidence never "changes" again. Never on a suspect planning
        # initiative: rewriting its `now` from a link we already doubt just launders the
        # bad link into prose.
        owes_clause = not init.get('now_auto')
        if ev and init['id'] not in suspect and (
                owes_clause or {b['source'] for b in ev} != before_now_evidence):
            targets.append((init, ev))

    touched, flagged, rejected = ([], [], [])
    if args.narrative:
        touched, flagged, rejected = run_narrative(targets, args.dry_run, args.max_narrative)

    stamp = now_wib().isoformat(timespec='minutes')
    portfolio['updated_wib'] = stamp
    portfolio['synced_wib'] = stamp
    portfolio['sync_source'] = 'portfolio_sync.py'

    if args.dry_run:
        print(f"DRY RUN -- {len(changed)} initiative(s) would change:")
        for c in changed:
            print(f"  {c}")
        print(f"  narrative candidates: {len(targets)} (would refresh {len(touched)})")
        return 0

    write_json_atomic(PORTFOLIO_PATH, portfolio)
    print(f"Synced portfolio.json @ {stamp}: {len(changed)} initiative(s) changed")
    for c in changed:
        print(f"  {c}")
    if touched:
        print(f"  narrative refreshed via GLM: {', '.join(touched)}")
    if flagged:
        print(f"  narrative unavailable, flagged needs_review: {', '.join(flagged)}")
    if rejected:
        print(f"  narrative answer rejected (kept existing line), flagged needs_review: "
              f"{', '.join(rejected)}", file=sys.stderr)

    if not args.no_render:
        r = subprocess.run([sys.executable, str(RENDER_SCRIPT)],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        print(r.stdout.strip() or r.stderr.strip())
        if r.returncode != 0:
            return r.returncode
    return 0

if __name__ == '__main__':
    sys.exit(main())
