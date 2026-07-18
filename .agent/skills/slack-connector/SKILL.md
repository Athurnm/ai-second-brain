---
name: Slack Connector
description: A skill to interact with Slack, allowing listing channels and reading message history.
---

# Slack Connector Skill

This skill allows the agent to interact with a Slack workspace using a Bot Token.

## Capabilities

1.  **List Channels**: Retrieve a list of public channels in the workspace.
2.  **Read History**: Retrieve message history from a specific channel.

## Prerequisites

-   A Slack Bot Token (starting with `xoxb-`) with the following scopes:
    -   `channels:read`
    -   `channels:history`
    -   (Optional) `groups:read`, `groups:history`, `im:read`, `im:history`, `mpim:read`, `mpim:history` for private channels/DMs.
-   Python 3 installed.
-   `requests` library (`pip install requests`).
-   **Timeouts**: The script has a built-in **180-second global timeout**. Always wrap background calls in `timeout 180s` for safety.

## Usage

The skill uses a helper script located at `scripts/slack_client.py`.

### List Channels

```bash
timeout 180s python3 .agent/skills/slack-connector/scripts/slack_client.py --action list_channels --token <YOUR_SLACK_TOKEN>
```

### Read Channel History

```bash
timeout 180s python3 .agent/skills/slack-connector/scripts/slack_client.py --action history --channel <CHANNEL_ID> --token <YOUR_SLACK_TOKEN> [--replies]
```
Use `--replies` to fetch thread replies for each message.

You can also set the `SLACK_BOT_TOKEN` environment variable to avoid passing `--token` every time.

```bash
export SLACK_BOT_TOKEN="xoxb-..."
python .agent/skills/slack-connector/scripts/slack_client.py --action list_channels
```

### Send Approval Gate

`post`, `upload`, and `invite` mutate outbound Slack state (they post messages,
files, or add channel members), so they are default-blocked. The command
refuses before touching the network unless one of these is given:

- `--approved`, once the owner has explicitly approved the draft. This is the
  form to use when an agent is sending on the owner's behalf.
- `SLACK_SEND_UNATTENDED=1` in the environment, for cron and automation that
  legitimately runs with no human present.

```bash
python3 .agent/skills/slack-connector/scripts/slack_client.py --action post \
  --channel <CHANNEL_ID> --text "Your message" --approved
```

Without either, the command exits nonzero and prints both ways to proceed.
Never retry a refused send by adding `--approved` on a guess; only pass it
once the owner has actually approved the message.
