#!/usr/bin/env python3
"""
GA4 Connector (Work) - read-only Google Analytics 4 client.
Design stolen from googleanalytics/google-analytics-mcp (tool surface) and
Bin-Huang/google-analytics-cli (CLI-first, JSON to stdout).

Auth: token_ga4_work.json (scope analytics.readonly), minted via ga4_auth_helper.py
from the shared Work OAuth client. Auto-refreshes.

Actions: accounts | property | meta | report | realtime | top | snapshot | set-default
"""
import os
import sys
import json
import argparse
import signal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def timeout_handler(signum, frame):
    print("[ERROR] GA4 client timed out after 180 seconds", file=sys.stderr)
    sys.exit(1)

if os.name != 'nt':
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
TOKEN_FILE = os.path.join(SKILL_DIR, 'token_ga4_work.json')
CONFIG_FILE = os.path.join(SKILL_DIR, 'config.json')
SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']

def get_creds():
    if not os.path.exists(TOKEN_FILE):
        print(f"[ERROR] No token at {TOKEN_FILE}. Run: python3 {SCRIPT_DIR}/ga4_auth_helper.py auth-url", file=sys.stderr)
        sys.exit(1)
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as t:
            t.write(creds.to_json())
    return creds

def data_api():
    return build('analyticsdata', 'v1beta', credentials=get_creds(), cache_discovery=False)

def admin_api():
    return build('analyticsadmin', 'v1beta', credentials=get_creds(), cache_discovery=False)

def resolve_property(args):
    prop = getattr(args, 'property', None) or os.environ.get('GA4_PROPERTY_ID')
    if not prop and os.path.exists(CONFIG_FILE):
        prop = json.load(open(CONFIG_FILE)).get('default_property')
    if not prop:
        print("[ERROR] No property. Pass --property, set GA4_PROPERTY_ID, or run set-default.", file=sys.stderr)
        sys.exit(1)
    prop = str(prop)
    return prop if prop.startswith('properties/') else f'properties/{prop}'

def out(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))

# ---------- report plumbing ----------

def build_filter(expr):
    """'dim==value' exact, 'dim=~value' contains. Single condition only."""
    if '=~' in expr:
        field, value, match = expr.split('=~')[0], expr.split('=~')[1], 'CONTAINS'
    elif '==' in expr:
        field, value, match = expr.split('==')[0], expr.split('==')[1], 'EXACT'
    else:
        print("[ERROR] --filter must be dim==value or dim=~value", file=sys.stderr)
        sys.exit(1)
    return {'filter': {'fieldName': field, 'stringFilter': {'matchType': match, 'value': value, 'caseSensitive': False}}}

def rows_to_records(resp):
    dims = [h['name'] for h in resp.get('dimensionHeaders', [])]
    mets = [h['name'] for h in resp.get('metricHeaders', [])]
    records = []
    for row in resp.get('rows', []):
        rec = {}
        for i, d in enumerate(dims):
            rec[d] = row.get('dimensionValues', [])[i].get('value')
        for i, m in enumerate(mets):
            rec[m] = row.get('metricValues', [])[i].get('value')
        records.append(rec)
    return records

def run_report(prop, dimensions, metrics, start, end, limit=20, order_metric=None, dim_filter=None, extra_ranges=None):
    body = {
        'dateRanges': [{'startDate': start, 'endDate': end}] + (extra_ranges or []),
        'metrics': [{'name': m} for m in metrics],
        'limit': limit,
    }
    if dimensions:
        body['dimensions'] = [{'name': d} for d in dimensions]
    if order_metric:
        body['orderBys'] = [{'metric': {'metricName': order_metric}, 'desc': True}]
    if dim_filter:
        body['dimensionFilter'] = build_filter(dim_filter)
    return data_api().properties().runReport(property=prop, body=body).execute()

# ---------- actions ----------

def action_accounts(args):
    resp = admin_api().accountSummaries().list(pageSize=200).execute()
    summary = []
    for acc in resp.get('accountSummaries', []):
        summary.append({
            'account': acc.get('account'),
            'accountName': acc.get('displayName'),
            'properties': [
                {'property': p.get('property'), 'name': p.get('displayName')}
                for p in acc.get('propertySummaries', [])
            ],
        })
    out(summary)

def action_property(args):
    prop = resolve_property(args)
    out(admin_api().properties().get(name=prop).execute())

def action_meta(args):
    prop = resolve_property(args)
    resp = data_api().properties().getMetadata(name=f'{prop}/metadata').execute()
    grep = (args.grep or '').lower()
    def keep(item):
        return not grep or grep in item.get('apiName', '').lower() or grep in item.get('uiName', '').lower()
    out({
        'dimensions': [{'apiName': d['apiName'], 'uiName': d.get('uiName'), 'custom': d.get('customDefinition', False)}
                       for d in resp.get('dimensions', []) if keep(d)],
        'metrics': [{'apiName': m['apiName'], 'uiName': m.get('uiName'), 'custom': m.get('customDefinition', False)}
                    for m in resp.get('metrics', []) if keep(m)],
    })

def action_report(args):
    prop = resolve_property(args)
    dims = [d.strip() for d in args.dimensions.split(',')] if args.dimensions else []
    mets = [m.strip() for m in args.metrics.split(',')]
    resp = run_report(prop, dims, mets, args.start, args.end,
                      limit=args.limit, order_metric=args.order_by, dim_filter=args.filter)
    out({'rowCount': resp.get('rowCount', 0), 'rows': rows_to_records(resp)})

