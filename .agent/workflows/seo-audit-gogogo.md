---
description: Run the SEO Audit for GoGoGo (gogogo.id)
---

This workflow executes the global Playwright-based SEO audit skill, configured specifically for the GoGoGo framework and its URL structures.

// turbo
1. Run the new global SEO audit skill:
```bash
python .agent/skills/seo-audit/scripts/seo_audit.py \
    --base-url https://gogogo.id \
    --blog-url https://gogogo.id/blog \
    --sitemap-url https://gogogo.id/blog/sitemap_index.xml \
    --pagination-pattern "https://gogogo.id/postingan?kategori=Mobile+Legend&page=2"
```

2. Review the output files in the current directory:
- `gogogo.id_seo_audit_results_YYYY-MM-DD.json`
- `gogogo.id_seo_audit_report_YYYY-MM-DD.html`

3. If there are failures, notify the developer team on Slack.
