#!/usr/bin/env python3
"""Embed local PNG/JPG screenshots into a Google Doc at text placeholders.

Generic version of embed_brd_gc_screenshots.py. Given a --spec JSON mapping each
placeholder token (e.g. "[[IMG:01]]") to a local image path + display width, it:
  1. uploads each image to Drive (work/personal account),
  2. makes it readable-by-link (so the inline-image URI loads at insert time),
  3. finds the placeholder text in the doc and replaces it with an inline image,
  4. trashes the temp Drive upload (the doc keeps its own copy of the image).

Run AFTER a gdocs-create / update --convert that placed the placeholder tokens.
Idempotent: a placeholder already replaced is skipped.

Usage:
  python3 scripts/embed_images_in_gdoc.py --id DOC_ID --account work \
      --spec /path/to/spec.json
spec.json: {"[[IMG:01]]": {"path": "screens/01.png", "width_pt": 430}, ...}
Height is auto-computed from the image aspect ratio (Pillow).
"""
import argparse, json, time, os, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    from PIL import Image
except ImportError:
    Image = None

TOKENS = {"work": ".agent/skills/work-drive-connector/token.json",
          "personal": ".agent/skills/google-drive-connector/token.json"}
URI = "https://lh3.googleusercontent.com/d/{}=w2000"

def retry(fn, tries=6, delay=3):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"  retry {i+1}: {str(e)[:90]}")
            time.sleep(delay)

def find_run(doc, needle):
    for el in doc.get("body", {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        for e in para.get("elements", []):
            tr = e.get("textRun")
            if tr and needle in tr.get("content", ""):
                s = e["startIndex"] + tr["content"].index(needle)
                return s, s + len(needle)
    return None, None

def aspect_height(path, width_pt):
    if Image is None:
        return width_pt  # square fallback
    with Image.open(path) as im:
        w, h = im.size
    return round(width_pt * h / w, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--account", default="work", choices=list(TOKENS))
    ap.add_argument("--spec", required=True, help="JSON map placeholder -> {path,width_pt}")
    args = ap.parse_args()

    spec = json.load(open(args.spec))
    creds = Credentials.from_authorized_user_file(TOKENS[args.account])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    for ph, cfg in spec.items():
        path = cfg["path"]
        width_pt = float(cfg.get("width_pt", 430))
        if not os.path.exists(path):
            print(f"{ph}: MISSING file {path}; skip"); continue

        # locate placeholder first (skip if already embedded)
        doc = retry(lambda: docs.documents().get(documentId=args.id).execute())
        s, e = find_run(doc, ph)
        if s is None:
            print(f"{ph}: placeholder not found (already embedded?); skip"); continue

        # upload image to Drive + make readable
        meta = {"name": f"_tmp_embed_{os.path.basename(path)}"}
        media = MediaFileUpload(path, mimetype="image/png", resumable=False)
        f = retry(lambda: drive.files().create(body=meta, media_body=media,
                                               fields="id").execute())
        fid = f["id"]
        retry(lambda: drive.permissions().create(
            fileId=fid, body={"role": "reader", "type": "anyone"}).execute())
        h_pt = aspect_height(path, width_pt)

        # replace placeholder with inline image
        retry(lambda: docs.documents().batchUpdate(documentId=args.id, body={"requests": [
            {"deleteContentRange": {"range": {"startIndex": s, "endIndex": e}}},
            {"insertInlineImage": {"location": {"index": s}, "uri": URI.format(fid),
             "objectSize": {"width": {"magnitude": width_pt, "unit": "PT"},
                            "height": {"magnitude": h_pt, "unit": "PT"}}}},
        ]}).execute())
        print(f"EMBEDDED {ph} <- {path} ({width_pt}x{h_pt}pt) drive={fid}")

        # trash the temp upload (doc has its own copy now)
        time.sleep(1)
        try:
            retry(lambda: drive.files().update(fileId=fid, body={"trashed": True}).execute())
        except Exception as ex:
            print(f"  (could not trash temp {fid}: {str(ex)[:60]})")

    print("Done:", f"https://docs.google.com/document/d/{args.id}/edit")

if __name__ == "__main__":
    main()
