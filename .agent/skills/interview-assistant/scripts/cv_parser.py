#!/usr/bin/env python3
"""
Interview Assistant CV Parser
Downloads CVs from Google Drive (PDF) and extracts text using pypdf.
Supports local file parsing too.
"""

import os
import sys
import argparse
import mimetypes
import pypdf

# Setup paths relative to script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
SCRATCH_DIR = os.path.join(REPO_ROOT, 'scratch')

def load_credentials(account):
    """Dynamically load credentials from drive connector skill."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    
    connector_dir = os.path.join(REPO_ROOT, '.agent', 'skills', f'{account}-drive-connector')
    # Fallback paths
    if account == 'work':
        token_path = os.path.join(REPO_ROOT, '.agent', 'skills', 'work-drive-connector', 'token.json')
    else:
        token_path = os.path.join(REPO_ROOT, '.agent', 'skills', 'google-drive-connector', 'token.json')
        
    if not os.path.exists(token_path):
        print(f"Error: Token file not found at {token_path}", file=sys.stderr)
        return None
        
    creds = Credentials.from_authorized_user_file(token_path, ['https://www.googleapis.com/auth/drive'])
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
    return creds

def download_from_drive(file_id, account, output_path):
    """Download a file from Google Drive."""
    from googleapiclient.discovery import build
    
    creds = load_credentials(account)
    if not creds:
        return False
        
    print(f"Connecting to Google Drive ({account})...", file=sys.stderr)
    service = build('drive', 'v3', credentials=creds)
    
    try:
        print(f"Downloading file ID: {file_id}...", file=sys.stderr)
        content = service.files().get_media(fileId=file_id).execute()
        with open(output_path, 'wb') as f:
            f.write(content)
        print(f"Downloaded and saved to {output_path}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Error downloading from Drive: {e}", file=sys.stderr)
        return False

def extract_pdf_text(pdf_path, text_output_path):
    """Extract text from a PDF file using pypdf."""
    try:
        print(f"Parsing PDF {pdf_path}...", file=sys.stderr)
        reader = pypdf.PdfReader(pdf_path)
        text_content = []
        for i, page in enumerate(reader.pages):
            text_content.append(f"--- PAGE {i+1} ---")
            text_content.append(page.extract_text() or "")
            
        full_text = '\n'.join(text_content)
        with open(text_output_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
        print(f"Successfully extracted text to {text_output_path}", file=sys.stderr)
        return full_text
    except Exception as e:
        print(f"Error extracting PDF text: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Interview Assistant CV Parser")
    parser.add_argument("--file", help="Path to local PDF/TXT file")
    parser.add_argument("--drive-id", help="Google Drive file ID")
    parser.add_argument("--account", default="work", choices=["work", "google"], help="Drive account (work or google/personal)")
    
    args = parser.parse_args()
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    
    drive_id = getattr(args, 'drive_id', None)
    
    if not args.file and not drive_id:
        print("Error: Either --file or --drive-id must be provided.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
        
    local_path = None
    
    if drive_id:
        local_path = os.path.join(SCRATCH_DIR, "downloaded_cv.pdf")
        success = download_from_drive(drive_id, args.account, local_path)
        if not success:
            sys.exit(1)
    else:
        local_path = args.file
        
    if not os.path.exists(local_path):
        print(f"Error: Local file not found at {local_path}", file=sys.stderr)
        sys.exit(1)
        
    # Check mime type or extension
    _, ext = os.path.splitext(local_path.lower())
    
    if ext == '.pdf':
        txt_path = os.path.join(SCRATCH_DIR, "cv_extracted_text.txt")
        text = extract_pdf_text(local_path, txt_path)
        if text:
            print(text)
        else:
            sys.exit(1)
    else:
        # Text/MD file - just print content
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                text = f.read()
            print(text)
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__':
    main()
