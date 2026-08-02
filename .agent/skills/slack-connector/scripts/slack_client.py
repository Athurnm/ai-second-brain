import argparse
import json
import os
import signal
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SKILL_DIR, '..', '..', '..', '..'))

sys.path.insert(0, os.path.join(REPO_ROOT, '.agent', 'scripts'))
from file_utils import require_send_approval  # Outbound send gate (CLAUDE.md)

# Ensure terminal outputs are always encoded in UTF-8 to prevent Windows UnicodeEncodeError
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Rate limiting configuration
MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 1
DEFAULT_TIMEOUT = 60 # increased from 15 to allow for larger payloads, but capped by global timeout
MAX_THREADS_PER_CHANNEL = 5 # only fetch replies for the first 5 threads
MAX_REPLIES_PER_THREAD = 20 # limit replies per thread

# Global timeout: 180 seconds
def timeout_handler(signum, frame):
    print("[ERROR] Slack Connector timed out after 180 seconds", file=sys.stderr)
    sys.exit(1)

if os.name != 'nt': # signal.alarm is Unix-only
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(180)

def make_slack_request(endpoint, token, params=None, retry_count=0):
    """
    Makes a request to the Slack API using urllib (standard library).
    Handles rate limiting with Retry-After header and exponential backoff.
    """
    base_url = "https://slack.com/api/"
    url = base_url + endpoint
    
    if params:
        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}
        data = urllib.parse.urlencode(params)
        url += "?" + data

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    print(f"[DEBUG] Calling Slack API: {endpoint}...", file=sys.stderr)
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body)
            
            if not data.get("ok"):
                error_code = data.get("error", "unknown_error")
                print(f"[DEBUG] Slack API returned error: {error_code}", file=sys.stderr)
                if error_code == "missing_scope":
                    print(f"[ERROR] Missing required scope. Needed for: {endpoint}", file=sys.stderr)
                return data
                
            print(f"[DEBUG] Slack API {endpoint} success.", file=sys.stderr)
            return data
    except urllib.error.HTTPError as e:
        # Handle rate limiting (429 Too Many Requests)
        if e.code == 429:
            if retry_count >= MAX_RETRIES:
                print(f"Rate limit exceeded after {MAX_RETRIES} retries. Giving up.", file=sys.stderr)
                sys.exit(1)
            
            # Check for Retry-After header
            retry_after = e.headers.get("Retry-After")
            if retry_after:
                wait_time = int(retry_after)
                print(f"Rate limited. Waiting {wait_time} seconds (from Retry-After header)...", file=sys.stderr)
            else:
                # Exponential backoff: 1, 2, 4, 8, 16 seconds
                wait_time = BASE_BACKOFF_SECONDS * (2 ** retry_count)
                print(f"Rate limited. Waiting {wait_time} seconds (exponential backoff, attempt {retry_count + 1}/{MAX_RETRIES})...", file=sys.stderr)
            
            time.sleep(wait_time)
            return make_slack_request(endpoint, token, params, retry_count + 1)
        else:
            print(f"HTTP Error: {e.code} - {e.reason}", file=sys.stderr)
            sys.exit(1)
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print(f"[ERROR] Request to {endpoint} timed out after {DEFAULT_TIMEOUT}s", file=sys.stderr)
        sys.exit(1)

def list_all_channels(token):
    """
    Lists all public channels in the workspace.
    """
    channels = []
    cursor = None
    page = 1
    
    while True:
        print(f"[DEBUG] Fetching all public channels page {page}...", file=sys.stderr)
        params = {"limit": 100, "types": "public_channel"}
        if cursor:
            params["cursor"] = cursor
            
        response = make_slack_request("conversations.list", token, params)
        if not response.get("ok"):
            print(f"Error listing all channels: {response.get('error')}", file=sys.stderr)
            break

        channels_in_page = response.get("channels", [])
        channels.extend(channels_in_page)
        print(f"[DEBUG] Received {len(channels_in_page)} channels in page {page} (Total: {len(channels)})", file=sys.stderr)
        
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        page += 1

    print(f"Found {len(channels)} public channels:")
    for channel in channels:
        print(f"- {channel['name']} (ID: {channel['id']})")

