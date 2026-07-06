---
name: ClickUp Connector
description: A skill to interact with ClickUp workspaces, allowing retrieval of spaces, folders, lists, and tasks, plus task creation.
---

# ClickUp Connector Skill

This skill allows the agent to interact with a ClickUp workspace using a Personal Access Token.

## Capabilities

1.  **Get Authorized User**: Verify connection and get user details.
2.  **List Teams (Workspaces)**: Retrieve a list of workspaces.
3.  **List Spaces**: Retrieve spaces within a workspace.
4.  **List Folders**: Retrieve folders within a space.
5.  **List Lists**: Retrieve lists within a folder or space.
6.  **List Tasks**: Retrieve tasks within a list.
7.  **Get Task**: Retrieve details of a specific task.
8.  **Create Task**: Create a new task in a specific list.

## Prerequisites

-   A ClickUp Personal Access Token (starting with `pk_`).
    -   Generate one in ClickUp: **Settings > Apps > API Token > Generate**.
-   Python 3 installed.
-   `requests` library (`pip install requests`).
-   **Timeouts**: The script has a built-in **180-second global timeout**. Always wrap background calls in `timeout 180s` for safety.

## Usage

The skill uses a helper script located at `scripts/clickup_client.py`.

### List Teams

```bash
timeout 180s python3 .agent/skills/clickup-connector/scripts/clickup_client.py --action list_teams --token <YOUR_CLICKUP_TOKEN>
```

### Create Task

```bash
timeout 180s python3 .agent/skills/clickup-connector/scripts/clickup_client.py --action create_task --list_id <LIST_ID> --name "Task Name" --description "Task Description" --token <YOUR_CLICKUP_TOKEN>
```

You can also set the `CLICKUP_ACCESS_TOKEN` environment variable to avoid passing `--token` every time.

```bash
export CLICKUP_ACCESS_TOKEN="pk_..."
python .agent/skills/clickup-connector/scripts/clickup_client.py --action list_teams
```
