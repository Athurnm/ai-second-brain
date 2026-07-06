import argparse
import json
import os
import requests
import signal
import sys

# Global timeout: 180 seconds
def timeout_handler(signum, frame):
    print("[ERROR] Figma Connector timed out after 180 seconds", file=sys.stderr)
    sys.exit(1)

if os.name != 'nt': # signal.alarm is Unix-only
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)

DEFAULT_TIMEOUT = 60

BASE_URL = "https://api.figma.com/v1"

def get_headers(token):
    return {
        "X-Figma-Token": token
    }

def get_file(file_key, token):
    url = f"{BASE_URL}/files/{file_key}"
    response = requests.get(url, headers=get_headers(token), timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()

def get_file_nodes(file_key, node_ids, token):
    url = f"{BASE_URL}/files/{file_key}/nodes"
    params = {"ids": node_ids}
    response = requests.get(url, headers=get_headers(token), params=params)
    response.raise_for_status()
    return response.json()

def get_comments(file_key, token):
    url = f"{BASE_URL}/files/{file_key}/comments"
    response = requests.get(url, headers=get_headers(token), timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()

def get_images(file_key, node_ids, token, format='png', scale=1):
    url = f"{BASE_URL}/images/{file_key}"
    params = {"ids": node_ids, "format": format, "scale": scale}
    response = requests.get(url, headers=get_headers(token), params=params)
    response.raise_for_status()
    return response.json()

def extract_text_from_node(node, text_list):
    if 'document' in node:
        node = node['document']
    
    if node['type'] == 'TEXT':
        # specific logic to capture style if needed, for now just content
        content = node.get('characters', '')
        if content:
            text_list.append({"id": node['id'], "name": node['name'], "text": content, "style": node.get('style', {})})
    
    if 'children' in node:
        for child in node['children']:
            extract_text_from_node(child, text_list)

def analyze_nodes_for_prd(file_key, node_ids, token):
    # Get the nodes details
    data = get_file_nodes(file_key, node_ids, token)
    nodes = data.get('nodes', {})
    
    results = {}
    for node_id, node_data in nodes.items():
        if not node_data:
            continue
            
        document = node_data.get('document', {})
        text_content = []
        extract_text_from_node(document, text_content)
        
        # Simple heuristic to organize text layout (y-coordinate sort usually helps read top-down)
        # However, for now, just returning the raw list
        results[node_id] = {
            "name": document.get('name'),
            "type": document.get('type'),
            "extracted_text": text_content
        }
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Figma Connector Client")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
    parser.add_argument("--token", help="Figma Personal Access Token (defaults to token.json if available)")
    
    # ... (rest of parser setup)
    # Get File
    get_file_parser = subparsers.add_parser("get-file", help="Get entire file data")
    get_file_parser.add_argument("--file-key", required=True, help="Figma File Key")

    # Get Comments
    get_comments_parser = subparsers.add_parser("get-comments", help="Get file comments")
    get_comments_parser.add_argument("--file-key", required=True, help="Figma File Key")

    # Get Nodes
    get_nodes_parser = subparsers.add_parser("get-nodes", help="Get specific nodes")
    get_nodes_parser.add_argument("--file-key", required=True, help="Figma File Key")
    get_nodes_parser.add_argument("--node-ids", required=True, help="Comma separated node IDs")

    # Get Images
    get_images_parser = subparsers.add_parser("export-image", help="Export nodes as images")
    get_images_parser.add_argument("--file-key", required=True, help="Figma File Key")
    get_images_parser.add_argument("--node-ids", required=True, help="Comma separated node IDs")

    # Analyze for PRD
    analyze_parser = subparsers.add_parser("analyze-prd", help="Analyze nodes to extract PRD content")
    analyze_parser.add_argument("--file-key", required=True, help="Figma File Key")
    analyze_parser.add_argument("--node-ids", required=True, help="Comma separated node IDs")

    args = parser.parse_args()

    # Token Resolution Logic
    token = args.token
    if not token:
        # Try environment variable
        token = os.environ.get("FIGMA_ACCESS_TOKEN")
    
    if not token:
        # Try token.json in the same directory as the skill or the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        skill_dir = os.path.dirname(script_dir) # .agent/skills/figma-connector
        token_path = os.path.join(skill_dir, "token.json")
        
        if os.path.exists(token_path):
            try:
                with open(token_path, 'r') as f:
                    token_data = json.load(f)
                    token = token_data.get("access_token")
            except Exception as e:
                print(f"[WARNING] Could not read token.json: {e}", file=sys.stderr)

    if not token:
        print("[ERROR] No Figma Access Token provided. Use --token, set FIGMA_ACCESS_TOKEN, or provide token.json.", file=sys.stderr)
        sys.exit(1)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "get-file":
            print(json.dumps(get_file(args.file_key, token), indent=2))
        elif args.command == "get-comments":
            print(json.dumps(get_comments(args.file_key, token), indent=2))
        elif args.command == "get-nodes":
            print(json.dumps(get_file_nodes(args.file_key, args.node_ids, token), indent=2))
        elif args.command == "export-image":
            print(json.dumps(get_images(args.file_key, args.node_ids, token), indent=2))
        elif args.command == "analyze-prd":
            print(json.dumps(analyze_nodes_for_prd(args.file_key, args.node_ids, token), indent=2))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