def action_realtime(args):
    prop = resolve_property(args)
    dims = [d.strip() for d in args.dimensions.split(',')] if args.dimensions else ['unifiedScreenName']
    mets = [m.strip() for m in args.metrics.split(',')] if args.metrics else ['activeUsers']
    body = {
        'dimensions': [{'name': d} for d in dims],
        'metrics': [{'name': m} for m in mets],
        'limit': args.limit,
    }
    resp = data_api().properties().runRealtimeReport(property=prop, body=body).execute()
    out({'rowCount': resp.get('rowCount', 0), 'rows': rows_to_records(resp)})

TOP_PRESETS = {
    'pages': (['pageTitle', 'pagePath'], ['screenPageViews', 'activeUsers', 'bounceRate']),
    'sources': (['sessionSource', 'sessionMedium'], ['sessions', 'activeUsers', 'engagedSessions']),
    'events': (['eventName'], ['eventCount', 'activeUsers']),
    'countries': (['country'], ['activeUsers', 'sessions']),
    'landing': (['landingPage'], ['sessions', 'activeUsers', 'bounceRate']),
    'devices': (['deviceCategory'], ['activeUsers', 'sessions']),
}

def action_top(args):
    prop = resolve_property(args)
    dims, mets = TOP_PRESETS[args.by]
    resp = run_report(prop, dims, mets, args.start, args.end, limit=args.limit, order_metric=mets[0])
    out({'by': args.by, 'dateRange': f'{args.start}..{args.end}', 'rows': rows_to_records(resp)})

def action_snapshot(args):
    """Composed KPI snapshot with previous-period comparison. The one-call input
    for briefings / weekly reports / insight generation."""
    prop = resolve_property(args)
    days = args.days
    cur = (f'{days}daysAgo', 'yesterday')
    prev = (f'{2 * days}daysAgo', f'{days + 1}daysAgo')

    kpi_metrics = ['activeUsers', 'newUsers', 'sessions', 'engagedSessions',
                   'engagementRate', 'averageSessionDuration', 'screenPageViews',
                   'eventCount', 'totalRevenue']

    def totals(start, end):
        resp = run_report(prop, [], kpi_metrics, start, end, limit=1)
        rows = rows_to_records(resp)
        return rows[0] if rows else {}

    result = {
        'property': prop,
        'period': f'last {days} days (vs previous {days})',
        'kpis': {'current': totals(*cur), 'previous': totals(*prev)},
    }

    deltas = {}
    for k, v in result['kpis']['current'].items():
        try:
            c, p = float(v), float(result['kpis']['previous'].get(k, 0))
            deltas[k] = round((c - p) / p * 100, 1) if p else None
        except (TypeError, ValueError):
            pass
    result['delta_pct_vs_previous'] = deltas

    for by in ['sources', 'pages', 'events', 'countries', 'devices']:
        dims, mets = TOP_PRESETS[by]
        resp = run_report(prop, dims, mets, *cur, limit=10, order_metric=mets[0])
        result[f'top_{by}'] = rows_to_records(resp)

    trend = run_report(prop, ['date'], ['activeUsers', 'sessions', 'totalRevenue'], *cur, limit=400)
    result['daily_trend'] = sorted(rows_to_records(trend), key=lambda r: r['date'])

    nvr = run_report(prop, ['newVsReturning'], ['activeUsers', 'sessions'], *cur, limit=5)
    result['new_vs_returning'] = rows_to_records(nvr)

    out(result)

def action_set_default(args):
    prop = str(args.property).replace('properties/', '')
    cfg = json.load(open(CONFIG_FILE)) if os.path.exists(CONFIG_FILE) else {}
    cfg['default_property'] = prop
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f"OK: default property set to {prop}")

def main():
    p = argparse.ArgumentParser(description='GA4 read-only connector (Work)')
    sub = p.add_subparsers(dest='action', required=True)

    sub.add_parser('accounts', help='list GA accounts + properties visible to the token')

    sp = sub.add_parser('property', help='property details')
    sp.add_argument('--property')

    sm = sub.add_parser('meta', help='list available dimensions/metrics (incl. custom)')
    sm.add_argument('--property')
    sm.add_argument('--grep', help='filter by substring')

    sr = sub.add_parser('report', help='custom report')
    sr.add_argument('--property')
    sr.add_argument('--dimensions', default='', help='comma-separated, e.g. date,sessionSource')
    sr.add_argument('--metrics', required=True, help='comma-separated, e.g. activeUsers,sessions')
    sr.add_argument('--start', default='28daysAgo')
    sr.add_argument('--end', default='yesterday')
    sr.add_argument('--limit', type=int, default=20)
    sr.add_argument('--order-by', help='metric to sort desc by')
    sr.add_argument('--filter', help='dimension filter: dim==value (exact) or dim=~value (contains)')

    srt = sub.add_parser('realtime', help='realtime report (last 30 min)')
    srt.add_argument('--property')
    srt.add_argument('--dimensions', default='')
    srt.add_argument('--metrics', default='')
    srt.add_argument('--limit', type=int, default=20)

    st = sub.add_parser('top', help='preset top-N tables')
    st.add_argument('--by', choices=sorted(TOP_PRESETS), required=True)
    st.add_argument('--property')
    st.add_argument('--start', default='28daysAgo')
    st.add_argument('--end', default='yesterday')
    st.add_argument('--limit', type=int, default=10)

    ss = sub.add_parser('snapshot', help='composed KPI snapshot + deltas vs previous period')
    ss.add_argument('--property')
    ss.add_argument('--days', type=int, default=28)

    sd = sub.add_parser('set-default', help='persist default property id')
    sd.add_argument('--property', required=True)

    args = p.parse_args()
    {
        'accounts': action_accounts,
        'property': action_property,
        'meta': action_meta,
        'report': action_report,
        'realtime': action_realtime,
        'top': action_top,
        'snapshot': action_snapshot,
        'set-default': action_set_default,
    }[args.action](args)

if __name__ == '__main__':
    main()
