#!/usr/bin/env python3
"""
Balance Google Doc table column widths by content length.

Goal: set each table column's width proportional to the longest cell text in
that column, normalized to the page's usable width, so one text-heavy cell
does not wrap into many lines while sibling columns sit nearly empty.

Per-column minimum (hard rule): every column is at least wide enough to hold
its single longest WORD on one line. No column is ever narrowed to the point
where a word has to break across lines. The minimum width per column is
max(--min-pt floor, longest-word-width), where longest-word-width is estimated
from the column's longest whitespace-delimited token (--char-pt per character
plus --cell-pad-pt of cell padding). If the sum of per-column minimums cannot
fit the usable width, the minimums are scaled down proportionally and a warning
is printed.

Pageless: defaults to switching the document to PAGELESS mode (so wide tables
are not clipped by the page edge). Pass --no-pageless to keep paged layout.

Usage:
  python3 scripts/set_gdoc_table_widths.py --id DOC_ID --account work \
      [--min-pt 48] [--char-pt 6.5] [--cell-pad-pt 12] [--no-pageless] [--dry-run]

Auth: reuses the drive-connector token.json (drive scope is valid for Docs API).
"""
import os
import sys
import argparse

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SKILL_DIR, '..')
ACCOUNTS = {
    'work':    os.path.join(REPO_ROOT, '.agent/skills/work-drive-connector'),
    'personal': os.path.join(REPO_ROOT, '.agent/skills/google-drive-connector'),
    'secondary': os.path.join(REPO_ROOT, '.agent/skills/secondary-drive-connector'),
}
SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate(account):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    token_path = os.path.join(ACCOUNTS[account], 'token.json')
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())
    return creds

def cell_text(cell):
    out = []
    for el in cell.get('content', []):
        para = el.get('paragraph')
        if not para:
            continue
        for pe in para.get('elements', []):
            tr = pe.get('textRun')
            if tr:
                out.append(tr.get('content', ''))
    return ''.join(out).strip()

def longest_word_len(text):
    """Longest whitespace-delimited token, in characters."""
    return max((len(w) for w in text.split()), default=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', required=True)
    ap.add_argument('--account', default='work', choices=list(ACCOUNTS))
    ap.add_argument('--min-pt', type=float, default=48.0,
                    help='base minimum column width in points')
    ap.add_argument('--char-pt', type=float, default=6.5,
                    help='estimated point width per character (~11pt body font)')
    ap.add_argument('--cell-pad-pt', type=float, default=12.0,
                    help='left+right cell padding added to the word-fit minimum')
    ap.add_argument('--pageless', action=argparse.BooleanOptionalAction,
                    default=True, help='switch the doc to PAGELESS mode (default on)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    from googleapiclient.discovery import build
    docs = build('docs', 'v1', credentials=authenticate(args.account))
    doc = docs.documents().get(documentId=args.id).execute()

    ds = doc.get('documentStyle', {})
    pw = ds.get('pageSize', {}).get('width', {}).get('magnitude', 612.0)
    ml = ds.get('marginLeft', {}).get('magnitude', 72.0)
    mr = ds.get('marginRight', {}).get('magnitude', 72.0)
    usable = pw - ml - mr
    print(f"Page usable width: {usable:.1f}pt (page {pw:.0f}, margins {ml:.0f}/{mr:.0f})")

    requests = []

    # Pageless mode (default on): keep wide tables from being clipped by the page edge.
    cur_mode = ds.get('documentFormat', {}).get('documentMode', 'PAGES')
    if args.pageless and cur_mode != 'PAGELESS':
        requests.append({
            'updateDocumentStyle': {
                'documentStyle': {'documentFormat': {'documentMode': 'PAGELESS'}},
                'fields': 'documentFormat',
            }
        })
        print("Document mode: PAGES -> PAGELESS")
    elif args.pageless:
        print("Document mode: already PAGELESS")

    tnum = 0
    for el in doc.get('body', {}).get('content', []):
        table = el.get('table')
        if not table:
            continue
        tnum += 1
        start = el['startIndex']
        ncol = table.get('columns') or len(table['tableRows'][0]['tableCells'])

        # longest cell text (for weighting) and longest single word (for the floor) per column
        maxlen = [1] * ncol
        maxword = [1] * ncol
        for row in table['tableRows']:
            for j, cell in enumerate(row['tableCells']):
                if j < ncol:
                    txt = cell_text(cell)
                    maxlen[j] = max(maxlen[j], len(txt))
                    maxword[j] = max(maxword[j], longest_word_len(txt))

        # per-column minimum: at least the base floor, and always wide enough
        # to hold the column's longest word on one line.
        base_floor = min(args.min_pt, usable / ncol)
        word_cap = usable * 0.85  # a single token longer than this cannot be fit anyway
        col_floor = [max(base_floor, min(word_cap, w * args.char_pt + args.cell_pad_pt))
                     for w in maxword]
        # if the minimums cannot all fit, scale them down proportionally (and warn)
        if sum(col_floor) > usable:
            print(f"  ! Table {tnum}: word-fit minimums ({sum(col_floor):.0f}pt) exceed "
                  f"usable width ({usable:.0f}pt); scaling minimums down - a long word may wrap.")
            s = usable / sum(col_floor)
            col_floor = [w * s for w in col_floor]

        # weight by content length, then enforce per-column floors
        widths = [usable * (m / sum(maxlen)) for m in maxlen]
        for _ in range(ncol * 2):
            deficit = sum(max(0.0, col_floor[i] - widths[i]) for i in range(ncol))
            if deficit <= 0.01:
                break
            donors = [i for i in range(ncol) if widths[i] > col_floor[i]]
            donor_total = sum(widths[i] - col_floor[i] for i in donors)
            if not donors or donor_total <= 0:
                widths = list(col_floor)
                break
            for i in donors:
                widths[i] -= deficit * (widths[i] - col_floor[i]) / donor_total
            widths = [max(widths[i], col_floor[i]) for i in range(ncol)]
        # final normalize for rounding drift (sum already ~usable, so floors hold)
        scale = usable / sum(widths)
        widths = [w * scale for w in widths]

        print(f"Table {tnum} (start {start}, {ncol} cols): "
              f"maxchars={maxlen} maxword={maxword} "
              f"minPt={[round(c) for c in col_floor]} -> widths={[round(w) for w in widths]}pt")

        for j, w in enumerate(widths):
            requests.append({
                'updateTableColumnProperties': {
                    'tableStartLocation': {'index': start},
                    'columnIndices': [j],
                    'tableColumnProperties': {
                        'widthType': 'FIXED_WIDTH',
                        'width': {'magnitude': round(w, 1), 'unit': 'PT'},
                    },
                    'fields': 'width,widthType',
                }
            })

    if tnum == 0:
        print("No tables found.")
    if not requests:
        return
    if args.dry_run:
        print(f"\n[dry-run] {len(requests)} requests across {tnum} tables. Not applied.")
        return

    docs.documents().batchUpdate(documentId=args.id,
                                 body={'requests': requests}).execute()
    print(f"\nApplied {len(requests)} requests across {tnum} tables.")
    print(f"Link: https://docs.google.com/document/d/{args.id}/edit")

if __name__ == '__main__':
    main()
