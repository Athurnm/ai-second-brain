---
name: GA4 Connector
description: Read-only Google Analytics 4 connector for Work properties (exampleprogram-estore, etc). Pull reports, realtime, top pages/sources/events, and a composed KPI snapshot with period-over-period deltas for insight generation.
---

# GA4 Connector (Work)

Read-only. Uses the owner's Work account (`you@yourcompany.com`) via the shared Work
OAuth client. Token: `token_ga4_work.json` in this directory (auto-refreshes).
Design adapted from `googleanalytics/google-analytics-mcp` (official, tool surface) and
`Bin-Huang/google-analytics-cli` (CLI-first JSON output).

**Default property**: `<YOUR_GA4_PROPERTY_ID>` = exampleprogram-estore (set in `config.json`). Override with
`--property <id>` or `GA4_PROPERTY_ID`.

## Commands

```bash
BASE="timeout 180s python3 .agent/skills/ga4-connector/scripts/ga4_client.py"

$BASE accounts                          # list all GA accounts + properties the owner can see
$BASE property [--property ID]          # property details (timezone, currency)
$BASE meta [--grep purchase]            # discover dimensions/metrics incl. custom ones
$BASE snapshot [--days 28]              # THE default: KPIs + deltas vs prev period + top tables + daily trend
$BASE top --by pages|sources|events|countries|landing|devices [--start 28daysAgo --end yesterday]
$BASE report --dimensions date,sessionSource --metrics activeUsers,sessions \
      --start 28daysAgo --end yesterday [--filter sessionSource==tiktok.com] [--order-by sessions] [--limit 20]
$BASE realtime [--dimensions unifiedScreenName]   # last 30 min
$BASE set-default --property <YOUR_GA4_PROPERTY_ID>
```

- Dates accept `NdaysAgo`, `yesterday`, `today`, or `YYYY-MM-DD`.
- `--filter`: `dim==value` exact, `dim=~value` contains (single condition).
- Unsure which dimension/metric name to use? Run `meta --grep <keyword>` first; invalid names
  return a 400 with the bad field named.

## Analysis SOP (insights / reports / action items)

1. Start from `snapshot` — never eyeball raw rows first. It gives KPIs with % delta vs the
   previous equal-length period, top sources/pages/events/countries/devices, daily trend,
   new-vs-returning.
2. Drill into anomalies with `report` + `--filter` (e.g. traffic drop → segment by
   `sessionSource`, `deviceCategory`, `country`; page issue → filter `pagePath`).
3. Weight findings by business impact (revenue/conversion events > raw traffic). For
   exampleprogram-estore check `meta --grep purchase` for ecommerce metrics
   (`totalRevenue`, `purchaseRevenue`, `transactions`, `ecommercePurchases`).
4. Insights must state: what changed, by how much, vs what baseline, likely driver, and a
   concrete owner-able action item. Recency ≠ importance.
5. This connector is Work data — NEVER mix with You connectors/repos.

## Release impact analysis (`sorting_impact.py`)

Pre/post read for a shipped change, with a difference-in-differences control so seasonality and
the sitewide traffic trend don't get mistaken for impact.

```bash
python3 .agent/skills/ga4-connector/scripts/sorting_impact.py --release 2026-07-16 --window 14
```

- Metric is list CTR = `itemsClickedInList / itemsViewedInList`, per surface group (the prefix of
  `itemListName` before the colon): `Product List`, `Category Grid`, `Featured Products`,
  `Suggested Products`, `Search Results`.
- `--treated` / `--control` pick which surfaces are which. Control surfaces must be ones the
  release did NOT touch.
- Windows are day-of-week matched and exclude today (partial day). Use multiples of 7.
- **ExampleProgram history starts 16 Jun 2026** — no funnel data before that, so `--window` above 21
  has no baseline to sit on.
**Calibrate with placebo runs before trusting any result.** Point `--release` at a date where
nothing shipped and read the DiD. Measured noise floor on ExampleProgram:

| Window | Treated-only before/after | With DiD control |
| :--- | :--- | :--- |
| 7 days | ±6% (two placebos hit p<0.05 falsely) | ±15% |
| 14 days | ±1% | ±8% |

So the treated ratio is the *tighter* read and the control adds noise, because Search Results only
carries ~3-5k impressions/day. Treat before/after as primary and DiD as a directional robustness
check, not the headline.

**Traffic-mix break, 8 Jul 2026.** TikTok referral was 51% of sessions and went to zero overnight
on 8 Jul. Any pre-window spanning that date mixes two different user populations. For a release on
16 Jul the only clean baseline is 8..15 Jul, so `--window 8`.

## Auth (one-time, or when token dies)

```bash
python3 .agent/skills/ga4-connector/scripts/ga4_auth_helper.py auth-url
# the owner opens URL in browser logged in as you@yourcompany.com, approves,
# copies ?code=... from the localhost redirect URL, then:
python3 .agent/skills/ga4-connector/scripts/ga4_auth_helper.py auth-save --code '4/0A...'
```

Prereq (one-time, GCP project that owns the Work OAuth client): enable
**Google Analytics Data API** and **Google Analytics Admin API** in Cloud Console → APIs & Services.
403 `SERVICE_DISABLED` errors mean this step was skipped; the error body contains the direct
activation URL.
