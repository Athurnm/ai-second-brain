---
description: Meeting minutes (MOM) for Work - Fathom transcript, English, quality-gated, exported to Google Docs
argument-hint: "<meeting name/date, or paste notes>"
---

MOM workflow (Work):

1. Read `Dashboard.md` and the relevant project context (Clients/Work/...).
2. Get the raw meeting facts: spawn the `meeting-harvester` subagent with the meeting name/date (or Fathom URL / call-id). It resolves the recording via `journal/fathom_registry.json`, pulls the transcript + summary, and returns raw facts (attendees, decisions, action items, key quotes) WITHOUT synthesis, keeping this context lean for drafting. If You pastes notes instead, use those. Fallback only if the Fathom MCP is unavailable: `python3 .agent/skills/fathom-connector/scripts/fathom_client.py`.
   - **Local recordings** (registry `recording_id` starting with `local-`, `match_source: "local-recorder"`, or You points at an audio file): these come from the local note-taker (`meeting-recorder/README.md`). The transcript is already at `Clients/Work/meetings/transcripts/<file>.md` and there is usually a MOM draft `Clients/Work/meetings/MOM_<slug>_<date>.md` with header `Status: DRAFT (local pipeline, belum direview)`. Do NOT redraft from scratch: review/refine that draft, then continue from step 4. If only a raw audio file exists (not yet processed), run `python3 meeting-recorder/watcher.py --file <audio>` first.
3. Draft in ENGLISH following `templates/mom_work.md` with sections: Attendees · Agenda · Discussion · Decisions · Action Items (owner + due date per item). No em-dashes.
4. Before presenting: spawn the `draft-reviewer` subagent (type "MOM"). Fix issues, then present to You.
5. After You approves, create the Google Doc:
   `timeout 180s python3 .agent/skills/gdocs-create/gdocs_create.py create-doc --title "..." --file <path> --account work`
6. If decisions affect active tasks → update `journal/todo.md` (and flag follow-ups for `journal/master_followup_tracker.md`).
7. Confirm with the file ID + Drive link (no ID returned means the operation FAILED).

Request: $ARGUMENTS
