#!/usr/bin/env python3
"""
portfolio_render.py -- render journal/state/portfolio.json into a printable
hierarchical markdown mirror at journal/portfolio.md.

Portfolio hierarchy: Team -> Initiative -> Workstream (sub-item).
This is the human-readable mirror of the same data the dashboard "Portfolio"
tab reads via /api/portfolio. Regenerated on demand and at the end of the
evening daily-update run.

Usage:
    python3 .agent/scripts/portfolio_render.py            # writes journal/portfolio.md
    python3 .agent/scripts/portfolio_render.py --check     # validate JSON only, no write
    python3 .agent/scripts/portfolio_render.py --stdout     # print to stdout instead of file
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PORTFOLIO_PATH = BASE_DIR / 'journal' / 'state' / 'portfolio.json'
OUT_PATH = BASE_DIR / 'journal' / 'portfolio.md'

HEALTH_EMOJI = {'on_track': '🟢', 'at_risk': '🟡', 'blocked': '🔴', 'planning': '⚪'}
HEALTH_RANK = {'blocked': 3, 'at_risk': 2, 'on_track': 1, 'planning': 0}
STATUS_EMOJI = {'done': '✅', 'in_progress': '🔵', 'todo': '⬜', 'blocked': '🔴', 'waiting': '⏳'}

def team_health(initiatives):
    """Team health = worst health among its ACTIVE initiatives (planning ignored)."""
    ranks = [HEALTH_RANK.get(i.get('health'), 0)
             for i in initiatives if i.get('status') != 'planning']
    if not ranks:
        return 'on_track'
    worst = max(ranks)
    return next(k for k, v in HEALTH_RANK.items() if v == worst)

def render(data):
    teams = data.get('teams', [])
    out = []
    out.append('# Portfolio -- Top-Down View (Team -> Initiative -> Sub-item)')
    out.append('')
    out.append(f"> Generated from `journal/state/portfolio.json` -- last updated **{data.get('updated_wib', '?')}**  ")
    out.append('> Legend: 🟢 on_track · 🟡 at_risk · 🔴 blocked · ⚪ planning · '
               '✅ done · 🔵 in_progress · ⬜ todo')
    out.append('')

    for team in teams:
        inits = team.get('initiatives', [])
        active = [i for i in inits if i.get('status') != 'planning']
        th = team_health(inits)
        blocker_total = sum(len(i.get('blockers', [])) for i in inits)
        out.append('---')
        out.append('')
        out.append(f"## {HEALTH_EMOJI.get(th, '')} {team.get('name')} "
                   f"({team.get('world', '?')} world · owner {team.get('owner', '?')})")
        out.append('')
        out.append(f"**{len(active)} active initiative(s)** · **{blocker_total} open blocker(s)** · "
                   f"team health **{th}**")
        out.append('')

        # Blocker roll-up for the whole team, top of section
        blk_rows = []
        for i in inits:
            for b in i.get('blockers', []):
                blk_rows.append((i.get('name'), b.get('what', ''), b.get('owner', '-'), b.get('since', '-')))
        if blk_rows:
            out.append('### 🔴 Blockers (team roll-up)')
            out.append('')
            out.append('| Initiative | Blocker | Owner | Since |')
            out.append('| :-- | :-- | :-- | :-- |')
            for name, what, owner, since in blk_rows:
                out.append(f"| {name} | {what} | {owner} | {since} |")
            out.append('')

        # Initiatives: active first (by health severity), then planning
        ordered = sorted(
            inits,
            key=lambda i: (i.get('status') == 'planning', -HEALTH_RANK.get(i.get('health'), 0), i.get('name', ''))
        )
        for i in ordered:
            emoji = HEALTH_EMOJI.get(i.get('health'), '')
            out.append(f"### {emoji} {i.get('name')} — {i.get('health')} · {i.get('status')}")
            out.append('')
            if i.get('one_liner'):
                out.append(f"_{i['one_liner']}_")
                out.append('')
            if i.get('now'):
                out.append(f"- **Now:** {i['now']}")
            if i.get('next_milestone'):
                out.append(f"- **Next:** {i['next_milestone']}")
            if i.get('owner'):
                out.append(f"- **Owner:** {i['owner']}")
            links = i.get('links', {})

            def _fmt(entry):
                """Render a link entry: {label,url} object -> md link; plain string kept as-is."""
                if isinstance(entry, dict):
                    label, url = entry.get('label', '?'), entry.get('url')
                    return f"[{label}]({url})" if url else label
                return str(entry)

            link_bits = []
            for key, title in (('jira', 'Jira'), ('jira_epic', 'Jira'), ('slack', 'Slack'), ('docs', 'Docs')):
                if links.get(key):
                    link_bits.append(f"{title}: " + ', '.join(_fmt(e) for e in links[key]))
            if link_bits:
                out.append(f"- **Links:** {' · '.join(link_bits)}")
            out.append('')

            ws = i.get('workstreams', [])
            if ws:
                out.append('| Sub-item | Phase | Status | PRD | Blocker |')
                out.append('| :-- | :-- | :-- | :-- | :-- |')
                for w in ws:
                    st = STATUS_EMOJI.get(w.get('status'), '') + ' ' + (w.get('status') or '')
                    out.append(f"| {w.get('name')} | {w.get('phase', '-')} | {st.strip()} | "
                               f"{w.get('prd', '-')} | {w.get('blocker') or '-'} |")
                out.append('')

    out.append('---')
    out.append('')
    out.append('_Mirror generated by `.agent/scripts/portfolio_render.py`. '
               'Edit `journal/state/portfolio.json` (source of truth), not this file._')
    out.append('')
    return '\n'.join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='validate JSON only, no write')
    ap.add_argument('--stdout', action='store_true', help='print to stdout instead of writing file')
    args = ap.parse_args()

    if not PORTFOLIO_PATH.exists():
        print(f"ERROR: {PORTFOLIO_PATH} not found", file=sys.stderr)
        return 1
    try:
        data = json.loads(PORTFOLIO_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f"ERROR: portfolio.json invalid JSON: {e}", file=sys.stderr)
        return 1

    n_teams = len(data.get('teams', []))
    n_inits = sum(len(t.get('initiatives', [])) for t in data.get('teams', []))
    if args.check:
        print(f"OK: {n_teams} team(s), {n_inits} initiative(s)")
        return 0

    md = render(data)
    if args.stdout:
        print(md)
        return 0
    OUT_PATH.write_text(md, encoding='utf-8')
    print(f"Wrote {OUT_PATH} ({n_teams} team(s), {n_inits} initiative(s), {len(md)} chars)")
    return 0

if __name__ == '__main__':
    sys.exit(main())
