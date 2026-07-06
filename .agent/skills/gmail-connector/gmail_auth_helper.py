#!/usr/bin/env python3
"""Headless two-step Gmail OAuth: `auth-url` prints the consent URL and persists the PKCE
verifier; `auth-save --code` exchanges the pasted code and writes token_gmail_work.json.
Reuses the Work Drive OAuth client (same credentials.json + localhost:8080 redirect)."""
import os, sys, json, argparse
from google_auth_oauthlib.flow import Flow

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
CREDENTIALS_FILE = os.path.join(BASE_DIR, '.agent', 'skills', 'work-drive-connector', 'credentials.json')
TOKEN_FILE = os.path.join(SCRIPT_DIR, 'token_gmail_work.json')
STATE_FILE = os.path.join(SCRIPT_DIR, '.gmail_auth_state.json')
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
REDIRECT = 'http://localhost:8080/'

def _flow():
    f = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES)
    f.redirect_uri = REDIRECT
    return f

def auth_url():
    f = _flow()
    url, _ = f.authorization_url(prompt='consent', access_type='offline')
    with open(STATE_FILE, 'w') as s:
        json.dump({'code_verifier': f.code_verifier}, s)
    print(url)

def auth_save(code):
    if not os.path.exists(STATE_FILE):
        print("ERROR: run auth-url first (no PKCE state saved)."); sys.exit(1)
    verifier = json.load(open(STATE_FILE)).get('code_verifier')
    f = _flow()
    f.code_verifier = verifier
    f.fetch_token(code=code)
    with open(TOKEN_FILE, 'w') as t:
        t.write(f.credentials.to_json())
    os.remove(STATE_FILE)
    print(f"OK: token saved to {TOKEN_FILE}")

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('auth-url')
    sv = sub.add_parser('auth-save'); sv.add_argument('--code', required=True)
    a = p.parse_args()
    if a.cmd == 'auth-url': auth_url()
    elif a.cmd == 'auth-save': auth_save(a.code)
    else: p.print_help()
