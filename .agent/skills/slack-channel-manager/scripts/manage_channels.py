import json
import argparse
import os

CHANNELS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "channels.json")

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return {}
    with open(CHANNELS_FILE, "r") as f:
        return json.load(f)

def save_channels(data):
    with open(CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Manage Slack channel whitelist")
    parser.add_argument("--action", choices=["list", "add", "remove"], required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--channel_id")
    parser.add_argument("--channel_name")
    
    args = parser.parse_args()
    data = load_channels()
    
    if args.client not in data:
        data[args.client] = {}
        
    if args.action == "list":
        print(f"Whitelisted channels for {args.client}:")
        for cid, name in data[args.client].items():
            print(f"- {cid}: {name}")
            
    elif args.action == "add":
        if not args.channel_id or not args.channel_name:
            print("Error: --channel_id and --channel_name required for 'add'")
            return
        data[args.client][args.channel_id] = args.channel_name
        save_channels(data)
        print(f"Added {args.channel_name} ({args.channel_id}) to {args.client} whitelist.")
        
    elif args.action == "remove":
        if not args.channel_id:
            print("Error: --channel_id required for 'remove'")
            return
        if args.channel_id in data[args.client]:
            name = data[args.client].pop(args.channel_id)
            save_channels(data)
            print(f"Removed {name} ({args.channel_id}) from {args.client} whitelist.")
        else:
            print(f"Channel {args.channel_id} not found in {args.client} whitelist.")

if __name__ == "__main__":
    main()
