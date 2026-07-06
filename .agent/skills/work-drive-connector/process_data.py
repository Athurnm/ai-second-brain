
import csv
import sys

def parse_float(s):
    try:
        return float(s.replace(',', '').replace(' ', ''))
    except:
        return 0.0

def process_data(csv_path):
    # Rows to aggregate
    tenant_rows = [
        'tenantCount_small', 'tenantCount_med', 'tenantCount_large', 
        'tenantCount_enterprise', 'oldworld_CustomerCount_enterprise'
    ]
    revenue_rows = [
        'totalRevenue_small', 'totalRevenue_med', 'totalRevenue_large', 
        'totalRevenue_enterprise', 'totalRevenue_oldworld_Customer'
    ]
    # Margin rows identified from scan
    margin_rows = [
        'GrossMarginAbsValue_SubscriptionsRevenue_small', 'GrossMarginAbsValue_SubscriptionsRevenue_med',
        'GrossMarginAbsValue_SubscriptionsRevenue_large', 'GrossMarginAbsValue_SubscriptionsRevenue_enterprise',
        'GrossMarginAbsValue_Tenant_NonSubscriptionsRevenue_small', 'GrossMarginAbsValue_Tenant_NonSubscriptionsRevenue_med',
        'GrossMarginAbsValue_Tenant_NonSubscriptionsRevenue_large', 'GrossMarginAbsValue_Tenant_NonSubscriptionsRevenue_enterprise',
        'GrossMarginAbsValue_SupplySide_NonSubscriptionsRevenue_small', 'GrossMarginAbsValue_SupplySide_NonSubscriptionsRevenue_med',
        'GrossMarginAbsValue_SupplySide_NonSubscriptionsRevenue_large', 'GrossMarginAbsValue_SupplySide_NonSubscriptionsRevenue_enterprise',
        'GrossMarginAbsValue_AncillaryRevenue_small', 'GrossMarginAbsValue_AncillaryRevenue_med',
        'GrossMarginAbsValue_AncillaryRevenue_large', 'GrossMarginAbsValue_AncillaryRevenue_enterprise',
        # And arguably oldworld margin if available? 
        # Scan didn't explicitly show 'totalMargin_oldworld', but maybe 'AverageMarginPerTenant' * Count
        # or implies specific rows.
        # I'll rely on what I found.
    ]

    # Initialize data structures
    # We expect 24 months (Jan 26 - Dec 27)
    # The scan output suggests values start around column index 4 (E).
    # "400.0" was at the start of values.
    # In row 3 (header?): ... Jan-26 ...
    
    monthly_data = {
        'tenants': [0.0] * 24,
        'revenue': [0.0] * 24,
        'margin': [0.0] * 24
    }
    
    start_col = -1 # To be determined

    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Determine start column by looking for the first numeric value in a known row
    # Let's look at `tenantCount_small` row.
    for row in rows:
        if len(row) > 3 and 'tenantCount_small' in str(row[2]):
            # Find the first float value
            for i, cell in enumerate(row):
                if i > 3: # Skip metadata
                    try:
                        float(cell)
                        start_col = i
                        break
                    except:
                        continue
            break
    
    if start_col == -1:
        # Fallback based on scan: index 4 looks like values
        start_col = 4 

    # Process rows
    for row in rows:
        if len(row) < 3: continue
        
        row_label = str(row[2]).strip()
        
        # Helper to get values
        def get_series(r):
            vals = []
            for i in range(start_col, min(len(r), start_col + 24)):
                vals.append(parse_float(r[i]))
            # Pad if short
            while len(vals) < 24:
                vals.append(0.0)
            return vals

        if any(tr in row_label for tr in tenant_rows):
            series = get_series(row)
            for i in range(24):
                monthly_data['tenants'][i] += series[i]
        
        if any(rr in row_label for rr in revenue_rows):
            series = get_series(row)
            for i in range(24):
                monthly_data['revenue'][i] += series[i]
                
        # Margin aggregation - simplistic
        # Based on keywords containing "GrossMarginAbsValue"
        if "GrossMarginAbsValue" in row_label:
             series = get_series(row)
             for i in range(24):
                monthly_data['margin'][i] += series[i]

    # Generate Report
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    print("# Ecommerce Solutions Financial Model")
    print("Based on Sales Budget 2026_v3.11\n")
    
    # 2026 Table
    print("## 2026 Monthly Model")
    print("| Mon | New Tenants | Total Tenants (MTU) | Revenue (GMV) | Margin | Net |")
    print("|---|---|---|---|---|---|")
    
    total_new_2026 = 0
    total_rev_2026 = 0
    total_margin_2026 = 0
    
    prev_tenants = 0 # Assume 0 starting or use first month's initial
    
    for i in range(12):
        month = months[i]
        tenants = monthly_data['tenants'][i]
        revenue = monthly_data['revenue'][i]
        margin = monthly_data['margin'][i]
        
        new_tenants = tenants - prev_tenants
        if i == 0: new_tenants = tenants # Assume all new in Jan? Or delta from prev year 0.
        
        # Format
        print(f"| {month} | {int(new_tenants)} | {int(tenants)} | ${int(revenue):,} | ${int(margin):,} | ${int(margin):,} |")
        
        total_new_2026 += new_tenants
        total_rev_2026 += revenue
        total_margin_2026 += margin
        
        prev_tenants = tenants

    print(f"\n**2026 Totals:** New: {int(total_new_2026)}, Revenue: ${int(total_rev_2026):,}, Margin: ${int(total_margin_2026):,}")

    # 2027 Table
    print("\n## 2027 Monthly Model")
    print("| Mon | New Tenants | Total Tenants (MTU) | Revenue (GMV) | Margin | Net |")
    print("|---|---|---|---|---|---|")
    
    total_new_2027 = 0
    total_rev_2027 = 0
    total_margin_2027 = 0
    
    for i in range(12, 24):
        month = months[i-12]
        tenants = monthly_data['tenants'][i]
        revenue = monthly_data['revenue'][i]
        margin = monthly_data['margin'][i]
        
        new_tenants = tenants - prev_tenants
        
        print(f"| {month} | {int(new_tenants)} | {int(tenants)} | ${int(revenue):,} | ${int(margin):,} | ${int(margin):,} |")
        
        total_new_2027 += new_tenants
        total_rev_2027 += revenue
        total_margin_2027 += margin
        prev_tenants = tenants

    print(f"\n**2027 Totals:** New: {int(total_new_2027)}, Revenue: ${int(total_rev_2027):,}, Margin: ${int(total_margin_2027):,}")

    # Summary Table like B2C
    print("\n## Summary")
    print("| Year | New Tenants | End MTU | Revenue | Margin | Net |")
    print("|---|---|---|---|---|---|")
    print(f"| 2026 | {int(total_new_2026)} | {int(monthly_data['tenants'][11])} | ${int(total_rev_2026):,} | ${int(total_margin_2026):,} | ${int(total_margin_2026):,} |")
    print(f"| 2027 | {int(total_new_2027)} | {int(monthly_data['tenants'][23])} | ${int(total_rev_2027):,} | ${int(total_margin_2027):,} | ${int(total_margin_2027):,} |")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 process_data.py <csv_path>")
        sys.exit(1)
    
    process_data(sys.argv[1])
