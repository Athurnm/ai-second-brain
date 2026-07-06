---
name: Secondary Slack Connector
description: Interact with the Slack workspace of the secondary client (whatever company is currently in use besides Work), listing channels and reading message history. Generic, company-agnostic.
---

# Secondary Slack Connector Skill

Generic Slack connector for the **secondary client** workspace (the non-Work company currently in use). Drop that workspace's bot token into `token.env` and it serves it.

## Capabilities

1.  **List Channels**: Retrieve a list of public channels in the workspace.
2.  **Read History**: Retrieve message history from a specific channel.
3.  **Thread Support**: Read or post replies to specific message threads.
4.  **User Caching**: Instant user ID lookups via local JSON cache.

## Usage

The skill uses a helper script located at `scripts/slack_client.py`.

### List Channels

```bash
python .agent/skills/secondary-slack-connector/scripts/slack_client.py --action list_channels
```

```bash
python .agent/skills/secondary-slack-connector/scripts/slack_client.py --action history --channel <CHANNEL_ID>
```

### Post to Thread

```bash
python .agent/skills/secondary-slack-connector/scripts/slack_client.py --action post --channel <CHANNEL_ID> --text "Your message" --thread_ts <TIMESTAMP>
```

### User ID Caching

The skill automatically caches user IDs in `scripts/user_cache.json` after the first lookup, making subsequent mentions extremely fast.

### Token Configuration

The skill expects a `SLACK_BOT_TOKEN` environment variable or a `token.env` file in the skill root.
To set up the token:
1. Create `.agent/skills/secondary-slack-connector/token.env`.
2. Add the secondary client's Bot Token: `SLACK_BOT_TOKEN=xoxb-...`
