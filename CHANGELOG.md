# Changelog

All notable changes to the AI Second Brain public template. Newest first.

This template is kept in sync from a private working repo; each release is a scrubbed
snapshot with all credentials, tokens, real client names, and personal data removed.

## 2026-07-12

### Added
- **PM ledger suite + trackers** (completeness pass): `commitment-ledger` (things you owe
  others), `decision-log`, `waiting-watchdog` (things others owe you), `outcomes-loop`,
  `premeeting-cards`, `reply-queue`, `token-tracker` (usage + cost), `harness-health`
  (cron-job truthfulness checks), and `slack-tracker` (stateful mention ledger). These are
  the state machines the dashboard visualizes; their data stays local under `journal/state/`.
- **More skills**: `fathom-frame-grab`, `gemini-image`, `google-ads-connector`,
  `proactive-assistant`, `interview-assistant` (hiring toolkit: CV parser, interview plan +
  assessment templates), and `work-link-sync`.
- **Document templates** (`templates/`): meeting-minutes and PRD skeletons used by the
  meeting recorder and PRD pipeline.
- **Integration wizard** (`setup/connect.py` + `integrations.json`): interactive CLI that
  wires MCP servers into your Claude Code settings from a catalog.
- **Curated helper scripts** (`scripts/`): registry sync, Google Docs image/table helpers,
  collaborator sharing, audio transcription, weekly-report tabs, doc indexer, maintenance.

### Fixed
- `daily_update_runner.py` shipped with a syntax error (an over-eager scrub step cut a
  generated-markdown f-string in half). The scrub is now markdown-scoped and every published
  Python/JS file is syntax-checked.

- **Meeting recorder** (`meeting-recorder/`): record and transcribe meetings locally on
  your own machine, with an automatic minutes draft. Cross-platform capture (macOS
  avfoundation, Windows WASAPI, Linux PulseAudio), local GPU transcription via whisper.cpp
  with a Gemini API fallback, and an optional advanced Vexa auto-join bot. A private
  alternative or complement to a cloud recorder. Guide: `docs/MEETING_RECORDER.md`.
  Ships with `config.example.json`; runtime state and API keys stay local.
- **Visual dashboard** (`dashboard/`): a local, stdlib-only web cockpit at
  `http://localhost:3737` over your notes, calendar, projects, to-do tracker, meeting
  health, routines, and token usage. Start with `python3 dashboard/server.py`. Guide:
  `docs/DASHBOARD.md`. Panels fill in as you use the brain; a fresh clone shows an empty
  shell by design.
- **`/setup` guided onboarding command.** Type `/setup` after cloning and the AI interviews
  you about who you are, your work contexts, your track record, and your rules, then requests
  access to your tools and assembles your `CLAUDE.md` for you. Phase-based, resumable
  (`/setup resume`), and it never asks you to paste a secret into the chat. It drives the
  mechanical steps in `docs/SETUP.md` rather than duplicating them.
- **Indonesian connection kit** in `docs/workshop/`: `MULAI_DARI_SINI.md` (start here),
  `PANDUAN_KONEKSI.md` (step-by-step tool connection guide), matching PDFs, and illustrated
  screenshots (`img/`) for the Google, Slack, and Jira setup flows. Token values in every
  illustration are masked; no real credentials are shown.

### Changed
- Harness refresh synced from the working repo: morning/evening update workflows, the MOM and
  weekly-planning commands, the daily-update quality rubric, and the Google Calendar, Drive,
  and make-pdf connectors.
- Workshop deck (`docs/workshop/2026-07-11/`) expanded with the full capability showcase and
  talk track.

## 2026-07-07

### Added
- Daily-use showcase and the one-recording content pipeline in the README.

### Changed
- README polish: header, badges, learning section, and capability catalog.
- Workshop deck expanded to a full capability showcase with real pricing math.

## 2026-07-06

### Added
- **Public template v2.** Fresh history, deep-scrub sync pipeline, easy install path
  (`install.sh`), and the first Indonesian workshop kit.
- Conversational-brain quick start: a smart local companion in 15 minutes with no API keys or
  OAuth, then connect real tools when you are ready.
- Connector skills for Google Workspace (Drive, Docs, Calendar, Gmail), Slack, Fathom, Figma,
  Mixpanel, Metabase, Jira, and ClickUp, plus the multi-agent harness (commands, agents, hooks).

---

*How releases are cut: the maintainer runs the sync pipeline, which copies a whitelist of
skills and scaffolding, scrubs every text file for personal data, and fails the publish if any
leak pattern survives. Your own clone stays entirely local; nothing you add is sent anywhere.*
