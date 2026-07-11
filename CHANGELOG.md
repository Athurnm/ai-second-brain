# Changelog

All notable changes to the AI Second Brain public template. Newest first.

This template is kept in sync from a private working repo; each release is a scrubbed
snapshot with all credentials, tokens, real client names, and personal data removed.

## 2026-07-12

### Added
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
