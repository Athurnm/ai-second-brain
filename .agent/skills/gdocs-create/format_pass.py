#!/usr/bin/env python3
"""
gdocs-create formatting pass (run AFTER every create-doc / update --convert with tables).

Does three things:
  1. Sets the document to PAGELESS mode (markdown->GDoc conversion creates PAGES/letter
     docs; You wants Work docs pageless). Skip with --keep-pages.
  2. Widens table columns to fill the width on pageless GDocs (conversion leaves the
     legacy ~468pt total, which looks cramped for 4-5 col tables). Per-table semantic
     weights by column count.
  3. Lints the rendered doc for AI-tell artifacts that survive conversion and read
     messy: literal " -- " / "--" and "->". These MUST be rephrased in the source
     (colon/comma/restructure per feedback_no_emdash_rephrase), never left as dashes.
     Exits non-zero if any are found so the caller re-converts instead of sharing.

NOTE: `update --convert` resets documentMode back to PAGES and re-publishes the doc
public every time, so run this pass (and drive_permissions.py restrict) AFTER the
final convert, not before.

Usage:
  python3 .agent/skills/gdocs-create/format_pass.py <doc_id> [<doc_id> ...] \
      [--account work|personal|secondary] [--total-width 700] [--keep-pages]

Auth reuses the same token as gdocs_create.py (per --account).
"""
import os, sys, argparse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
ACCOUNTS = {
    'work':     os.path.join(REPO, '.agent/skills/work-drive-connector/token.json'),
    'personal':  os.path.join(REPO, '.agent/skills/google-drive-connector/token.json'),
    'secondary': os.path.join(REPO, '.agent/skills/secondary-drive-connector/token.json'),
}
SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']

# per-column-count weight profiles (sum to 1.0); tuned for MOM/PRD-style tables.
# 2col=metadata(label,value); 3col=(#,decision,rationale); 4col=(#,item,owner,meta);
# 5col=(#,task,owner,deadline,priority)
WEIGHTS = {
    2: [0.22, 0.78],
    3: [0.07, 0.51, 0.42],
    4: [0.06, 0.50, 0.24, 0.20],
    5: [0.05, 0.42, 0.20, 0.20, 0.13],
}

def svc(account):
    tok = ACCOUNTS[account]
    c = Credentials.from_authorized_user_file(tok, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request()); open(tok, 'w').write(c.to_json())
    return build('docs', 'v1', credentials=c)

def set_pageless(docs, doc_id):
    docs.documents().batchUpdate(documentId=doc_id, body={'requests': [{
        'updateDocumentStyle': {
            'documentStyle': {'documentFormat': {'documentMode': 'PAGELESS'}},
            'fields': 'documentFormat.documentMode'}}]}).execute()

def widen_and_lint(docs, doc_id, total):
    doc = docs.documents().get(documentId=doc_id).execute()
    reqs, bad = [], []

    def walk(elems):
        for el in elems:
            p = el.get('paragraph')
            if p:
                txt = ''.join(r.get('textRun', {}).get('content', '') for r in p.get('elements', []))
                if ' -- ' in txt or '--' in txt or '->' in txt:
                    bad.append(txt.strip()[:80])
            t = el.get('table')
            if t:
                start = el['startIndex']; ncols = t['columns']
                w = WEIGHTS.get(ncols, [1.0 / ncols] * ncols)
                for ci in range(ncols):
                    reqs.append({'updateTableColumnProperties': {
                        'tableStartLocation': {'index': start}, 'columnIndices': [ci],
                        'tableColumnProperties': {'widthType': 'FIXED_WIDTH',
                                                  'width': {'magnitude': total * w[ci], 'unit': 'PT'}},
                        'fields': 'widthType,width'}})
                for row in t['tableRows']:
                    for cell in row['tableCells']:
                        walk(cell['content'])
    walk(doc['body']['content'])
    if reqs:
        docs.documents().batchUpdate(documentId=doc_id, body={'requests': reqs}).execute()
    return len(reqs), bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='+')
    ap.add_argument('--account', default='work', choices=list(ACCOUNTS))
    ap.add_argument('--total-width', type=float, default=700.0)
    ap.add_argument('--keep-pages', action='store_true', help='do not switch to pageless')
    a = ap.parse_args()
    docs = svc(a.account)
    fail = False
    for did in a.ids:
        if not a.keep_pages:
            set_pageless(docs, did)
        n, bad = widen_and_lint(docs, did, a.total_width)
        print(f'{did}: pageless={not a.keep_pages}, widened {n} columns')
        if bad:
            fail = True
            print(f'  [LINT FAIL] {len(bad)} paragraph(s) still contain "--" or "->". Rephrase the source and re-convert:')
            for b in bad[:10]:
                print(f'    - {b}')
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main()
