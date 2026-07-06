---
name: Browser Service
description: Ensures the Chrome CDP browser service is running before any browser interaction. Must be invoked before using browser_subagent.
---

# Browser Service Skill

This skill ensures the headless Chromium CDP (Chrome DevTools Protocol) service is running on `127.0.0.1:9222` before any browser tool usage. **You MUST run this skill's check before every `browser_subagent` call.**

## When to Use

**Every time** you are about to call the `browser_subagent` tool, run the ensure script first. This guarantees the CDP backend is responsive.

## Usage

Before calling `browser_subagent`, run:

```bash
bash .agent/skills/browser-service/scripts/ensure_cdp.sh
```

- Exit code `0` → CDP is ready, proceed with `browser_subagent`.
- Exit code `1` → CDP could not start. Report the error to the user instead of calling `browser_subagent`.

## How It Works

1. **Quick check** — pings `http://127.0.0.1:9222/json/version`. If responsive, exits immediately.
2. **Find Chromium** — searches `~/.cache/ms-playwright/chromium-*/chrome-linux/chrome` (Antigravity standard), then falls back to system-installed `chromium-browser`, `chromium`, `google-chrome`, or `google-chrome-stable`.
3. **Launch** — starts Chromium headless with `--remote-debugging-port=9222`, `--no-sandbox`, `--disable-gpu`.
4. **Wait** — polls CDP for up to 5 seconds to confirm it's ready.

## Logs

Chrome stdout/stderr are written to:
- `/tmp/chrome_stdout.log`
- `/tmp/chrome_stderr.log`

## Example Agent Workflow

```
1. User asks to browse a website
2. Agent runs:  bash .agent/skills/browser-service/scripts/ensure_cdp.sh
3. Script outputs "✅ CDP service already running" or starts it
4. Agent calls browser_subagent with the task
```
