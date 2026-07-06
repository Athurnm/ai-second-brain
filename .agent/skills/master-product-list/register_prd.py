import os, sys, argparse, re, json
from googleapiclient.discovery import build
import httplib2
import google_auth_httplib2

# Configure constants
MASTER_LIST_MD = './Clients/Work/Marketplace/Master_Product_List_Restructured.md'
SHEET_ID = '<YOUR_DRIVE_ID>'

# Add work-drive-connector to path for auth
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVE_CONNECTOR_DIR = os.path.join(SCRIPT_DIR, '..', 'work-drive-connector')
if DRIVE_CONNECTOR_DIR not in sys.path:
    sys.path.append(DRIVE_CONNECTOR_DIR)
from gdrive_manager import authenticate

def update_markdown(component, feature, details, version, status, prd_url, prd_title):
    print(f"Updating local MD file: {MASTER_LIST_MD}...")
    if not os.path.exists(MASTER_LIST_MD):
        print(f"Error: {MASTER_LIST_MD} not found.")
        return False
    with open(MASTER_LIST_MD, 'r') as f:
        content = f.read()

    comp_esc = re.escape(component)
    comp_pattern = rf"##+.*?{comp_esc}"
    comp_match = re.search(comp_pattern, content, re.IGNORECASE)
    if not comp_match:
        print(f"Error: Component '{component}' not found in Markdown.")
        return False

    comp_level = len(comp_match.group(0)) - len(comp_match.group(0).lstrip('#'))
    next_section_pattern = rf"\n#{{1,{comp_level}}} [^#]"
    next_section_match = re.search(next_section_pattern, content[comp_match.end():])
    search_limit = comp_match.end() + next_section_match.start() if next_section_match else len(content)
    comp_section = content[comp_match.start():search_limit]

    version_main = version.split('(')[0].strip()
    version_pattern = rf"##+.*?{re.escape(version_main)}"
    version_match = re.search(version_pattern, comp_section, re.IGNORECASE)
    if not version_match:
        print(f"Error: Version '{version_main}' not found in Markdown.")
        return False

    table_pattern = r"\| Feature \|.*?\|\n\|.*?\n((?:\|.*?\|\n?)+)"
    table_match = re.search(table_pattern, comp_section[version_match.end():], re.DOTALL)
    if not table_match:
        print("Error: Feature table not found in Markdown.")
        return False

    table_content = table_match.group(1)
    feature_esc = re.escape(feature)
    row_pattern = rf"\| \*\*{feature_esc}\*\* \|.*?\|.*?\|.*?\|"
    formatted_details = details.replace(';', '<br>')
    new_row = f"| **{feature}** | {formatted_details} | {status} | [{prd_title}]({prd_url}) |"
    
    if re.search(row_pattern, table_content, re.IGNORECASE):
        updated_table = re.sub(row_pattern, new_row, table_content, flags=re.IGNORECASE)
    else:
        updated_table = table_content.rstrip() + "\n" + new_row + "\n"

    new_comp_section = comp_section[:version_match.end()] + comp_section[version_match.end():].replace(table_content, updated_table)
    new_content = content[:comp_match.start()] + new_comp_section + content[search_limit:]

    with open(MASTER_LIST_MD, 'w') as f:
        f.write(new_content)
    print("Markdown update complete.")
    return True

def get_sheets_service():
    creds = authenticate()
    return build('sheets', 'v4', http=google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=60)))

def _get_sheet_id(service, tab_name):
    meta = service.spreadsheets().get(spreadsheetId=SHEET_ID, fields="sheets(properties(title,sheetId))").execute()
    for s in meta['sheets']:
        if s['properties']['title'] == tab_name: return s['properties']['sheetId']
    return None

def _update_sheet_tab(service, tab_name, component, feature, details, version, status, prd_url, prd_title):
    print(f"Updating Sheet Tab: \"{tab_name}\"...")
    sheet_id = _get_sheet_id(service, tab_name)
    metadata = service.spreadsheets().get(spreadsheetId=SHEET_ID, ranges=[f"'{tab_name}'!A1:B300"], fields="sheets(merges,data(rowData(values(effectiveValue))))").execute()
    sheet = metadata['sheets'][0]
    merges = sheet.get('merges', [])
    rows = sheet['data'][0].get('rowData', [])
    
    comp_row_idx = -1
    comp_merge = None
    for i, r in enumerate(rows):
        vals = r.get('values', [])
        if vals:
            val = vals[0].get('effectiveValue', {}).get('stringValue', '')
            if component.lower().replace(' ', '') in val.lower().replace(' ', ''):
                comp_row_idx = i
                for m in merges:
                    if m.get('startColumnIndex', 0) == 0 and m.get('startRowIndex', 0) <= i < m.get('endRowIndex', 0):
                        comp_merge = m
                        break
                break
    
    if comp_row_idx == -1:
        print(f"Warning: Component '{component}' not found in tab '{tab_name}'. Skipping.")
        return

    c_start = comp_merge['startRowIndex'] if comp_merge else comp_row_idx
    c_end = comp_merge['endRowIndex'] if comp_merge else comp_row_idx + 1
    
    details_items = [d.strip() for d in details.split(';')]
    num_rows = len(details_items)
    link_formula = f'=HYPERLINK("{prd_url}", "{prd_title}")'
    
    # Append a single row at the end of the tab.
    # Google Sheets "Table" objects reject insertRange ("cannot insert cells over part of a table"),
    # so we append instead of inserting mid-section. Grouping merges are intentionally skipped.
    row = [component, feature, details.replace(';', ' / '), version, status, link_formula]
    service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!A1",
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body={'values': [row]}
    ).execute()
    print(f"Sheet tab '{tab_name}' updated successfully (appended 1 row).")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--component', required=True)
    parser.add_argument('--feature', required=True)
    parser.add_argument('--details', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--status', default='Planned') # Default to Planned as per screenshot
    parser.add_argument('--url', required=True)
    parser.add_argument('--title', required=True)
    args = parser.parse_args()
    
    update_markdown(args.component, args.feature, args.details, args.version, args.status, args.url, args.title)
    service = get_sheets_service()
    _update_sheet_tab(service, "Master Product List & Breakdown (MECE)", args.component, args.feature, args.details, args.version, args.status, args.url, args.title)
    _update_sheet_tab(service, "Roadmap Breakdown", args.component, args.feature, args.details, args.version, args.status, args.url, args.title)

if __name__ == "__main__":
    main()
