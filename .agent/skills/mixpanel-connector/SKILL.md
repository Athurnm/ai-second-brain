---
name: Mixpanel Connector
description: Connector for Mixpanel analytics — track events, read data, query funnels & retention, export raw events.
---

# Mixpanel Connector Skill

Enables the agent to interact with Mixpanel via REST API.

## Setup

1. Fill in credentials in `token.env`:
   - `MIXPANEL_PROJECT_TOKEN` — from Project Settings
   - `MIXPANEL_PROJECT_ID` — numeric ID in project URL
   - `MIXPANEL_API_SECRET` — from Settings → Access Keys
   - (Optional) `MIXPANEL_SERVICE_ACCOUNT_USERNAME` + `MIXPANEL_SERVICE_ACCOUNT_SECRET` — preferred over API Secret

2. Where to find credentials:
   - Go to `mixpanel.com` → your project → **Settings** → **Project Settings**
   - Token & Secret are under **Access Keys**
   - Service accounts: **Settings** → **Organization Settings** → **Service Accounts**

---

## Commands

All commands: `timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py <action> [options]`

### Track an Event
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py track \
  --event "Button Clicked" \
  --id "user_123" \
  --props '{"button": "signup", "page": "home"}'
```

### Set User Profile Properties
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py people \
  --id "user_123" \
  --props '{"$name": "You", "$email": "brian@example.com", "plan": "pro"}'
```

### Query Event Counts Over Time
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py query-events \
  --events "Button Clicked,Page Viewed" \
  --from 2026-04-01 \
  --to 2026-04-30 \
  --unit day
```

### List Top Events by Volume
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py top-events --limit 20
```

### List All Funnels
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py list-funnels
```

### Query Funnel Data
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py query-funnel \
  --id 12345 \
  --from 2026-04-01 \
  --to 2026-04-30
```

### Query Retention
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py retention \
  --from 2026-04-01 \
  --to 2026-04-30 \
  --born-event "Signup Completed" \
  --unit week
```

### Export Raw Events
```bash
timeout 180s python3 .agent/skills/mixpanel-connector/scripts/mixpanel_client.py export \
  --from 2026-04-01 \
  --to 2026-04-07 \
  --events "Button Clicked,Purchase" \
  --limit 500
```

---

## Notes
- All timeouts are set to 180s globally.
- No external libraries needed — uses Python stdlib only.
- Service Account auth is preferred over API Secret for production use.
- The `export` command hits `data.mixpanel.com` (separate from query API).
