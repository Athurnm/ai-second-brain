
import os
import sys
from googleapiclient.discovery import build

# Add the directory to sys.path to import gdrive_manager
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from gdrive_manager import authenticate

def list_sheets(file_id):
    creds = authenticate()
    service = build('sheets', 'v4', credentials=creds)
    
    spreadsheet = service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    
    print(f"Sheets found in {file_id}:")
    for sheet in sheets:
        print(f"- {sheet['properties']['title']} (ID: {sheet['properties']['sheetId']})")

def get_sheet_values(file_id, sheet_name):
    creds = authenticate()
    service = build('sheets', 'v4', credentials=creds)
    
    result = service.spreadsheets().values().get(
        spreadsheetId=file_id, range=sheet_name).execute()
    values = result.get('values', [])
    
    if not values:
        print(f"No data found in sheet '{sheet_name}'.")
    else:
        for row in values:
            print(",".join([str(cell) for cell in row]))

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 fetch_sheets.py <command> <file_id> [sheet_name]")
        print("Commands: list, get")
        sys.exit(1)
        
    command = sys.argv[1]
    file_id = sys.argv[2]
    
    if command == 'list':
        list_sheets(file_id)
    elif command == 'get':
        if len(sys.argv) < 4:
            print("Usage for get: python3 fetch_sheets.py get <file_id> <sheet_name>")
            sys.exit(1)
        sheet_name = sys.argv[3]
        get_sheet_values(file_id, sheet_name)
    else:
        print(f"Unknown command: {command}")
