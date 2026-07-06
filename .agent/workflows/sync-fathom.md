---
description: Trigger a manual sync of Fathom recordings and generate meeting notes
---
// turbo-all

# Sync Fathom Workflow

Use this workflow to manually fetch recent Fathom recordings and auto-generate structured local meeting notes.

## 1. Run Sync Script

```bash
// turbo
python3 scripts/fathom_to_notes.py
```

The script will:
1. Fetch the last 20 Fathom recordings (with transcript, summary, action items)
2. Match each recording to a Google Calendar event (±30 min window)
3. Classify by client/project using calendar attendees or Fathom invitee emails as fallback
4. Write one `.md` file per meeting to the correct `Clients/[Client]/[Project]/meetings/` folder
5. Skip files that already exist (idempotent — safe to re-run)
6. Save raw results to `_temp/fathom_sync_results.json`

## 2. Output Locations

| Client | Project | Path |
| :--- | :--- | :--- |
| Work | B2C SuperApp | `Clients/Work/B2C SuperApp/meetings/` |
| Work | Seller Portal | `Clients/Work/Seller Portal/meetings/` |
| Work | Marketplace | `Clients/Work/Marketplace/meetings/` |
| Work | General | `Clients/Work/meetings/` |
| ClientB | General | `Clients/ClientB/meetings/` (gitignored by design — local only) |
| You | General | You repo: WSL `~/antigravity-projects/You/meetings/`, macOS `~/You/You/meetings/` |
| You | Taaruf Lalu Nikah | You repo: `<You repo>/Taaruf Lalu Nikah/meetings/` |

**Anti-misfiling rule (2026-07-04):** "Impromptu Google Meet Meeting" recordings must be classified by CONTENT (participants + client keywords: Work/ExampleProgram/Teammate/Teammate = Work; ClientB/ClientB = ClientB), never defaulted to You. On 2026-07-04, 13 Work/ClientB meetings were found mis-filed under You and relocated. When unsure → `Clients/Work/meetings/` if any Work signal, else leave in `_temp/` for manual triage.

## 3. Filename Format

`YYYY-MM-DD_HHMM_Meeting_Title_Slug.md` (WIB time, 24h)

## 4. This runs automatically

The evening daily update runner calls this script at Step 8 (weekdays only). Manual trigger is only needed to catch up on missed days or test.

---

## 5. Fathom Meeting Registry (lookup index)

Separate from the per-meeting notes above, `scripts/fathom_registry_sync.py` maintains a **cumulative master list** of every Fathom recording, so a meeting can be resolved to its Fathom link long after it leaves the API window.

```bash
// turbo
python3 scripts/fathom_registry_sync.py            # incremental (daily; stops at known recordings)
python3 scripts/fathom_registry_sync.py --backfill # walk ALL Fathom history via next_cursor (rebuild)
python3 scripts/fathom_registry_sync.py --rebuild-md # regenerate the .md from existing json only
```

What it does:
1. Paginates Fathom via `next_cursor` (the API caps ~10/page but paginates fully).
2. For each recording, pulls Work + personal Google Calendar events in a ±30 min window and matches by **time + attendee-email overlap**.
3. Assigns confidence: 🟢 time + shared attendee · 🟡 time only · ⚪ no calendar event (truly impromptu).
4. Upserts (keyed by `recording_id`) into:
   - `journal/fathom_registry.json` — source of truth (never drops history)
   - `Fathom_Registry.md` — human index, newest-first

**Lookup rule**: when You names a meeting + date, grep `journal/fathom_registry.json` (by `date_wib` / `matched_meeting` / `client`) to find the right `fathom_url` before doing anything else. The registry runs automatically right after Step 8 in the evening runner.