def _build_user_name_map(token):
    """
    id -> display name, one users.list sweep. Used to give DM conversations a
    readable name, since an im object carries only a user ID.
    """
    names = {}
    cursor = None
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        response = make_slack_request("users.list", token, params)
        if not response.get("ok"):
            print(f"[WARN] users.list failed ({response.get('error')}), DM names will fall back to user IDs", file=sys.stderr)
            break
        for u in response.get("members", []):
            profile = u.get("profile", {}) or {}
            label = profile.get("display_name") or profile.get("real_name") or u.get("name") or u["id"]
            names[u["id"]] = label
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return names

def list_joined_channels(token, include_dms=False):
    """
    List conversations the authenticated user is actually IN.

    include_dms also pulls im/mpim. DMs carry no 'name' field, only a user ID,
    so they are labelled dm-<display name> via a users.list map and are
    rendered with a [DM] marker so downstream filters can keep them.
    """
    channels = []
    cursor = None
    page = 1

    types = "public_channel,private_channel"
    if include_dms:
        types += ",im,mpim"

    while True:
        print(f"[DEBUG] Fetching joined channels page {page}...", file=sys.stderr)
        params = {"limit": 100, "types": types}
        if cursor:
            params["cursor"] = cursor

        # users.conversations is the API for "channels I am in"
        response = make_slack_request("users.conversations", token, params)
        if not response.get("ok"):
            print(f"Error listing joined channels: {response.get('error')}", file=sys.stderr)
            break

        channels_in_page = response.get("channels", [])
        channels.extend(channels_in_page)
        print(f"[DEBUG] Received {len(channels_in_page)} channels in page {page} (Total: {len(channels)})", file=sys.stderr)

        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        page += 1

    user_names = _build_user_name_map(token) if include_dms else {}

    print(f"Found {len(channels)} joined channels:")
    for channel in channels:
        is_dm = channel.get("is_im") or channel.get("is_mpim")
        if not is_dm:
            print(f"- {channel['name']} (ID: {channel['id']})")
            continue
        # updated is ms epoch; emit seconds so callers can filter dormant DMs
        updated_s = int(channel.get("updated", 0)) // 1000
        if channel.get("is_im"):
            uid = channel.get("user", "")
            label = f"dm-{user_names.get(uid, uid or 'unknown')}"
        else:
            label = channel.get("name", channel["id"])
        print(f"- {label} (ID: {channel['id']}) [DM updated={updated_s}]")

def get_thread_replies(token, channel_id, thread_ts):
    """
    Gets replies for a specific thread.
    """
    replies = []
    cursor = None
    
    while True:
        params = {"channel": channel_id, "ts": thread_ts, "limit": 100}
        if cursor:
            params["cursor"] = cursor
            
        response = make_slack_request("conversations.replies", token, params)
        if not response.get("ok"):
            print(f"Error getting replies for thread {thread_ts}: {response.get('error')}", file=sys.stderr)
            break

        messages = response.get("messages", [])
        replies.extend(messages)
        
        if len(replies) >= MAX_REPLIES_PER_THREAD:
            print(f"  [DEBUG] Thread reply limit reached ({MAX_REPLIES_PER_THREAD}). Stopping.", file=sys.stderr)
            break
        
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
            
    return replies

FULL_OUTPUT = False  # when True, disable the 100-char truncation in history/search prints

def _clip(text):
    """Truncate to 100 chars for display unless --full was passed."""
    if FULL_OUTPUT or len(text) <= 100:
        return text
    return text[:100] + "..."

