---
name: commitment-ledger
description: Outbound commitments ledger - things You said he'd do (from Fathom meeting action items, sent Slack messages, and local meeting transcripts/MOM drafts), tracked from "I'll ..." until actually delivered or dropped. Not for things You is waiting on others for (see waiting-watchdog).
---

## Capabilities

- Mechanically pull Fathom action items assigned to You from recently-synced meetings
  (`journal/fathom_registry.json`) into high-confidence commitment items - no LLM needed.
- Sweep You's own sent Slack messages for commitment language ("I'll send...", "will follow
  up...") into a cheap-filtered candidate queue, then use GLM (via agy-bridge) to extract
  structured commitments (recipient, due date) from that queue.
- Mechanically capture You's spoken "this is my action item" cues from local meeting
  transcripts, plus MOM "Action Items" rows that name You, into high-confidence commitment
  items - no LLM needed (see **Local meeting-cue capture** below for the exact trigger phrases).
- Mechanically auto-close a commitment when You later posts a completion word or a Drive/Docs
  link in the same thread.
- Emit a briefing-ready markdown report (overdue open first, then open by due date, then
  no-due, closed items only with `--all`).

## Local meeting-cue capture

Say ANY of these mid-meeting (Bahasa or English, case-insensitive) and the local recorder's
transcript/MOM draft will mechanically pick it up on the next `sweep` - no LLM, no manual entry:

- `ini action item gw: <what you'll do>`
- `action item gw <what you'll do>` / `action item gue ...` / `action item saya ...`
- `note action item: <what you'll do>` / `note, action item ...`
- `my action item: <what you'll do>`

Everything after the cue phrase, to the end of that line, becomes the commitment text (a
leading `:` or `-` is stripped). Captures under 4 words are dropped as noise (e.g. just saying
the cue phrase with nothing after it, or a transcription artifact). The recipient (`to`) is
always left blank - a spoken cue names an action, not a recipient - so these render as `->`-less
items in `report`; add one later with the ledger's own `close --note` or by editing `to` via a
future manual pass if needed.

Separately, ANY row inside a MOM's "Action Items" section (table row, checkbox bullet, plain
line - whatever format that MOM uses) that contains the literal word "You" is also captured.
**Caveat:** this is a blunt word match, not owner-column parsing - parsing which table column
is "Owner" per MOM format would need real understanding, which the mechanical/no-LLM
constraint rules out. So a row like `| Rani | Share X with You and Javi | ... |` gets
captured even though You is only the recipient named in that row, not the owner. Skim these
before turning one into a ticket.

## Usage

```bash
# cron default: Fathom action items + Slack candidate collection + mechanical auto-close
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py sweep

# GLM extraction pass over queued Slack candidates -> structured medium-confidence items
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py extract

# manual capture (e.g. a commitment made verbally, or spotted during /mom)
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py add \
  --text "Send updated OTO PRD to Teammate" --to "Teammate Sanka" --due 2026-07-14 \
  --project "OTO Logistics" --source "https://fathom.video/calls/..."

# close/drop manually
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py close COM-0001 --note "sent via Slack"
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py drop COM-0002 --note "no longer relevant"

# briefing-ready markdown (embed verbatim in morning/evening update)
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py report
python3 .agent/skills/commitment-ledger/scripts/commitment_ledger.py report --all   # include closed
```

## Notes

- State file: `journal/state/commitments.json` - `{next_seq, items: {COM-NNNN: {...}},
  slack_search_watermark, local_watermark, processed_fathom_ids, processed_sources,
  pending_candidates, user_names, last_sweep}`. `local_watermark` (epoch float) is the local
  meeting-cue source's watermark, parallel to `slack_search_watermark` - the newest mtime
  (across all scanned files) seen by the most recent `sweep`.
- IDs are human-typeable and monotonic: `COM-0001`, `COM-0002`, ...
- Item schema: `{id, text, to, to_slug, channel, channel_name, thread_ts, permalink, due,
  project, source: {type: fathom|slack|manual|meeting-local, ref}, status: open|done|dropped,
  confidence: high|medium, first_seen, closed_at, closed_by, priority, notes[]}`.
  `to_slug` = `slugify(to)` (lowercase-dash) so this ledger can cross-reference
  `journal/state/people.json` (owned by the `stakeholders` component) by slug without a
  hard dependency - resolve by slug, fall back to the free-text `to` name.
