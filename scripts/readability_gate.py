#!/usr/bin/env python3
"""Readability gate for Work docs, run BEFORE and AFTER publishing.

Catches the failure mode that shipped twice on 16-17 Jul 2026: a doc written as bare
consecutive sentence-lines with no markdown structure, which converts into an
unreadable wall of text in Google Docs.

Two modes:
  --source <file.md>   lint the markdown BEFORE publishing (the real fix point)
  --doc <DOC_ID>       verify the published Google Doc AFTER converting

Exit 0 = clean, exit 1 = blocked. Fix the SOURCE, never the doc by hand.
"""
import argparse
import re
import sys

WALL_MIN = 2          # 2+ consecutive bare prose lines is a wall block
STRUCT_PREFIX = ('|', '-', '*', '#', '>', '[[', '<!--', '```')

def lint_source(path: str) -> int:
    lines = open(path, encoding='utf-8').read().splitlines()
    fenced = False
    walls, cur, start = [], 0, 0
    missing_blank_table, missing_blank_list = [], []
    emdash = []

    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith('```'):
            fenced = not fenced
            if cur >= WALL_MIN:
                walls.append((start, cur))
            cur = 0
            continue
        if fenced:
            continue

        if '—' in raw:
            emdash.append(i + 1)

        prev = lines[i - 1].strip() if i else ''
        # A table/list must not sit directly under a PARAGRAPH line. Headings and
        # blockquotes are block-level, so the converter handles those fine.
        prev_is_block = (not prev) or prev.startswith(('#', '>', '<!--'))
        if s.startswith('|') and not prev_is_block and not prev.startswith('|'):
            missing_blank_table.append(i + 1)
        if re.match(r'^([-*]|\d+\.)\s', s) and not prev_is_block \
                and not re.match(r'^([-*]|\d+\.)\s', prev):
            missing_blank_list.append(i + 1)

        is_struct = (not s) or s.startswith(STRUCT_PREFIX) or bool(re.match(r'^\d+\.\s', s))
        if is_struct:
            if cur >= WALL_MIN:
                walls.append((start, cur))
            cur = 0
        else:
            if cur == 0:
                start = i + 1
            cur += 1
    if cur >= WALL_MIN:
        walls.append((start, cur))

    fails = []
    if walls:
        total = sum(n for _, n in walls)
        fails.append(
            f"{len(walls)} wall-of-text block(s), {total} bare prose lines. "
            f"Biggest at line {max(walls, key=lambda w: w[1])[0]} "
            f"({max(n for _, n in walls)} lines).\n"
            f"      Bare consecutive sentence-lines are NOT a list. Make each block a "
            f"table, real bullets, or one joined paragraph.\n"
            f"      Lines: {', '.join(str(s) for s, _ in walls[:12])}"
        )
    if missing_blank_table:
        fails.append(f"table(s) with no blank line before, at line(s): {missing_blank_table[:12]}")
    if missing_blank_list:
        fails.append(f"list(s) with no blank line before, at line(s): {missing_blank_list[:12]}")
    if emdash:
        fails.append(f"em-dash character at line(s): {emdash[:12]}")

    if fails:
        print(f"[GATE FAIL] {path}")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"[GATE PASS] {path}")
    return 0

def verify_doc(doc_id: str, account: str, allow_public: bool = False) -> int:
    sys.path.insert(0, '.agent/skills/gdocs-create')
    from gdocs_create import authenticate  # noqa: E402
    from googleapiclient.discovery import build  # noqa: E402

    drive = build('drive', 'v3', credentials=authenticate(account))
    html = drive.files().export(fileId=doc_id, mimeType='text/html').execute().decode()

    tables = len(re.findall(r'<table', html))
    li = len(re.findall(r'<li', html))
    img = len(re.findall(r'<img', html))
    leftover = html.count('[[') + html.count(':---') + html.count('```')

    perms = drive.permissions().list(
        fileId=doc_id, fields='permissions(type,role,domain,emailAddress)').execute()['permissions']
    public = any(p['type'] == 'anyone' for p in perms)

    print(f"  tables={tables} li={li} img={img} leftover={leftover} public={public}")

    fails = []
    if leftover:
        fails.append(f"{leftover} unconverted marker(s): raw [[placeholder]], :--- or ``` survived the convert")
    if public and not allow_public:
        fails.append("doc is PUBLIC (anyone with link). Run drive_permissions.py restrict LAST")
    if tables == 0 and li == 0:
        fails.append("doc has zero tables and zero list items: it is a wall of text")

    if fails:
        print(f"[GATE FAIL] doc {doc_id}")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"[GATE PASS] doc {doc_id}")
    return 0

def main():
    ap = argparse.ArgumentParser(description='Readability gate for Work docs')
    ap.add_argument('--source', help='markdown file to lint before publishing')
    ap.add_argument('--doc', help='Google Doc ID to verify after publishing')
    ap.add_argument('--account', default='work', choices=['work', 'personal', 'secondary'])
    ap.add_argument('--allow-public', action='store_true',
                     help='skip the public-permission check (doc intentionally left public)')
    args = ap.parse_args()

    if not args.source and not args.doc:
        ap.error('pass --source and/or --doc')

    rc = 0
    if args.source:
        rc |= lint_source(args.source)
    if args.doc:
        rc |= verify_doc(args.doc, args.account, allow_public=args.allow_public)
    return rc

if __name__ == '__main__':
    sys.exit(main())
