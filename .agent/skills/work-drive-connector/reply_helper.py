#!/usr/bin/env python3
"""Helper: identify token owner, list comment IDs, and post replies to Google Doc comments (as the token owner)."""
import os, sys, json, argparse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, 'token.json')
SCOPES = ['https://www.googleapis.com/auth/drive']

def svc():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('drive', 'v3', credentials=creds)

def whoami():
    s = svc()
    about = s.about().get(fields='user').execute()
    print(json.dumps(about.get('user', {}), indent=2))

def list_ids(file_id):
    s = svc()
    res = s.comments().list(fileId=file_id,
        fields="comments(id,content,author(displayName),resolved,replies(author(displayName),content))",
        pageSize=100).execute()
    for i, c in enumerate(res.get('comments', []), 1):
        au = c.get('author', {}).get('displayName', '?')
        content = (c.get('content', '') or '').replace('\n', ' ')[:60]
        resolved = c.get('resolved', False)
        print(f"[{i}] id={c['id']} resolved={resolved} {au}: {content}")

def reply(file_id, comment_id, text, resolve=False):
    s = svc()
    body = {'content': text}
    if resolve:
        body['action'] = 'resolve'
    r = s.replies().create(fileId=file_id, commentId=comment_id, body=body,
        fields='id,content,author(displayName),action').execute()
    print(json.dumps(r, indent=2))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('whoami')
    li = sub.add_parser('list'); li.add_argument('--id', required=True)
    rp = sub.add_parser('reply')
    rp.add_argument('--id', required=True); rp.add_argument('--comment', required=True)
    rp.add_argument('--text', required=True); rp.add_argument('--resolve', action='store_true')
    a = p.parse_args()
    if a.cmd == 'whoami': whoami()
    elif a.cmd == 'list': list_ids(a.id)
    elif a.cmd == 'reply': reply(a.id, a.comment, a.text, a.resolve)
    else: p.print_help()
