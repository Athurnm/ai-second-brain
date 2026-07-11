#!/usr/bin/env python3
"""
Work Weekly Reports -> single Google Doc with one native Document Tab per week.

Google Docs supports native document tabs, and (as of 2025) the Docs API can
CREATE them programmatically via the `addDocumentTab` batchUpdate request. This
script maintains one master doc ("Work Weekly Reports") and adds/fills one tab
per weekly report, fully automated. Each new week becomes a tab right after the
cover tab, so the newest week sits at the top of the tab sidebar.

It renders a markdown subset used by the weekly reports:
  - `# / ## / ###`      -> Heading 1 / 2 / 3
  - `* ` or `- `        -> bulleted list item
  - `1. `               -> numbered list item
  - `**bold**`          -> bold run
  - `| a | b |` tables  -> native Docs tables (header row bolded)
  - `________________`  -> rendered as a blank spacer paragraph
  - everything else      -> normal paragraph

Commands:
  ensure-master  --account work [--title "Work Weekly Reports"]
      Find or create the master doc; prints its ID + link.

  add-week  --id MASTER_ID --file report.md --tab-title "Jun 12 - 18, 2026" \
            [--emoji 📊] [--account work] [--position 1]
      Add a tab and populate it from the markdown file. If a tab with the same
      title already exists it is replaced (deleted + re-added) so re-runs are
      idempotent.

Auth: reuses the drive-connector token.json (drive scope is valid for the Docs API).
"""
import os
import re
import sys
import time
import argparse

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SKILL_DIR, '..')
ACCOUNTS = {
    'work':    os.path.join(REPO_ROOT, '.agent/skills/work-drive-connector'),
    'personal': os.path.join(REPO_ROOT, '.agent/skills/google-drive-connector'),
    'secondary': os.path.join(REPO_ROOT, '.agent/skills/secondary-drive-connector'),
}
SCOPES = ['https://www.googleapis.com/auth/drive']
MASTER_TITLE = 'Work Weekly Reports'

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

