import argparse
import json
import os
import sys
import urllib.request
import urllib.parse

MANIFEST = {
    "display_information": {
        "name": "Secondary Assistant Bot",
        "description": "Assistant bot for Secondary ecosystem tasks",
        "background_color": "#121016"
    },
    "features": {
        "bot_user": {
            "display_name": "Secondary Assistant",
            "always_online": True
        }
    },
    "oauth_config": {
        "scopes": {
            "bot": [
                "channels:history",
                "channels:join",
                "channels:read",
                "chat:write",
                "chat:write.public",
                "files:read",
                "files:write",
                "groups:history",
                "groups:read",
                "im:history",
                "im:read",
                "mpim:history",
                "mpim:read",
                "users:read",
                "users:read.email",
                "app_mentions:read",
                "reactions:read",
                "reactions:write"
            ]
        }
    },
    "settings": {
        "org_deploy_enabled": False,
        "socket_mode_enabled": False,
        "token_rotation_enabled": False,
        "event_subscriptions": {
            "request_url": "https://example.com/slack/events",
            "bot_events": [
                "app_mention",
                "message.channels",
                "message.groups",
                "message.im",
                "message.mpim"
            ]
        }
    }
}

def call_slack_api(endpoint, config_token, data_dict):
    url = f"https://slack.com/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {config_token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    data = json.dumps(data_dict).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except Exception as e:
        print(f"Failed to call Slack API: {e}")
        return None

def update_app(config_token, app_id):
    print(f"Updating Slack App {app_id} via Manifest...")
    res_data = call_slack_api("apps.manifest.update", config_token, {"app_id": app_id, "manifest": MANIFEST})
    
    if not res_data or not res_data.get("ok"):
        print(f"Error updating app: {res_data.get('error') if res_data else 'Network Error'}")
        if res_data and res_data.get("errors"):
            print(f"Manifest errors: {res_data.get('errors')}")
        return False
    
    print(f"Success! App {app_id} updated with new scopes.")
    return True

def create_app(config_token):
    print("Creating Slack App via Manifest...")
    res_data = call_slack_api("apps.manifest.create", config_token, {"manifest": MANIFEST})
    
    if not res_data or not res_data.get("ok"):
        print(f"Error creating app: {res_data.get('error') if res_data else 'Network Error'}")
        if res_data and res_data.get("errors"):
            print(f"Manifest errors: {res_data.get('errors')}")
        return None
    
    app_id = res_data.get("app_id")
    print(f"Success! App Created. ID: {app_id}")
    print(f"Install Link: {res_data.get('install_url')}")
    print("\n!!! ACTION REQUIRED !!!")
    print(f"1. Click the Install Link above to authorize the bot in your workspace.")
    print("2. Once authorized, it will provide your 'Bot User OAuth Token' (xoxb-...).")
    print("3. Paste that token here when prompted.")
    return app_id

def main():
    parser = argparse.ArgumentParser(description="Setup Slack App using Configuration Token")
    parser.add_argument("--config-token", help="Slack Configuration Token (refreshable)")
    parser.add_argument("--update", action="store_true", help="Update existing app instead of creating new")
    parser.add_argument("--app-id", help="Slack App ID (required for update)")
    args = parser.parse_args()

    if not args.config_token:
        print("Please provide a Slack Configuration Token.")
        sys.exit(1)

    if args.update:
        if not args.app_id:
            print("Please provide an --app-id for update.")
            sys.exit(1)
        update_app(args.config_token, args.app_id)
    else:
        app_id = create_app(args.config_token)
        if app_id:
            print("\nApp setup is partially complete.")

if __name__ == "__main__":
    main()