def get_channel_history(token, channel_id, limit=20, fetch_replies=False):
    """
    Gets history for a channel.
    """
    response = make_slack_request("conversations.history", token, {"channel": channel_id, "limit": limit})
    if not response.get("ok"):
        print(f"Error getting history: {response.get('error')}", file=sys.stderr)
        return

    messages = response.get("messages", [])
    print(f"Last {len(messages)} messages in {channel_id}:")
    threads_fetched = 0
    for msg in messages:
        user = msg.get("user", "Unknown")
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        thread_ts = msg.get("thread_ts")
        reply_count = msg.get("reply_count", 0)
        files = msg.get("files", [])
        
        file_info = ""
        if files:
            file_info = " [FILES: " + ", ".join([f"{f.get('name')} (ID: {f.get('id')})" for f in files]) + "]"
        
        # Basic formatting
        print(f"[{ts}] {user}: {_clip(text)}{file_info}")
        
        if fetch_replies and thread_ts and reply_count > 0:
            if threads_fetched >= MAX_THREADS_PER_CHANNEL:
                print(f"  [Thread] Skipping replies (channel thread limit {MAX_THREADS_PER_CHANNEL} reached)")
                continue

            print(f"  [Thread] Fetching {reply_count} replies...")
            replies = get_thread_replies(token, channel_id, thread_ts)
            threads_fetched += 1
            # Skip the first one as it is the parent message
            for reply in replies[1:]:
                r_user = reply.get("user", "Unknown")
                r_text = reply.get("text", "")
                r_ts = reply.get("ts", "")
                print(f"    [{r_ts}] {r_user}: {_clip(r_text)}")

def list_channel_members(token, channel_id):
    """
    Lists members of a specific channel.
    """
    members = []
    cursor = None
    
    while True:
        params = {"channel": channel_id, "limit": 100}
        if cursor:
            params["cursor"] = cursor
            
        response = make_slack_request("conversations.members", token, params)
        if not response.get("ok"):
            print(f"Error listing members for {channel_id}: {response.get('error')}", file=sys.stderr)
            break

        members.extend(response.get("members", []))
        
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    print(f"Found {len(members)} members in {channel_id}:")
    for member_id in members:
        print(f"- {member_id}")

def search_messages(token, query):
    """
    Searches for messages matching a query.
    """
    response = make_slack_request("search.messages", token, {"query": query, "count": 20})
    if not response.get("ok"):
        print(f"Error searching messages for '{query}': {response.get('error')}", file=sys.stderr)
        return

    messages = response.get("messages", {}).get("matches", [])
    print(f"Found {len(messages)} matches for '{query}':")
    for msg in messages:
        channel = msg.get("channel", {}).get("name", "N/A")
        channel_id = msg.get("channel", {}).get("id", "N/A")
        user = msg.get("user", "N/A")
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        print(f"[{ts}] {user} in #{channel} ({channel_id}): {_clip(text)}")

def list_users(token):
    """
    Lists users in the workspace with pagination.
    """
    users = []
    cursor = None
    
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
            
        response = make_slack_request("users.list", token, params)
        if not response.get("ok"):
            print(f"Error listing users: {response.get('error')}", file=sys.stderr)
            break

        users.extend(response.get("members", []))
        
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    print(f"Found {len(users)} users:")
    for user in users:
        name = user.get("name", "N/A")
        real_name = user.get("real_name", "N/A")
        user_id = user.get("id", "N/A")
        print(f"- {real_name} (@{name}) [ID: {user_id}]")

def get_user_info(token, user_id):
    """
    Gets info for a specific user.
    """
    response = make_slack_request("users.info", token, {"user": user_id})
    if not response.get("ok"):
        print(f"Error getting user info for {user_id}: {response.get('error')}", file=sys.stderr)
        return

    user = response.get("user", {})
    name = user.get("name", "N/A")
    real_name = user.get("real_name", "N/A")
    email = user.get("profile", {}).get("email", "N/A")
    print(f"User {user_id}: {real_name} (@{name})")
    print(f"Email: {email}")

def get_channel_info(token, channel_id):
    """
    Gets info for a specific channel.
    """
    response = make_slack_request("conversations.info", token, {"channel": channel_id})
    if not response.get("ok"):
        print(f"Error getting channel info for {channel_id}: {response.get('error')}", file=sys.stderr)
        return

    channel = response.get("channel", {})
    name = channel.get("name", "N/A")
    purpose = channel.get("purpose", {}).get("value", "N/A")
    topic = channel.get("topic", {}).get("value", "N/A")
    print(f"Channel {channel_id}: #{name}")
    print(f"Purpose: {purpose}")
    print(f"Topic: {topic}")

def get_file_info(token, file_id):
    """
    Gets info for a specific file.
    """
    response = make_slack_request("files.info", token, {"file": file_id})
    if not response.get("ok"):
        print(f"Error getting file info for {file_id}: {response.get('error')}", file=sys.stderr)
        return

    file = response.get("file", {})
    name = file.get("name", "N/A")
    user = file.get("user", "N/A")
    url = file.get("url_private", "N/A")
    print(f"File {file_id}: {name}")
    print(f"Owner: {user}")
    print(f"URL: {url}")

