---
name: Fathom Connector
description: A skill to interact with the Fathom AI API, allowing retrieval of meetings, recordings, and transcripts.
---

# Fathom Connector Skill

> **Preferred method**: Use the **MCP Fathom server** (`mcp__fathom__*` tools), configured in `~/.claude/settings.json`. It is faster, needs no timeout guards, and exposes meetings, transcripts, and summaries natively.
>
> Use this Python script only as a **fallback** when MCP is unavailable.

## Capabilities

1.  **List Meetings**: Retrieve a list of recent meetings recorded by the user.
2.  **Get Transcript**: Retrieve the full transcript for a specific meeting.
3.  **Search Recordings**: Find recordings by title or date.
- **Timeouts**: Scripts have a built-in **180-second global timeout**. Always wrap background calls in `timeout 180s` for safety.

## Usage (Fallback — Python Script)

The skill uses a helper script located at `.agent/skills/fathom-connector/scripts/fathom_client.py`.

### List Recent Meetings

```bash
timeout 180s python3 .agent/skills/fathom-connector/scripts/fathom_client.py --action list
```

### Get Transcript for a Meeting

```bash
timeout 180s python3 .agent/skills/fathom-connector/scripts/fathom_client.py --action transcript --id <MEETING_ID>
```

## Token Configuration

The script expects a `FATHOM_API_KEY` in `.agent/skills/fathom-connector/token.env`.
Format:
```env
FATHOM_API_KEY=your_api_key_here
```

The MCP server uses the same key, configured via the `Authorization: Bearer` header in `~/.claude/settings.json`.
