#!/usr/bin/env bash
# Publish a Work PRD/BRD to Google Docs, correctly, in one command.
#
# Exists because the manual sequence was run by hand on 16-17 Jul 2026 and steps
# got skipped twice, shipping wall-of-text docs and leaving one publicly shared.
# The order below is not negotiable:
#   gate source -> convert -> embed diagrams -> format pass -> restrict LAST -> verify doc
# "restrict LAST" matters: every convert re-publishes the doc as "anyone with link".
#
# Usage:
#   scripts/publish_prd.sh --file <path.md> --id <DOC_ID> [--account work]
#   scripts/publish_prd.sh --file <path.md> --title "PRD: ..." [--account work]   # first publish
#   scripts/publish_prd.sh --file <path.md> --id <DOC_ID> --share Teammate@examplevendor.com
#
# Options:
#   --no-restrict   skip the domain restriction (only for a doc meant to stay public)
#   --gate-only     lint the source and stop
set -euo pipefail

cd "$(dirname "$0")/.."

FILE=""; ID=""; TITLE=""; ACCOUNT="work"; SHARE=""; RESTRICT=1; GATE_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --file) FILE="$2"; shift 2;;
    --id) ID="$2"; shift 2;;
    --title) TITLE="$2"; shift 2;;
    --account) ACCOUNT="$2"; shift 2;;
    --share) SHARE="$2"; shift 2;;
    --no-restrict) RESTRICT=0; shift;;
    --gate-only) GATE_ONLY=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

[[ -z "$FILE" ]] && { echo "ERROR: --file is required" >&2; exit 2; }
[[ ! -f "$FILE" ]] && { echo "ERROR: no such file: $FILE" >&2; exit 2; }
[[ -z "$ID" && -z "$TITLE" ]] && { echo "ERROR: pass --id to update, or --title to create" >&2; exit 2; }

echo "==> [1/6] Readability gate on source"
python3 scripts/readability_gate.py --source "$FILE" || {
  echo ""
  echo "BLOCKED. Fix the SOURCE markdown, never the Google Doc by hand." >&2
  exit 1
}
[[ $GATE_ONLY -eq 1 ]] && exit 0

if [[ -n "$ID" ]]; then
  echo "==> [2/6] Converting into existing doc $ID"
  python3 .agent/skills/work-drive-connector/gdrive_manager.py update --id "$ID" --file "$FILE" --convert >/dev/null
else
  echo "==> [2/6] Creating new doc: $TITLE"
  OUT=$(timeout 180s python3 .agent/skills/gdocs-create/gdocs_create.py create-doc \
        --title "$TITLE" --file "$FILE" --account "$ACCOUNT")
  echo "$OUT"
  ID=$(echo "$OUT" | grep -oP 'ID:\s*\K[A-Za-z0-9_-]+' | head -1)
  [[ -z "$ID" ]] && { echo "ERROR: no file ID returned, treat as FAILURE" >&2; exit 1; }
fi

echo "==> [3/6] Embedding mermaid diagrams"
# || guard: under set -e a failing command substitution would kill the script
# before the error output below ever prints.
EMBED_RC=0
EMBED_OUT=$(python3 scripts/embed_mermaid_in_gdoc.py --id "$ID" --account "$ACCOUNT" 2>&1) || EMBED_RC=$?
echo "$EMBED_OUT"
if [[ $EMBED_RC -ne 0 ]]; then
  echo "ERROR: mermaid embed step failed" >&2
  exit 1
elif ! grep -qE "EMBEDDED|error" <<<"$EMBED_OUT"; then
  echo "  (no placeholders in this doc)"
fi

echo "==> [4/6] Formatting pass"
python3 .agent/skills/gdocs-create/format_pass.py "$ID" --account "$ACCOUNT"

if [[ -n "$SHARE" ]]; then
  echo "==> [5/6] Sharing commenter access to $SHARE"
  python3 - "$ID" "$ACCOUNT" "$SHARE" <<'PY'
import sys
sys.path.insert(0, '.agent/skills/gdocs-create')
from gdocs_create import authenticate
from googleapiclient.discovery import build
doc_id, account, emails = sys.argv[1], sys.argv[2], sys.argv[3]
drive = build('drive', 'v3', credentials=authenticate(account))
for email in [e.strip() for e in emails.split(',') if e.strip()]:
    drive.permissions().create(
        fileId=doc_id,
        body={'type': 'user', 'role': 'commenter', 'emailAddress': email},
        sendNotificationEmail=False,
    ).execute()
    print(f"  granted commenter: {email}")
PY
else
  echo "==> [5/6] No --share requested, skipping"
fi

if [[ $RESTRICT -eq 1 ]]; then
  echo "==> [6/6] Restricting to yourcompany.com (LAST, converts re-publish public)"
  python3 .agent/scripts/drive_permissions.py restrict "$ID" --domain yourcompany.com --apply | tail -2
else
  echo "==> [6/6] --no-restrict passed, doc left as-is"
fi

echo ""
echo "==> Verifying published doc"
GATE_ARGS=(--doc "$ID" --account "$ACCOUNT")
[[ $RESTRICT -eq 0 ]] && GATE_ARGS+=(--allow-public)
python3 scripts/readability_gate.py "${GATE_ARGS[@]}" || {
  echo "Published doc failed verification. Investigate before sharing the link." >&2
  exit 1
}

echo ""
echo "File published: $FILE"
echo "  ID:  $ID"
echo "  URL: https://docs.google.com/document/d/$ID/edit"
