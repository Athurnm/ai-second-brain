import argparse
import json
import os
import signal
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# Default timeout for API requests
DEFAULT_TIMEOUT = 60 # increased from 30 to allow for larger payloads, but capped by global timeout
TOKEN_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "token.env")

# Global timeout: 180 seconds
def timeout_handler(signum, frame):
    print("[ERROR] Fathom Connector timed out after 180 seconds", file=sys.stderr)
    sys.exit(1)

if os.name != 'nt': # signal.alarm is Unix-only
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)

def load_fathom_token():
    """Load the Fathom API key from the token.env file."""
    if os.path.exists(TOKEN_ENV_PATH):
        with open(TOKEN_ENV_PATH, 'r') as f:
            for line in f:
                if line.startswith('FATHOM_API_KEY='):
                    return line.split('=', 1)[1].strip()
    return os.environ.get('FATHOM_API_KEY')

def make_fathom_request(endpoint, token, method='GET', params=None, data=None):
    """
    Makes a request to the Fathom API using urllib.
    """
    base_url = "https://api.fathom.ai/external/v1"
    url = f"{base_url}{endpoint}"
    
    if params:
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url += f"?{query_string}"
    
    headers = {
        "X-Api-Key": token,
        "Accept": "application/json"
    }
    
    encoded_data = None
    if data:
        encoded_data = json.dumps(data).encode('utf-8')
        headers["Content-Type"] = "application/json"

    print(f"[DEBUG] Calling Fathom API: {method} {endpoint}...", file=sys.stderr)
    req = urllib.request.Request(url, headers=headers, data=encoded_data, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        print(f"[ERROR] Fathom API Error: {e.code} - {body}", file=sys.stderr)
        return {"error": e.code, "message": body}
    except Exception as e:
        print(f"[ERROR] Connection Error: {str(e)}", file=sys.stderr)
        return {"error": "connection_error", "message": str(e)}

def list_meetings(token, limit=20, created_after=None, include_all=True):
    """List recent meetings with optional full data."""
    params = {"limit": limit}
    if created_after:
        params["created_after"] = created_after
    
    if include_all:
        params["include_transcript"] = "true"
        params["include_summary"] = "true"
        params["include_action_items"] = "true"
    
    response = make_fathom_request("/meetings", token, params=params)
    if "error" in response:
        return []
    
    # Fathom API returns a list in the 'items' key
    meetings = response.get("items", [])
    print(f"Found {len(meetings)} meetings:", file=sys.stderr)
    for m in meetings:
        mid = m.get("recording_id") or m.get("id")
        title = m.get("title", "Untitled")
        start = m.get("recording_start_time") or m.get("start_at", "Unknown")
        print(f"- [{mid}] {title} ({start})", file=sys.stderr)
    return meetings

def get_meeting(token, meeting_id, action="get"):
    """Retrieve a specific meeting or transcript."""
    if action == "transcript":
        endpoint = f"/recordings/{meeting_id}/transcript"
        return make_fathom_request(endpoint, token)
    else:
        # Try meetings endpoint first
        endpoint = f"/meetings/{meeting_id}"
        res = make_fathom_request(endpoint, token)
        if "error" in res and res["error"] == 404:
            # Fallback to recordings endpoint
            endpoint = f"/recordings/{meeting_id}"
            return make_fathom_request(endpoint, token)
        return res

def main():
    parser = argparse.ArgumentParser(description="Fathom API Connector")
    parser.add_argument("--action", required=True, choices=["list", "get", "transcript"], help="Action to perform")
    parser.add_argument("--id", help="Meeting ID for 'get' or 'transcript' action")
    parser.add_argument("--limit", type=int, default=20, help="Limit for listing meetings")
    parser.add_argument("--after", help="Filter meetings created after (ISO 8601)")
    parser.add_argument("--full", action="store_true", help="Include transcript/summary/action items in list")
    
    args = parser.parse_args()
    
    token = load_fathom_token()
    if not token:
        print("Error: FATHOM_API_KEY not found in token.env or environment.", file=sys.stderr)
        sys.exit(1)
        
    if args.action == "list":
        meetings = list_meetings(token, args.limit, args.after, include_all=args.full)
        print(json.dumps(meetings, indent=2))
    elif args.action in ["get", "transcript"]:
        if not args.id:
            print("Error: --id is required for get/transcript action.", file=sys.stderr)
            sys.exit(1)
        res = get_meeting(token, args.id, action=args.action)
        print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