def download_file(token, url, save_path):
    """
    Downloads a file from Slack using the token.
    """
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as response:
            with open(save_path, 'wb') as f:
                f.write(response.read())
            print(f"File downloaded to {save_path}")
            return True
    except Exception as e:
        print(f"Error downloading file: {e}", file=sys.stderr)
        return False

def upload_file(token, channel_id, file_path, initial_comment=None, thread_ts=None):
    """
    Uploads a file to a channel using the modern Slack API (files.getUploadURLExternal).
    """
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    # Step 1: Get upload URL
    params = {
        "filename": file_name,
        "length": str(file_size)
    }
    response = make_slack_request("files.getUploadURLExternal", token, params)
    if not response.get('ok'):
        print(f"Error getting upload URL: {response.get('error')}", file=sys.stderr)
        return False

    upload_url = response.get('upload_url')
    file_id = response.get('file_id')

    # Step 2: Upload to external URL (using PUT as per Slack docs)
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
            
        req = urllib.request.Request(upload_url, data=file_data, method='POST')
        with urllib.request.urlopen(req) as upload_res:
            if upload_res.status != 200:
                print(f"Error uploading file data: {upload_res.status}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"Error uploading file data: {e}", file=sys.stderr)
        return False

    # Step 3: Complete upload
    complete_params = {
        "files": json.dumps([{"id": file_id, "title": file_name}]),
        "channel_id": channel_id,
        "initial_comment": initial_comment
    }
    # Without thread_ts the file lands as a loose channel message, detached from
    # the message it belongs to. Pass the parent ts to keep it in the thread.
    if thread_ts:
        complete_params["thread_ts"] = thread_ts
    # completeUploadExternal requires POST with form data
    complete_response = make_slack_request("files.completeUploadExternal", token, complete_params)
    if not complete_response.get('ok'):
        print(f"Error completing upload: {complete_response.get('error')}", file=sys.stderr)
        return False

    print(f"File uploaded successfully: {file_id}")
    return True

def lookup_user_by_name(token, name, channel_id=None):
    """
    Looks up a user ID by their Slack handle (@name) or real name.
    Falls back to channel members if not found in global list.
    """
    search_name = name.lower().lstrip('@')
    
    # 1. Global search
    cursor = None
    while True:
        params = {"limit": 100}
        if cursor: params["cursor"] = cursor
        response = make_slack_request("users.list", token, params)
        if not response.get("ok"): break
        for member in response.get("members", []):
            if member.get("name", "").lower() == search_name or \
               member.get("real_name", "").lower() == search_name or \
               member.get("profile", {}).get("display_name", "").lower() == search_name:
                return member.get("id")
        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor: break

    # 2. Fallback: Search channel members (reliable for guest users)
    if channel_id:
        cursor = None
        while True:
            params = {"channel": channel_id, "limit": 100}
            if cursor: params["cursor"] = cursor
            response = make_slack_request("conversations.members", token, params)
            if not response.get("ok"): break
            
            for uid in response.get("members", []):
                u_res = make_slack_request("users.info", token, {"user": uid})
                if u_res.get("ok"):
                    u = u_res.get("user", {})
                    uname = u.get("name", "").lower()
                    ureal = u.get("real_name", "").lower()
                    udisp = u.get("profile", {}).get("display_name", "").lower()
                    if uname == search_name or ureal == search_name or udisp == search_name:
                        return uid
            
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor: break
            
    return None

def post_message(token, channel_id, text, thread_ts=None, unfurl=False):
    """
    Posts a message to a channel (or as a thread reply when thread_ts is set),
    automatically resolving @usernames to <@ID>. Prints the permalink on success.
    """
    import re

    # Self-heal broken mention syntax that slips in from hand-written drafts.
    # 1. HTML-escaped brackets render as literal text and never ping:
    #    &lt;@U123&gt; -> <@U123>  (also #channel and !here/!channel/!subteam)
    text = re.sub(r'&lt;([@#!][A-Z0-9]+(?:\|[^&]*?)?)&gt;', r'<\1>', text)
    text = re.sub(r'&lt;(![a-z]+(?:\^[A-Z0-9]+)?(?:\|[^&]*?)?)&gt;', r'<\1>', text)
    # 2. Legacy "<@ID|Name>" label form often renders literally; Slack shows the
    #    canonical name from a bare "<@ID>", so strip any |label.
    text = re.sub(r'<@([A-Z0-9]+)\|[^>]*>', r'<@\1>', text)

    # Find @username (alphanumeric, dots, underscores, dashes).
    # Negative lookbehind for '<' so already-formed <@USERID> mentions are left
    # alone (otherwise each would trigger a full users.list scan and get mangled).
    mentions = re.findall(r'(?<!<)@([a-zA-Z0-9\._-]+)', text)
    for name in mentions:
        user_id = lookup_user_by_name(token, name, channel_id)
        if user_id:
            text = text.replace(f'@{name}', f'<@{user_id}>')
            print(f"Resolved @{name} to <@{user_id}>")
        else:
            print(f"Warning: Could not resolve @{name}")

    params = {"channel": channel_id, "text": text}
    if thread_ts:
        params["thread_ts"] = thread_ts
    if not unfurl:
        params["unfurl_links"] = "false"
        params["unfurl_media"] = "false"
    response = make_slack_request("chat.postMessage", token, params)
    if not response.get("ok"):
        print(f"Error posting message: {response.get('error')}", file=sys.stderr)
        return False
    print("Message posted successfully")
    ts = response.get("ts")
    ch = response.get("channel", channel_id)
    if ts:
        pl = make_slack_request("chat.getPermalink", token, {"channel": ch, "message_ts": ts})
        if pl.get("ok"):
            print(f"Permalink: {pl.get('permalink')}")
    return True

def update_message(token, channel_id, message_ts, text, unfurl=False):
    """
    Edits an existing message the owner authored (chat.update, requires the xoxp
    user token). Applies the same mention self-healing as post_message.
    Prints the permalink on success.
    """
    import re

    text = re.sub(r'&lt;([@#!][A-Z0-9]+(?:\|[^&]*?)?)&gt;', r'<\1>', text)
    text = re.sub(r'&lt;(![a-z]+(?:\^[A-Z0-9]+)?(?:\|[^&]*?)?)&gt;', r'<\1>', text)
    text = re.sub(r'<@([A-Z0-9]+)\|[^>]*>', r'<@\1>', text)

    mentions = re.findall(r'(?<!<)@([a-zA-Z0-9\._-]+)', text)
    for name in mentions:
        user_id = lookup_user_by_name(token, name, channel_id)
        if user_id:
            text = text.replace(f'@{name}', f'<@{user_id}>')
            print(f"Resolved @{name} to <@{user_id}>")
        else:
            print(f"Warning: Could not resolve @{name}")

    params = {"channel": channel_id, "ts": message_ts, "text": text}
    if not unfurl:
        params["unfurl_links"] = "false"
        params["unfurl_media"] = "false"
    response = make_slack_request("chat.update", token, params)
    if not response.get("ok"):
        print(f"Error updating message: {response.get('error')}", file=sys.stderr)
        return False
    print("Message updated successfully")
    ch = response.get("channel", channel_id)
    ts = response.get("ts", message_ts)
    pl = make_slack_request("chat.getPermalink", token, {"channel": ch, "message_ts": ts})
    if pl.get("ok"):
        print(f"Permalink: {pl.get('permalink')}")
    return True

def invite_user(token, channel_id, user_ids):
    """
    Invites users to a specific channel.
    user_ids: comma-separated list of user IDs.
    """
    params = {"channel": channel_id, "users": user_ids}
    response = make_slack_request("conversations.invite", token, params)
    if not response.get("ok"):
        print(f"Error inviting users: {response.get('error')}", file=sys.stderr)
        return False
    print(f"Users invited successfully to {channel_id}")
    return True

def join_channel(token, channel_id):
    """
    Joins a channel.
    """
    params = {"channel": channel_id}
    response = make_slack_request("conversations.join", token, params)
    if not response.get("ok"):
        print(f"Error joining channel: {response.get('error')}", file=sys.stderr)
        return False
    print(f"Joined channel {channel_id} successfully")
    return True

def leave_channel(token, channel_id):
    """
    Leaves a channel.
    """
    params = {"channel": channel_id}
    response = make_slack_request("conversations.leave", token, params)
    if not response.get("ok"):
        print(f"Error leaving channel: {response.get('error')}", file=sys.stderr)
        return False
    print(f"Left channel {channel_id} successfully")
    return True

def main():
    parser = argparse.ArgumentParser(description="Slack Connector Helper")
    parser.add_argument("--action", required=True, choices=["list_channels", "list_joined_channels", "history", "list_users", "user_info", "channel_members", "search", "channel_info", "file_info", "download", "upload", "post", "update", "lookup", "invite", "join", "leave"], help="Action to perform")
    parser.add_argument("--token", help="Explicit Slack token. Default for all actions is SLACK_USER_TOKEN (xoxp, the owner's), falling back to SLACK_BOT_TOKEN. Use --bot to force the bot token.")
    parser.add_argument("--channel", help="Channel ID for history, channel_members, upload, post, lookup, invite, join, and leave actions")
    parser.add_argument("--user", help="User ID/Name for user_info or lookup action")
    parser.add_argument("--users", help="User IDs (comma-separated) for invite action")
    parser.add_argument("--file", help="File ID for file_info action")
    parser.add_argument("--url", help="URL for download action")
    parser.add_argument("--path", help="Local path for download/upload action")
    parser.add_argument("--text", help="Text for post action")
    parser.add_argument("--comment", help="Comment for upload action")
    parser.add_argument("--query", help="Query for search action")
    parser.add_argument("--limit", type=int, default=20, help="Number of messages to retrieve")
    parser.add_argument("--replies", action="store_true", help="Fetch thread replies in history")
    parser.add_argument("--as-user", dest="as_user", action="store_true", help="Post as the owner using SLACK_USER_TOKEN (no Claude-bot footer). This is the default for the post action.")
    parser.add_argument("--bot", action="store_true", help="Force the bot token (xoxb) for post instead of the user token.")
    parser.add_argument("--thread-ts", dest="thread_ts", help="Parent message ts to reply in-thread (post action).")
    parser.add_argument("--ts", dest="message_ts", help="Timestamp of the message to edit (update action).")
    parser.add_argument("--text-file", dest="text_file", help="Read post text from a file instead of --text (avoids shell escaping).")
    parser.add_argument("--unfurl", action="store_true", help="Enable link/media unfurling on post (default: off).")
    parser.add_argument("--approved", action="store_true", help="Confirm the owner has explicitly approved this specific send before it goes out. Required for post/upload/invite; there is no environment override.")
    parser.add_argument("--full", action="store_true", help="Disable the 100-char truncation in history/search output (print full message text).")
    parser.add_argument("--include-dms", action="store_true", help="list_joined_channels only: also list im/mpim conversations, labelled dm-<name> and marked [DM].")

    args = parser.parse_args()

    global FULL_OUTPUT
    FULL_OUTPUT = args.full

    # Auto-load token.env from the connector directory so SLACK_USER_TOKEN /
    # SLACK_BOT_TOKEN are available without a manual export.
    #
    # token.env carries credentials only. It must never be able to grant
    # authorization, so keys that would relax the send gate are refused here
    # even though the gate itself no longer consults the environment. This
    # keeps a future re-introduction of an env flag from silently becoming
    # writable by a credentials file.
    _TOKEN_ENV_DENYLIST = {"SLACK_SEND_UNATTENDED"}
    _token_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "token.env")
    if os.path.exists(_token_env):
        with open(_token_env) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k = _k.strip()
                    if _k in _TOKEN_ENV_DENYLIST:
                        print(
                            f"[WARN] Ignoring '{_k}' in token.env: that file supplies "
                            "credentials only and cannot grant send authorization.",
                            file=sys.stderr,
                        )
                        continue
                    os.environ.setdefault(_k, _v.strip())

    # Token selection. Default to the owner's user token (xoxp) for EVERY action:
    # it is a member of every channel the owner is in and is the only token type
    # Slack allows for search.messages. The bot token (xoxb) is only in a couple
    # of channels and lacks history scope, so reads with it fail with
    # channel_not_found / not_in_channel / not_allowed_token_type. This also keeps
    # sends going out AS the owner (no Claude-bot footer), per the standing rule.
    # --token overrides everything; --bot forces the bot token (e.g. for actions
    # that must run as the app, like join); --as-user is kept for back-compat.
    if args.token:
        token = args.token
    elif args.bot:
        token = os.environ.get("SLACK_BOT_TOKEN")
    else:
        token = os.environ.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("Error: Slack token not found. Pass --token, or set SLACK_USER_TOKEN / SLACK_BOT_TOKEN (token.env).", file=sys.stderr)
        sys.exit(1)

    if args.action == "list_channels":
        list_all_channels(token)
    elif args.action == "list_joined_channels":
        list_joined_channels(token, include_dms=args.include_dms)
    elif args.action == "history":
        if not args.channel:
            print("Error: --channel is required for history action.", file=sys.stderr)
            sys.exit(1)
        get_channel_history(token, args.channel, args.limit, args.replies)
    elif args.action == "list_users":
        list_users(token)
    elif args.action == "user_info":
        if not args.user:
            print("Error: --user is required for user_info action.", file=sys.stderr)
            sys.exit(1)
        get_user_info(token, args.user)
    elif args.action == "lookup":
        if not args.user:
            print("Error: --user (name) is required for lookup action.", file=sys.stderr)
            sys.exit(1)
        uid = lookup_user_by_name(token, args.user, args.channel)
        if uid:
            print(f"User ID for {args.user}: {uid}")
        else:
            print(f"User {args.user} not found.")
    elif args.action == "channel_members":
        if not args.channel:
            print("Error: --channel is required for channel_members action.", file=sys.stderr)
            sys.exit(1)
        list_channel_members(token, args.channel)
    elif args.action == "search":
        if not args.query:
            print("Error: --query is required for search action.", file=sys.stderr)
            sys.exit(1)
        search_messages(token, args.query)
    elif args.action == "channel_info":
        if not args.channel:
            print("Error: --channel is required for channel_info action.", file=sys.stderr)
            sys.exit(1)
        get_channel_info(token, args.channel)
    elif args.action == "file_info":
        if not args.file:
            print("Error: --file is required for file_info action.", file=sys.stderr)
            sys.exit(1)
        get_file_info(token, args.file)
    elif args.action == "download":
        if not args.url or not args.path:
            print("Error: --url and --path are required for download action.", file=sys.stderr)
            sys.exit(1)
        download_file(token, args.url, args.path)
    elif args.action == "upload":
        if not args.channel or not args.path:
            print("Error: --channel and --path are required for upload action.", file=sys.stderr)
            sys.exit(1)
        require_send_approval("upload a file to Slack", args.approved)
        upload_file(token, args.channel, args.path, args.comment, args.thread_ts)
    elif args.action == "post":
        text = args.text
        if args.text_file:
            with open(args.text_file) as _tf:
                text = _tf.read().strip()
        if not args.channel or not text:
            print("Error: --channel and (--text or --text-file) are required for post action.", file=sys.stderr)
            sys.exit(1)
        require_send_approval("post a Slack message", args.approved)
        post_message(token, args.channel, text, thread_ts=args.thread_ts, unfurl=args.unfurl)
    elif args.action == "update":
        text = args.text
        if args.text_file:
            with open(args.text_file) as _tf:
                text = _tf.read().strip()
        if not args.channel or not args.message_ts or not text:
            print("Error: --channel, --ts and (--text or --text-file) are required for update action.", file=sys.stderr)
            sys.exit(1)
        require_send_approval("edit an existing Slack message", args.approved)
        update_message(token, args.channel, args.message_ts, text, unfurl=args.unfurl)
    elif args.action == "invite":
        if not args.channel or not args.users:
            print("Error: --channel and --users are required for invite action.", file=sys.stderr)
            sys.exit(1)
        require_send_approval("invite users to a Slack channel", args.approved)
        invite_user(token, args.channel, args.users)
    elif args.action == "join":
        if not args.channel:
            print("Error: --channel is required for join action.", file=sys.stderr)
            sys.exit(1)
        join_channel(token, args.channel)
    elif args.action == "leave":
        if not args.channel:
            print("Error: --channel is required for leave action.", file=sys.stderr)
            sys.exit(1)
        leave_channel(token, args.channel)

if __name__ == "__main__":
    main()