def services(account):
    from googleapiclient.discovery import build
    creds = authenticate(account)
    docs = build('docs', 'v1', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    return docs, drive

# ----------------------------- markdown parsing -----------------------------

# Inline tokens: **bold** or [text](url). Matched in document order.
INLINE_RE = re.compile(r'\*\*(?P<b>.+?)\*\*|\[(?P<t>[^\]]+)\]\((?P<u>[^)]+)\)')
UNESCAPE_RE = re.compile(r'\\([\\`*_{}\[\]()#+\-.!&<>~|])')

def u16(s):
    """Length in UTF-16 code units -- the unit Google Docs uses for indexes.
    Emoji and other astral characters count as 2, matching the Docs API."""
    return len(s.encode('utf-16-le')) // 2

def unescape_md(text):
    return UNESCAPE_RE.sub(r'\1', text)

def parse_inline(text):
    """Return (clean_text, spans) where spans = [(start, end, style_dict), ...]
    in UTF-16 units. style_dict carries {'bold': True} and/or {'link': url}.
    Markdown backslash escapes are removed from the clean text."""
    out = []
    spans = []
    i = 0
    acc = 0
    for m in INLINE_RE.finditer(text):
        pre = unescape_md(text[i:m.start()])
        out.append(pre)
        acc += u16(pre)
        if m.group('b') is not None:
            inner = unescape_md(m.group('b'))
            start = acc
            out.append(inner)
            acc += u16(inner)
            spans.append((start, acc, {'bold': True}))
        else:
            inner = unescape_md(m.group('t'))
            url = m.group('u')
            start = acc
            out.append(inner)
            acc += u16(inner)
            spans.append((start, acc, {'link': url}))
        i = m.end()
    out.append(unescape_md(text[i:]))
    return ''.join(out), spans

def parse_markdown(md):
    """Parse into an ordered list of block dicts."""
    blocks = []
    lines = md.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        # table: a run of lines starting with '|'
        if stripped.startswith('|'):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl.append(lines[i].strip())
                i += 1
            rows = []
            for r in tbl:
                cells = [c.strip() for c in r.strip('|').split('|')]
                # skip the |:---|:---| separator row
                if all(re.fullmatch(r':?-{2,}:?', c or '-') for c in cells):
                    continue
                rows.append(cells)
            if rows:
                blocks.append({'type': 'table', 'rows': rows})
            continue

        if stripped == '________________' or stripped == '':
            blocks.append({'type': 'spacer'})
            i += 1
            continue

        if stripped.startswith('### '):
            blocks.append({'type': 'h3', 'text': stripped[4:]})
        elif stripped.startswith('## '):
            blocks.append({'type': 'h2', 'text': stripped[3:]})
        elif stripped.startswith('# '):
            blocks.append({'type': 'h1', 'text': stripped[2:]})
        elif stripped.startswith('* ') or stripped.startswith('- '):
            blocks.append({'type': 'bullet', 'text': stripped[2:]})
        elif re.match(r'^\d+\.\s', stripped):
            blocks.append({'type': 'number', 'text': re.sub(r'^\d+\.\s', '', stripped)})
        else:
            blocks.append({'type': 'para', 'text': stripped})
        i += 1
    return blocks

# ----------------------------- docs helpers -----------------------------

NAMED = {'h1': 'HEADING_1', 'h2': 'HEADING_2', 'h3': 'HEADING_3'}
TABLE_MARK = '⁣TBL%d⁣'  # invisible-ish unique marker per table

def get_tab(docs, doc_id, tab_id):
    doc = docs.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    for t in doc.get('tabs', []):
        if t['tabProperties']['tabId'] == tab_id:
            return t
    raise RuntimeError('tab %s not found' % tab_id)

def find_tab_by_title(docs, doc_id, title):
    doc = docs.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    for t in doc.get('tabs', []):
        if t['tabProperties'].get('title') == title:
            return t['tabProperties']['tabId']
    return None

def tab_body_elements(tab):
    return tab['documentTab']['body']['content']

def locate_text(tab, needle):
    """Return absolute start index of `needle` within the tab body, or None."""
    for el in tab_body_elements(tab):
        para = el.get('paragraph')
        if not para:
            continue
        for pe in para.get('elements', []):
            tr = pe.get('textRun')
            if tr and needle in tr.get('content', ''):
                off = tr['content'].index(needle)
                return pe['startIndex'] + off
    return None

# ----------------------------- tab population -----------------------------

def populate_tab(docs, doc_id, tab_id, blocks):
    """Insert text (with table markers), style it, then build real tables."""
    # 1) Build one text stream; tables become a marker paragraph.
    text = ''
    styles = []   # (start, end, kind, payload)
    inlines = []  # (start, end, style_dict)
    bullets = []  # (start, end, ordered)
    tables = []   # (marker_string, rows)
    tbl_n = 0
    cursor = 1    # tab body first position

    def emit(s):
        nonlocal text
        text += s

    for b in blocks:
        if b['type'] == 'table':
            mark = TABLE_MARK % tbl_n
            tbl_n += 1
            start = cursor
            emit(mark + '\n')
            cursor += u16(mark) + 1
            tables.append((mark, b['rows']))
            continue
        if b['type'] == 'spacer':
            emit('\n')
            cursor += 1
            continue
        clean, spans = parse_inline(b['text'])
        start = cursor
        emit(clean + '\n')
        end = cursor + u16(clean)
        cursor += u16(clean) + 1
        for (bs, be, sty) in spans:
            inlines.append((start + bs, start + be, sty))
        if b['type'] in NAMED:
            styles.append((start, end + 1, 'heading', NAMED[b['type']]))
        elif b['type'] == 'bullet':
            bullets.append((start, end, False))
        elif b['type'] == 'number':
            bullets.append((start, end, True))

    # 2) Insert the whole text body at once.
    reqs = [{'insertText': {'location': {'index': 1, 'tabId': tab_id}, 'text': text}}]
    docs.documents().batchUpdate(documentId=doc_id, body={'requests': reqs}).execute()

    # 3) Apply paragraph styles (headings) + bullets + bold, one batch.
    style_reqs = []
    for (s, e, kind, payload) in styles:
        style_reqs.append({'updateParagraphStyle': {
            'range': {'startIndex': s, 'endIndex': e, 'tabId': tab_id},
            'paragraphStyle': {'namedStyleType': payload},
            'fields': 'namedStyleType'}})
    for (s, e, ordered) in bullets:
        preset = 'NUMBERED_DECIMAL_ALPHA_ROMAN' if ordered else 'BULLET_DISC_CIRCLE_SQUARE'
        style_reqs.append({'createParagraphBullets': {
            'range': {'startIndex': s, 'endIndex': e, 'tabId': tab_id},
            'bulletPreset': preset}})
    for (s, e, sty) in inlines:
        ts, fields = {}, []
        if sty.get('bold'):
            ts['bold'] = True
            fields.append('bold')
        if sty.get('link'):
            ts['link'] = {'url': sty['link']}
            fields.append('link')
        style_reqs.append({'updateTextStyle': {
            'range': {'startIndex': s, 'endIndex': e, 'tabId': tab_id},
            'textStyle': ts, 'fields': ','.join(fields)}})
    if style_reqs:
        docs.documents().batchUpdate(documentId=doc_id, body={'requests': style_reqs}).execute()

    # 4) Build tables in REVERSE order (so earlier marker indexes stay valid).
    for (mark, rows) in reversed(tables):
        _build_table(docs, doc_id, tab_id, mark, rows)

def _build_table(docs, doc_id, tab_id, mark, rows):
    nrows = len(rows)
    ncols = max(len(r) for r in rows)
    # delete the marker, insert an empty table at that spot
    tab = get_tab(docs, doc_id, tab_id)
    mi = locate_text(tab, mark)
    if mi is None:
        raise RuntimeError('table marker %r not found' % mark)
    docs.documents().batchUpdate(documentId=doc_id, body={'requests': [
        {'deleteContentRange': {'range': {'startIndex': mi, 'endIndex': mi + u16(mark), 'tabId': tab_id}}},
        {'insertTable': {'rows': nrows, 'columns': ncols,
                         'location': {'index': mi, 'tabId': tab_id}}},
    ]}).execute()

    # re-fetch, collect each cell's paragraph start index
    tab = get_tab(docs, doc_id, tab_id)
    table = None
    for el in tab_body_elements(tab):
        if el.get('table') and el['startIndex'] >= mi:
            table = el
            break
    if table is None:
        raise RuntimeError('inserted table not found')

    # gather (index, text, is_header) for every cell, then fill bottom-up
    fills = []
    for r, row in enumerate(table['table']['tableRows']):
        for c, cell in enumerate(row['tableCells']):
            cell_start = cell['content'][0]['startIndex']
            val = rows[r][c] if c < len(rows[r]) else ''
            clean, _ = parse_inline(val)
            fills.append((cell_start, clean))
    fills.sort(key=lambda x: x[0], reverse=True)
    reqs = []
    for (idx, clean) in fills:
        if clean:
            reqs.append({'insertText': {'location': {'index': idx, 'tabId': tab_id}, 'text': clean}})
    if reqs:
        docs.documents().batchUpdate(documentId=doc_id, body={'requests': reqs}).execute()

    # style cells: header row fully bold; body cells get their inline bold/link
    tab = get_tab(docs, doc_id, tab_id)
    for el in tab_body_elements(tab):
        if el.get('table') and el['startIndex'] >= mi:
            table = el
            break
    style_reqs = []
    for r, row in enumerate(table['table']['tableRows']):
        for c, cell in enumerate(row['tableCells']):
            val = rows[r][c] if c < len(rows[r]) else ''
            clean, spans = parse_inline(val)
            if not clean:
                continue
            cs = cell['content'][0]['startIndex']
            if r == 0:
                style_reqs.append({'updateTextStyle': {
                    'range': {'startIndex': cs, 'endIndex': cs + u16(clean), 'tabId': tab_id},
                    'textStyle': {'bold': True}, 'fields': 'bold'}})
            else:
                for (bs, be, sty) in spans:
                    ts, fields = {}, []
                    if sty.get('bold'):
                        ts['bold'] = True
                        fields.append('bold')
                    if sty.get('link'):
                        ts['link'] = {'url': sty['link']}
                        fields.append('link')
                    style_reqs.append({'updateTextStyle': {
                        'range': {'startIndex': cs + bs, 'endIndex': cs + be, 'tabId': tab_id},
                        'textStyle': ts, 'fields': ','.join(fields)}})
    if style_reqs:
        docs.documents().batchUpdate(documentId=doc_id, body={'requests': style_reqs}).execute()

# ----------------------------- commands -----------------------------

def cmd_ensure_master(args):
    docs, drive = services(args.account)
    title = args.title or MASTER_TITLE
    q = ("name = '%s' and mimeType = 'application/vnd.google-apps.document' "
         "and trashed = false") % title.replace("'", "\\'")
    res = drive.files().list(q=q, fields='files(id,name)', pageSize=5).execute()
    files = res.get('files', [])
    if files:
        doc_id = files[0]['id']
        print('Found existing master: %s' % doc_id)
    else:
        doc = docs.documents().create(body={'title': title}).execute()
        doc_id = doc['documentId']
        # rename the default tab to a cover
        tabs = docs.documents().get(documentId=doc_id, includeTabsContent=True).execute().get('tabs', [])
        if tabs:
            cover_id = tabs[0]['tabProperties']['tabId']
            docs.documents().batchUpdate(documentId=doc_id, body={'requests': [
                {'updateDocumentTabProperties': {
                    'tabProperties': {'tabId': cover_id, 'title': 'Index', 'index': 0},
                    'fields': 'title'}},
            ]}).execute()
            populate_tab(docs, doc_id, cover_id, parse_markdown(
                '# Work Weekly Reports\n\nMaster archive. Each tab is one weekly progress report, '
                'newest at the top. Maintained by the weekly-report workflow.\n'))
        print('Created master: %s' % doc_id)
    print('Link: https://docs.google.com/document/d/%s/edit' % doc_id)
    return doc_id

def cmd_add_week(args):
    docs, drive = services(args.account)
    with open(args.file, encoding='utf-8') as f:
        md = f.read()
    blocks = parse_markdown(md)

    existing = find_tab_by_title(docs, args.id, args.tab_title)
    if existing:
        docs.documents().batchUpdate(documentId=args.id, body={'requests': [
            {'deleteTab': {'tabId': existing}}]}).execute()
        print('Replaced existing tab "%s"' % args.tab_title)

    props = {'title': args.tab_title, 'index': args.position}
    if args.emoji:
        props['iconEmoji'] = args.emoji
    docs.documents().batchUpdate(documentId=args.id, body={'requests': [
        {'addDocumentTab': {'tabProperties': props}}]}).execute()

    tab_id = find_tab_by_title(docs, args.id, args.tab_title)
    if not tab_id:
        raise RuntimeError('failed to create tab')
    populate_tab(docs, args.id, tab_id, blocks)
    print('Added tab "%s" (tabId %s)' % (args.tab_title, tab_id))
    print('Link: https://docs.google.com/document/d/%s/edit?tab=%s' % (args.id, tab_id))

def main():
    p = argparse.ArgumentParser(description='Work Weekly Reports tabbed doc builder')
    sub = p.add_subparsers(dest='cmd', required=True)

    pm = sub.add_parser('ensure-master')
    pm.add_argument('--account', default='work', choices=list(ACCOUNTS.keys()))
    pm.add_argument('--title')
    pm.set_defaults(func=cmd_ensure_master)

    pa = sub.add_parser('add-week')
    pa.add_argument('--id', required=True)
    pa.add_argument('--file', required=True)
    pa.add_argument('--tab-title', required=True)
    pa.add_argument('--emoji')
    pa.add_argument('--position', type=int, default=1)
    pa.add_argument('--account', default='work', choices=list(ACCOUNTS.keys()))
    pa.set_defaults(func=cmd_add_week)

    args = p.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
