#!/usr/bin/env python3
"""
make_pdf.py - markdown -> publication-quality PDF (WeasyPrint).

For You lead magnets, one-pagers, and any polished document export.
Adapted from gstack /make-pdf. Uses python-markdown + WeasyPrint (both already
installed); no pandoc/LaTeX needed.

Usage:
  python3 make_pdf.py --file doc.md --out doc.pdf [--title "Title"] \
      [--accent "#1F6FEB"] [--css custom.css] [--footer "You"]

Notes:
- Default style is a clean A4 document: readable serif body, sans headings,
  accent-colored H1/H2 rules, page numbers, generous margins.
- Tables, code blocks, blockquotes, and task lists are styled.
- Pass --css to fully override the stylesheet for a branded template.
"""
import argparse
import sys

try:
    import markdown
except ImportError:
    print("ERROR: python-markdown not installed (pip install markdown)", file=sys.stderr)
    sys.exit(2)
try:
    from weasyprint import HTML, CSS
except ImportError:
    print("ERROR: weasyprint not installed (pip install weasyprint)", file=sys.stderr)
    sys.exit(2)

DEFAULT_CSS = """
@page {{
    size: A4;
    margin: 22mm 20mm 20mm 20mm;
    @bottom-center {{ content: counter(page) " / " counter(pages);
                      font-family: 'DejaVu Sans', sans-serif; font-size: 8pt; color: #888; }}
    @bottom-right {{ content: "{footer}"; font-family: 'DejaVu Sans', sans-serif;
                     font-size: 8pt; color: #888; }}
}}
body {{ font-family: 'DejaVu Serif', Georgia, serif; font-size: 10.8pt;
        line-height: 1.5; color: #1a1a1a; }}
h1, h2, h3, h4 {{ font-family: 'DejaVu Sans', Arial, sans-serif; line-height: 1.25;
                  color: #111; margin-top: 1.1em; }}
h1 {{ font-size: 22pt; color: {accent}; border-bottom: 3px solid {accent};
      padding-bottom: 6px; }}
h2 {{ font-size: 15pt; border-bottom: 1px solid #ddd; padding-bottom: 3px; }}
h3 {{ font-size: 12.5pt; }}
a {{ color: {accent}; text-decoration: none; }}
code {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt;
        background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }}
pre {{ background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 6px;
       padding: 10px; font-size: 9pt; overflow-x: auto; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ border-left: 3px solid {accent}; margin-left: 0; padding-left: 14px;
              color: #555; font-style: italic; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9.6pt; margin: 10px 0; }}
th, td {{ border: 1px solid #ddd; padding: 6px 9px; text-align: left; }}
th {{ background: {accent}; color: #fff; }}
tr:nth-child(even) td {{ background: #fafafa; }}
img {{ max-width: 100%; }}
ul, ol {{ padding-left: 22px; }}
hr {{ border: none; border-top: 1px solid #ddd; margin: 1.4em 0; }}
.doc-title {{ font-family: 'DejaVu Sans', sans-serif; font-size: 26pt; font-weight: 700;
              color: {accent}; margin-bottom: 4px; }}
"""

def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown -> polished PDF via WeasyPrint")
    ap.add_argument("--file", required=True, help="input markdown file")
    ap.add_argument("--out", required=True, help="output PDF path")
    ap.add_argument("--title", default=None, help="optional cover title rendered above the body")
    ap.add_argument("--accent", default="#1F6FEB", help="accent color (hex), default #1F6FEB")
    ap.add_argument("--footer", default="", help="footer text (bottom-right of each page)")
    ap.add_argument("--css", default=None, help="path to a CSS file that fully overrides the default style")
    args = ap.parse_args()

    md_text = open(args.file, encoding="utf-8").read()
    body_html = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "toc", "attr_list", "nl2br"],
    )
    title_html = f'<div class="doc-title">{args.title}</div>\n' if args.title else ""
    html_doc = f"<html><head><meta charset='utf-8'></head><body>{title_html}{body_html}</body></html>"

    if args.css:
        css = CSS(filename=args.css)
    else:
        css = CSS(string=DEFAULT_CSS.format(accent=args.accent, footer=args.footer))

    HTML(string=html_doc).write_pdf(args.out, stylesheets=[css])
    import os
    size = os.path.getsize(args.out)
    print(f"OK - PDF written: {args.out} ({size} bytes)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
