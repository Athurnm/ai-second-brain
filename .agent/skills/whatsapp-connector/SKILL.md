---
name: WhatsApp Connector
description: Allows the agent to read and send messages, check status, and monitor communities on WhatsApp Web using a persistent session.
---

# WhatsApp Connector Skill

This skill enables the agent to interact with WhatsApp Web. It relies on a persistent Chromium session managed by the `browser-service`.

## Capabilities

1. **Send Messages**: Search for a contact or group and send text messages.
2. **Read Today's Updates**: Summarize chats, communities, and status updates from the last 24 hours.
3. **Monitor Status**: Check recent status updates from contacts.
4. **Community Access**: Access and read updates from joined communities.

## Prerequisites

- The `browser-service` must be running with the persistent data directory:
  `--user-data-dir="$HOME/.config/antigravity-chrome-data"`
- User must have performed the initial QR scan.

## Usage Guidelines

### Sending a Message
1. Use `browser_subagent` to navigate to `https://web.whatsapp.com`.
2. Click the search bar (Selector: `div[contenteditable="true"][data-tab="3"]`).
3. Type the contact/group name.
4. Click the correct chat from the results.
5. Type the message in the input box (Selector: `div[contenteditable="true"][data-tab="10"]`).
6. Press Enter.

### Reading Today's Updates
1. Navigate to `https://web.whatsapp.com`.
2. Scan the left sidebar for chats with recent timestamps.
3. To read Status: Click the Status icon (Selector: `span[data-icon="status-v3"]` or similar).
4. To read Communities: Click the Communities icon (Selector: `span[data-icon="community-v2"]`).

### Forwarding from Channels
1. Navigate to `https://web.whatsapp.com`.
2. Click the 'Channels' icon in the sidebar (Selector: `span[data-icon="newsletter-outline"]` or `span[data-icon="channels-outline"]`).
3. Click the desired channel (e.g., "Karir & Growth You").
4. Identify the latest post (usually the bottom-most entry).
5. Hover over the post and click the 'Forward' arrow icon (appears on the top right or bottom of the message block).
6. In the search box of the 'Forward message to' dialog, search for the target groups/contacts.
7. Check the boxes for all intended recipients.
8. Click the green 'Send' circle button.
9. **Limitation**: WhatsApp Web currently does not support forwarding channel posts to 'My Status'.

## Safety & Privacy
- **DO NOT** read messages outside the scope requested by the user.
- **DO NOT** share private chat content with external APIs unless explicitly instructed.
- Always confirm before sending sensitive or bulk messages.

## Persistence Note
The session is stored in `~/.config/antigravity-chrome-data`. If the agent reports a QR code screen, it means the session has expired or was cleared.
