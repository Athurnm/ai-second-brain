---
description: Draft a Slack message for You's review - NEVER sends without explicit approval ("kirim")
argument-hint: "<what to say and to whom / which channel>"
---

Slack message workflow (approval-gated):

1. Identify the target channel/DM. If ambiguous, ask You. For thread/channel context, read history via `python3 .agent/skills/slack-connector/scripts/slack_client.py` (read-only).
2. Draft the full message. Language: English for Work channels (match the thread's language if it differs). No em-dashes. When replying about a specific task, include the direct Slack permalink (see harness memory `feedback_slack_links`).
3. Spawn the `draft-reviewer` subagent with: the draft, type "Slack", target channel, and audience. Fix any issues it raises before presenting.
4. Present to You: the final draft + target channel/DM + one-line reason for sending.
5. WAIT for explicit approval ("kirim", "send", "approve"). Do NOT send speculatively. Do NOT treat general agreement as send approval.
6. Only after approval: send via the Slack MCP send tool. A PreToolUse hook will surface one extra confirmation prompt - that is expected behavior, not an error.
7. After sending, report the message timestamp/permalink.

Request: $ARGUMENTS