- **Fathom path gotcha (confirmed 2026-07-10):** `fathom_client.py --action get --id
  <recording_id>` 404s for every recording_id currently in `fathom_registry.json` on this
  deployment (tried 2 recent IDs, both 404 on both `/meetings/` and `/recordings/`
  endpoints). `--action list --full` DOES return `action_items[]` per meeting (confirmed
  shape: `{description, user_generated, completed, recording_timestamp,
  recording_playback_url, assignee: {name, email, team}}`). `sweep_fathom()` therefore uses
  `list --full` (bounded `--limit`, default 20) and cross-references against
  `fathom_registry.json` to identify which fetched meetings are new, rather than fetching
  per-recording via `get`. You-assignee match: `assignee.email == you@example.com` OR
  assignee name contains `"brian arfi"`/`"brian faridhi"` (case-insensitive - Fathom's
  transcript speaker-matching produces inconsistent casing/fullname variants, e.g. "brian
  arfi" vs "Your Name").
- Slack sent-message sweep: `search.messages from:<@<SLACK_ID>>` (You's verified Slack
  ID), paginated (bounded to 5 pages/sweep), cheap regex pre-filter (`COMMIT_RE`) so
  `pending_candidates` doesn't fill with unrelated sent messages. First run looks back 3
  days. Extraction into real ledger items is NOT done during `sweep` - only `extract`
  (GLM via agy-bridge) turns a candidate into a `COM-*` item, confidence `medium`.
  Fathom-sourced items are confidence `high` (mechanical, no LLM).
- Local meeting-cue sweep scans (verified against `meeting-recorder/watcher.py` constants,
  do not guess): `Clients/Work/meetings/transcripts/*.md` (raw local/vexa transcripts),
  `Clients/Work/meetings/*.md` (MOM drafts - same dir the watcher + `/mom` write to), and
  `Clients/*/meetings/*.md` (any other client's meeting notes, present or future). `.md` only
  - the `.txt` whisper sidecars in the transcripts dir are not scanned. Only files with
  `mtime` newer than `local_watermark` are read each sweep (first run: 3-day lookback, same
  as Fathom/Slack). Two independent captures per file: (1) `CUE_RE` finds You's spoken
  cues anywhere in the text; (2) `extract_mom_action_lines()` finds the "Action Items"
  heading (heading-level aware, so a nested subheading doesn't end the section early) and
  scans its rows for the literal word "You". Dedupe key: `local:<repo-relative
  path>:<sha1(raw line)[:12]>` in `processed_sources` - content-hashed per line, so
  re-touching a file (e.g. a later hand-edit of a MOM) only re-captures genuinely new/changed
  lines, not ones already ingested. Confidence `high` (mechanical, no LLM, same tier as
  Fathom). `permalink` and `source.ref` are both set to the repo-relative path so `report`
  renders a clickable local link (`[ref](Clients/Work/meetings/...)`), consistent with how
  You opens local files from this harness.
- agy-bridge contract: rc 0 -> stdout has JSON lines to parse. rc 3 -> `FALLBACK_TO_CLAUDE`
  marker printed, `pending_candidates` left untouched, exit 0 (NOT a failure - Claude
  should run `extract`'s judgment manually in that case, same pattern as
  `mention_ledger.py cmd_classify`).
- Auto-close is mechanical only: an open item with a `channel` + `thread_ts` gets closed
  (`closed_by: auto_thread`) when You's own later message in that thread contains a
  completion word (done/sent/shared/delivered/...) or a `docs.google.com`/`drive.google.com`
  link. Fathom-sourced items have no `thread_ts` (the API gives no recipient thread) so they
  can only be closed via `close`/`drop`.
- Retention: `done`/`dropped` items pruned after 14 days (`CLOSED_RETENTION_DAYS`). Stale
  unconsumed `pending_candidates` (>14d, never `extract`-ed) are also dropped as likely
  superseded.
- `report` ordering: (1) overdue open (`due` < today WIB), (2) open by due date ascending
  (no-due items after all dated ones), (3) with `--all`, closed items last by close time.
- This skill never writes to `tickets.json`, the mention ledger, `people.json`, or any
  other component's state - read-only relationship elsewhere is by slug/id cross-reference
  only (see `to_slug`).
- Cron (design only - NOT installed by this skill): `10 9,14,20 * * * flock -n
  /tmp/commitment_ledger.lock python3 <abs>/commitment_ledger.py sweep >>
  .agent/skills/commitment-ledger/commitment_ledger_cron.log 2>&1` then a second `extract`
  invocation in the same flock line (`sweep && extract`), off the `:00`/`:30` marks so it
  doesn't collide with `mention_ledger`'s `*/30` cron.
- Heartbeat: `sweep` calls `.agent/scripts/heartbeat.py --job commitment-ledger --status
  ok|fail --summary "<sweep summary>"` itself at the end of the run (ok on success, fail +
  re-raise on exception) so the Routines panel at localhost:3737 sees it with no wrapper
  needed. `extract` does not heartbeat separately (it's chained after `sweep` in the same
  cron line; a failed `extract` just leaves `pending_candidates` untouched for next run).
