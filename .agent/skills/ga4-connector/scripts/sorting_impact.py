#!/usr/bin/env python3
"""Pre/post impact analysis for the ExampleProgram product-sorting release.

Metric: list CTR = itemsClickedInList / itemsViewedInList, per surface group.
Design: equal-length pre/post windows in whole weeks (day-of-week matched), plus a
difference-in-differences against unaffected surfaces to net out seasonality and the
site-wide traffic decline.

  python3 sorting_impact.py --release 2026-07-16 --window 14
  python3 sorting_impact.py --release 2026-07-16 --window 14 --treated "Product List" \
      --control "Suggested Products,Featured Products"
"""
import argparse, json, subprocess, statistics as stats
from datetime import date, timedelta
from pathlib import Path

CLIENT = Path(__file__).with_name("ga4_client.py")

def fetch(start, end):
    out = subprocess.run(
        ["python3", str(CLIENT), "report",
         "--dimensions", "date,itemListName",
         "--metrics", "itemsViewedInList,itemsClickedInList",
         "--start", start, "--end", end, "--limit", "100000"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out).get("rows", [])

def group(name):
    return name.split(":")[0].strip() if ":" in name else name.strip()

def daily_ctr(rows, surfaces):
    """-> {date: (impressions, clicks)} summed over the named surface groups."""
    acc = {}
    for r in rows:
        if group(r["itemListName"]) not in surfaces:
            continue
        d = r["date"]
        i, c = acc.get(d, (0, 0))
        acc[d] = (i + int(r["itemsViewedInList"]), c + int(r["itemsClickedInList"]))
    return acc

def welch(a, b):
    """Welch t-test on two daily-CTR samples. Returns (diff, t, approx two-sided p)."""
    ma, mb = stats.mean(a), stats.mean(b)
    va, vb = stats.variance(a), stats.variance(b)
    se = (va / len(a) + vb / len(b)) ** 0.5
    t = (mb - ma) / se if se else 0.0
    # normal approximation to the two-sided p-value; n>=7/arm makes this close enough
    p = 2 * (1 - 0.5 * (1 + _erf(abs(t) / 2 ** 0.5)))
    return mb - ma, t, p

def _erf(x):
    # Abramowitz & Stegun 7.1.26
    s = 1 if x >= 0 else -1
    x = abs(x)
    t = 1 / (1 + 0.3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
              - 0.284496736) * t + 0.254829592) * t * (2.718281828459045 ** (-x * x))
    return s * y

def window_series(acc, days):
    """-> list of daily CTR% in date order, plus (impressions, clicks) totals."""
    ser, ti, tc = [], 0, 0
    for d in sorted(days):
        i, c = acc.get(d, (0, 0))
        if i:
            ser.append(100 * c / i)
            ti += i
            tc += c
    return ser, ti, tc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", required=True, help="release date YYYY-MM-DD (first FULL day live)")
    ap.add_argument("--window", type=int, default=14, help="days per arm; use multiples of 7")
    # Phase 1 (CR CTS#006 §3, PRD_Ecom_Storefront_Product_Ordering §6) ranks listing pages,
    # the home category grid and homepage featured. Search Results is deferred to Phase 2 and
    # recommendation widgets ("Suggested Products") run on separate endpoints -- those two are
    # the only defensible controls.
    ap.add_argument("--treated", default="Product List,Category Grid,Featured Products")
    ap.add_argument("--control", default="Suggested Products,Search Results")
    a = ap.parse_args()

    rel = date.fromisoformat(a.release)
    treated = [s.strip() for s in a.treated.split(",")]
    control = [s.strip() for s in a.control.split(",")]

    # Post excludes today (partial day). Pre is the equal-length block ending the day before release.
    today = date.today()
    post_days = [rel + timedelta(days=i) for i in range(a.window)]
    post_days = [d for d in post_days if d < today]
    pre_days = [rel - timedelta(days=i) for i in range(1, a.window + 1)][::-1]

    if not post_days:
        print(f"No complete post-release days yet (release {rel}, today {today}). "
              f"Nothing to measure. Re-run after {rel + timedelta(days=1)}.")
        return

    if len(post_days) < a.window:
        print(f"NOTE: only {len(post_days)}/{a.window} post-days are complete. "
              f"Pre-window trimmed to match for a fair day-of-week comparison.\n")
        pre_days = pre_days[-len(post_days):]

    rows = fetch(min(pre_days).isoformat(), max(post_days).isoformat())
    pre_k = {d.strftime("%Y%m%d") for d in pre_days}
    post_k = {d.strftime("%Y%m%d") for d in post_days}

    print(f"Release {rel} | pre {min(pre_days)}..{max(pre_days)} | "
          f"post {min(post_days)}..{max(post_days)} | {len(post_days)}d per arm\n")

    results = {}
    for label, surfaces in (("TREATED", treated), ("CONTROL", control)):
        acc = daily_ctr(rows, surfaces)
        pre, pi, pc = window_series(acc, pre_k)
        post, qi, qc = window_series(acc, post_k)
        if len(pre) < 2 or len(post) < 2:
            print(f"{label}: not enough days with data.")
            return
        diff, t, p = welch(pre, post)
        rel = 100 * diff / stats.mean(pre)
        # Treated and control sit at very different CTR levels (~25% vs ~0.5%), so a
        # percentage-point gap between them is not comparable. DiD is done on relative change.
        results[label] = rel
        print(f"{label}: {', '.join(surfaces)}")
        print(f"  pre  CTR {stats.mean(pre):6.3f}%  ({pc:,} clicks / {pi:,} impressions)")
        print(f"  post CTR {stats.mean(post):6.3f}%  ({qc:,} clicks / {qi:,} impressions)")
        print(f"  delta {diff:+.3f}pp ({rel:+.1f}% relative)  "
              f"t={t:.2f}  p={p:.4f}{'  SIGNIFICANT' if p < 0.05 else ''}\n")

    did = results["TREATED"] - results["CONTROL"]
    print(f"DIFF-IN-DIFF (treated relative change minus control relative change): {did:+.1f}%")
    print("  Seasonality-adjusted read. Control surfaces (Search Results, Suggested Products)")
    print("  are out of Phase 1 scope, so they absorb sitewide traffic-mix and seasonal swings;")
    print("  what survives is attributable to sorting.")

if __name__ == "__main__":
    main()
