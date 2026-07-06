import argparse
import json
import os
import requests
import signal
import sys

class ClickUpClient:
    BASE_URL = "https://api.clickup.com/api/v2"

    def __init__(self, token=None):
        self.token = token or os.environ.get("CLICKUP_ACCESS_TOKEN")
        if not self.token:
            print("Error: ClickUp Access Token is required. Use --token or set CLICKUP_ACCESS_TOKEN env var.")
            sys.exit(1)
        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }
        
        # Global timeout: 180 seconds
        def timeout_handler(signum, frame):
            print("[ERROR] ClickUp Connector timed out after 180 seconds", file=sys.stderr)
            sys.exit(1)

        if os.name != 'nt': # signal.alarm is Unix-only
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(180)

    def _get(self, endpoint):
        response = requests.get(f"{self.BASE_URL}{endpoint}", headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint, data):
        response = requests.post(f"{self.BASE_URL}{endpoint}", headers=self.headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        return response.json()

    def _put(self, endpoint, data):
        response = requests.put(f"{self.BASE_URL}{endpoint}", headers=self.headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        return response.json()

    def get_user(self):
        return self._get("/user")

    def list_teams(self):
        return self._get("/team")

    def list_spaces(self, team_id):
        return self._get(f"/team/{team_id}/space")

    def list_folders(self, space_id):
        return self._get(f"/space/{space_id}/folder")

    def list_lists(self, folder_id=None, space_id=None):
        if folder_id:
            return self._get(f"/folder/{folder_id}/list")
        elif space_id:
            return self._get(f"/space/{space_id}/list")
        else:
            raise ValueError("Either folder_id or space_id must be provided")

    def list_tasks(self, list_id, archived=False):
        return self._get(f"/list/{list_id}/task?archived={str(archived).lower()}")

    def get_task(self, task_id):
        return self._get(f"/task/{task_id}")

    def create_task(self, list_id, name, description=None, status=None, priority=None, assignees=None):
        data = {
            "name": name,
            "description": description,
        }
        if status:
            data["status"] = status
        if priority:
            data["priority"] = priority
        if assignees:
            data["assignees"] = assignees
        
        return self._post(f"/list/{list_id}/task", data)

    def update_task(self, task_id, name=None, description=None, status=None, priority=None, assignees=None):
        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if status:
            data["status"] = status
        if priority:
            data["priority"] = priority
        if assignees:
            data["assignees"] = assignees
        
        return self._put(f"/task/{task_id}", data)

def main():
    parser = argparse.ArgumentParser(description="ClickUp API Client")
    parser.add_argument("--action", required=True, choices=[
        "get_user", "list_teams", "list_spaces", "list_folders", "list_lists", "list_tasks", "get_task", "create_task", "update_task"
    ])
    parser.add_argument("--token", help="ClickUp Personal Access Token")
    parser.add_argument("--team_id", help="Team (Workspace) ID")
    parser.add_argument("--space_id", help="Space ID")
    parser.add_argument("--folder_id", help="Folder ID")
    parser.add_argument("--list_id", help="List ID")
    parser.add_argument("--task_id", help="Task ID")
    parser.add_argument("--name", help="Task Name (for create_task)")
    parser.add_argument("--description", help="Task Description (for create_task)")
    parser.add_argument("--status", help="Task Status (for create_task)")
    parser.add_argument("--priority", type=int, help="Task Priority (1-4, for create_task)")
    parser.add_argument("--assignees", nargs="+", type=int, help="List of Assignee IDs (for create_task)")

    args = parser.parse_args()
    client = ClickUpClient(args.token)

    try:
        if args.action == "get_user":
            result = client.get_user()
        elif args.action == "list_teams":
            result = client.list_teams()
        elif args.action == "list_spaces":
            if not args.team_id:
                print("Error: --team_id is required for list_spaces")
                sys.exit(1)
            result = client.list_spaces(args.team_id)
        elif args.action == "list_folders":
            if not args.space_id:
                print("Error: --space_id is required for list_folders")
                sys.exit(1)
            result = client.list_folders(args.space_id)
        elif args.action == "list_lists":
            if not args.folder_id and not args.space_id:
                print("Error: --folder_id or --space_id is required for list_lists")
                sys.exit(1)
            result = client.list_lists(args.folder_id, args.space_id)
        elif args.action == "list_tasks":
            if not args.list_id:
                print("Error: --list_id is required for list_tasks")
                sys.exit(1)
            result = client.list_tasks(args.list_id)
        elif args.action == "get_task":
            if not args.task_id:
                print("Error: --task_id is required for get_task")
                sys.exit(1)
            result = client.get_task(args.task_id)
        elif args.action == "create_task":
            if not args.list_id or not args.name:
                print("Error: --list_id and --name are required for create_task")
                sys.exit(1)
            result = client.create_task(args.list_id, args.name, args.description, args.status, args.priority, args.assignees)
        elif args.action == "update_task":
            if not args.task_id:
                print("Error: --task_id is required for update_task")
                sys.exit(1)
            result = client.update_task(args.task_id, args.name, args.description, args.status, args.priority, args.assignees)

        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
