import json
import argparse
import os
import subprocess
from datetime import datetime, timedelta

CHANNELS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "channels.json")
SLACK_CLIENT_PATH = ".agent/skills/slack-connector/scripts/slack_client.py"

def load_channels(client):
    if not os.path.exists(CHANNELS_FILE):
        return {}
    with open(CHANNELS_FILE, "r") as f:
        data = json.load(f)
        return data.get(client, {})

def get_channel_history(channel_id, channel_name, days):
    print(f"\n--- Fetching updates for {channel_name} ({channel_id}) ---")
    cmd = [
        "python3", SLACK_CLIENT_PATH,
        "--action", "history",
        "--channel", channel_id,
        "--limit", "50"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching history for {channel_name}: {e.stderr}")

def main():
    parser = argparse.ArgumentParser(description="Get updates from whitelisted Slack channels")
    parser.add_argument("--client", required=True)
    parser.add_argument("--days", type=int, default=1)
    
    args = parser.parse_args()
    channels = load_channels(args.client)
    
    if not channels:
        print(f"No whitelisted channels found for {args.client}.")
        return
        
    print(f"Scanning {len(channels)} channels for {args.client}...")
    for cid, name in channels.items():
        get_channel_history(cid, name, args.days)

if __name__ == "__main__":
    main()
