#!/usr/bin/env python3
"""
render_check.py - validate a Mermaid diagram renders, and save a preview PNG.

Uses the same kroki.io renderer as scripts/embed_mermaid_in_gdoc.py, so a pass
here guarantees the diagram will render when embedded into a Google Doc.

Usage:
  python3 render_check.py --file diagram.mmd [--out /tmp/diagram_preview.png]
  python3 render_check.py --text "flowchart TB; A-->B" [--out ...]

Exit 0 = valid (PNG saved). Non-zero = the renderer rejected the syntax
(stderr carries kroki's error so you can fix the Mermaid and re-run).
"""
import argparse
import base64
import sys
import zlib

try:
    import requests
except ImportError:
    print("ERROR: requests not installed (pip install requests)", file=sys.stderr)
    sys.exit(2)

def kroki_png_url(src: str) -> str:
    # identical encoding to scripts/embed_mermaid_in_gdoc.py:kroki_png_url
    data = base64.urlsafe_b64encode(zlib.compress(src.encode("utf-8"), 9)).decode()
    return "https://kroki.io/mermaid/png/" + data

def main() -> int:
    ap = argparse.ArgumentParser(description="Validate + preview a Mermaid diagram via kroki.io")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="path to a .mmd / Mermaid source file")
    g.add_argument("--text", help="inline Mermaid source")
    ap.add_argument("--out", default="/tmp/diagram_preview.png", help="where to save the preview PNG")
    args = ap.parse_args()

    src = open(args.file, encoding="utf-8").read() if args.file else args.text
    src = src.strip()
    if not src:
        print("ERROR: empty Mermaid source", file=sys.stderr)
        return 2

    url = kroki_png_url(src)
    try:
        r = requests.get(url, timeout=60)
    except Exception as e:
        print(f"ERROR: could not reach kroki.io: {e}", file=sys.stderr)
        return 3

    if r.status_code != 200:
        # kroki returns the syntax error in the body
        print(f"INVALID Mermaid (HTTP {r.status_code}):", file=sys.stderr)
        print(r.text[:1500], file=sys.stderr)
        return 1

    with open(args.out, "wb") as f:
        f.write(r.content)
    print(f"OK - renders cleanly. Preview saved: {args.out} ({len(r.content)} bytes)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
