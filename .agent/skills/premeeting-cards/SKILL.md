---
name: premeeting-cards
description: Generates auto-brief "pre-meeting cards" for upcoming Work calendar events — a pure mechanical join across the calendar, people roster, MTG-* tickets, Fathom registry, and the open-items ledgers (mention ledger, decisions, commitments, waiting-on watchdog). No LLM calls.
---

# Pre-meeting Cards

Auto-brief card per upcoming meeting so You walks in knowing: who's in the room, when he last met them, what he owes them, what they owe him, any open decisions tied to them, unanswered Slack pings from them, and any related MTG-* prep ticket.

This is a **pure mechanical join** — no LLM calls, no network writes. It reads six local/connector sources and joins them by simple rules (token overlap, name/email match). All source files except the calendar connector are read-with-fallback: if a sibling ledger doesn't exist yet (or fails to parse), that section of the card just renders empty — never crashes.

## Capabilities

- `generate [--date YYYY-MM-DD]` — pulls Work calendar events for that WIB date (default: today) via `gcal_manager.py list --days-back 0 --days-forward 1 --profile work --json`, and for each event writes a card to `journal/premeeting/<date>/<HHMM>_<slug>.md` joining:
  - **Attendees** — resolved against `journal/state/people.json` (owned by the `stakeholders` component). See Gotchas below — resolution is best-effort.
  - **Last time we met** — `journal/fathom_registry.json`, participant-name overlap (preferred) or event-title token overlap (fallback), highest-scoring match with score >= 2.
  - **You owe them** — open items in `journal/state/commitments.json` where `to_slug` matches an attendee.
  - **They owe you** — open/breached items in `journal/state/waiting_on.json` where `owner_slug` matches an attendee.
  - **Open decisions** — open items in `journal/state/decisions.json` where an attendee slug is in `stakeholder_slugs`.
  - **Unanswered pings** — open items in `journal/state/slack_mention_ledger.json` authored by an attendee's `slack_id`.
  - **Related tickets** — `journal/state/tickets.json` MTG-* tickets sharing >=2 significant tokens with the event title.
  - Idempotent: rerunning `generate` for the same date clears and rewrites that date's card files and its `journal/state/premeeting.json` entry — no duplicates.
  - Prunes card date-directories older than 14 days on every run.
- `report [--date YYYY-MM-DD]` — briefing-ready markdown index of that date's cards (one line per meeting with flag counts), meant to be embedded verbatim into the morning update.

## Usage

```bash
# generate cards for today (WIB) — cron does this
python3 .agent/skills/premeeting-cards/scripts/premeeting_cards.py generate

# generate for a specific date
python3 .agent/skills/premeeting-cards/scripts/premeeting_cards.py generate --date 2026-07-14

# briefing-ready index for the morning update
python3 .agent/skills/premeeting-cards/scripts/premeeting_cards.py report
```

State: `journal/state/premeeting.json` (`dates.<YYYY-MM-DD>.cards[]` = metadata per generated card, plus `last_run`).
Cards: `journal/premeeting/<YYYY-MM-DD>/<HHMM>_<slug>.md`.

### Cron (design only — not installed by this component)

```
45 7 * * 1-5 flock -n /tmp/premeeting_cards.lock python3 <repo>/.agent/skills/premeeting-cards/scripts/premeeting_cards.py generate >> <repo>/.agent/skills/premeeting-cards/premeeting_cron.log 2>&1
```

Runs weekdays 07:45 WIB, ahead of the ~09:30 morning update, so `report` output is ready to embed. End the cron line with a `heartbeat.py --job premeeting-cards --status ok|fail` call once wired into the SOP (this component does not call heartbeat itself since generation is meant to run inside the morning-update workflow, but a standalone cron invocation should append one — see integration notes).

## Notes / Gotchas

- **Calendar attendees (gap fixed in integration stage, 2026-07-10)**: `gcal_manager.py list --json` now emits a native `attendees` field (`[{email, displayName, responseStatus}]`, empty list when the event has no invitees) — path (a) below is the live path. Attendee resolution order: (a) native `attendees` field, (b) email addresses regex-matched out of the event `description`, (c) known-person name/alias substring matches against `summary + description`. When none match, the card renders "(not resolvable from calendar payload — see SKILL.md gap note)" and every join keyed on attendees degrades to empty — expected, not a bug.
- `journal/state/people.json` is owned by the `stakeholders` component; this script only reads it (empty dict if missing).
- `tickets.json`, `slack_mention_ledger.json`, `fathom_registry.json` are read-only inputs, never modified.
- `decisions.json` / `commitments.json` / `waiting_on.json` are owned by components 1/2/3 respectively; read-with-fallback (empty dict) if not yet present or unparsable.
- No Slack/email/calendar writes of any kind. No LLM/agy-bridge calls — this is intentionally pure-mechanical per the harness-upgrade plan (cards must be cheap and always available even if agy-bridge is down).
- MTG-ticket / last-meeting matching is fuzzy (token overlap) — it degrades gracefully to "None matched" / "No prior meeting matched" rather than guessing.
