---
name: Make PDF
description: Convert a markdown document into a publication-quality PDF (clean typography, page numbers, styled tables). For You lead magnets, one-pagers, guides, and any polished export. Triggers: "make this a PDF", "export to PDF", "/make-pdf". Adapted from gstack /make-pdf.
---

# Make PDF

Markdown to a polished, branded PDF via WeasyPrint (no pandoc/LaTeX). The default style is an A4 document with serif body, sans headings, accent-colored rules, styled tables/code/quotes, and page numbers, suitable for You lead magnets and guides.

## When to use
A markdown doc needs to ship as a downloadable PDF: a lead magnet (e.g. the AI Office Toolkit), a one-pager, a guide, a proposal. NOT for Google Docs (use `gdocs-create` for editable Docs).

## Usage

```bash
python3 .agent/skills/make-pdf/make_pdf.py \
  --file path/to/doc.md \
  --out  path/to/doc.pdf \
  --title "AI Office Toolkit" \
  --accent "#1F6FEB" \
  --footer "You"
```

- `--title` renders a large cover title above the body (optional).
- `--accent` sets the brand color for H1/links/table headers (hex). Default `#1F6FEB`.
- `--footer` puts text at the bottom-right of every page (e.g. "You" or a URL).
- `--css path.css` fully overrides the built-in stylesheet for a custom branded template.

Exit 0 + a printed byte count = success. The script prints the output path.

## Notes
- Body content (markdown features supported): headings, tables, fenced code, blockquotes, lists/task-lists, links, images, `attr_list`. Images resolve relative to where you run the command.
- You brand colors: pass `--accent` to match the post/visual palette for the campaign.
- This is the standard path for any You downloadable. The existing `AI-Office-Toolkit-by-You.pdf` is the reference output; regenerate via this skill so future lead magnets share one consistent look.
- Language follows the document: You lead magnets are Indonesian; a Work one-pager would be English.
