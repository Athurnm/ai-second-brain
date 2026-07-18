# Changelog

All notable changes to the AI Second Brain public template. Newest first.

This template is kept in sync from a private working repo; each release is a scrubbed
snapshot with all credentials, tokens, real client names, and personal data removed.

## 2026-07-18

### Added
- **Claude-only mode is now first-class.** The optional model bridge (`agy-bridge`)
  detects instantly when no non-Claude backend is configured and emits its standard
  Claude-fallback signal, so the whole harness runs on Claude alone at full capability.
  `run.py --doctor` explains your mode and what each optional backend needs; the
  `/setup` wizard now asks which subscriptions you have (including "none") and skips
  token setup accordingly. New optional backend: Kimi Code (Anthropic-compatible).
- **Token-efficiency loop** (`.agent/scripts/token_efficiency.py` +
  `.agent/protocols/token_efficiency.md`): weekly self-audit of tokens, cost, and
  offload share per task type from real usage logs; a `log-change` ledger records every
  optimization so the next report shows each change next to its observed effect. New
  dashboard panel (`/api/token-efficiency`) renders the trend, top hotspots, and the
  what-changed log; weekly planning picks at most one hotspot to optimize.
- **PRD publish chain**: `scripts/publish_prd.sh` (gate → convert → embed → format →
  share → restrict → verify, update-in-place, hard-fails loudly at every step) and
  `scripts/readability_gate.py` (wall-of-text lint before publish, post-publish verify,
  `--allow-public` for intentionally public docs).
- **Meeting-coverage tripwire** (`meeting-recorder/mom_reconcile.py`): enumerates the
  day from the live recorder API (never a stale local registry), tri-state exit
  (covered / gaps / cannot-verify), grace window for just-ended meetings, skips
  recordings that belong to other workspaces, designed to run on its own cron.
- **Inbox hub** (dashboard): conversations with context-aware reply drafts and an
  approve-before-send flow; drafts can never send themselves. Command-queue workers are
  draft-only by tool policy, not just by prompt.

### Security
- **Dashboard access control**: per-request client-IP allowlist (loopback + auto-detected
  WSL gateway + `DASHBOARD_ALLOWED_IPS`) enforced for every route, including the
  send-capable endpoints. 403 for everything else.
- **Headless AI runs de-fanged**: background inbox/digest/enrichment tasks now get
  narrowly scoped tool allowlists (no unscoped shell) since their prompts embed
  untrusted inbound message content; sends stay approval-gated at the server.
- **Scrub pipeline hardened**: runtime prompt snapshots (`*_prompt.txt`, which can carry
  real message text) and retired code are now blocklisted from ever syncing here.

### Fixed
- Premeeting-card enrichment always goes through the dedicated bridge script (the
  headless cron path had silently grown a divergent inline re-implementation that could
  overwrite the card audit trail).
- Meeting-note sync no longer aborts the whole batch when one note targets a path
  outside the repo; per-note failures are isolated and reported.
- Commitment-ledger duplicate adjudication (`dedupe`) now runs on cron; cron log lines
  carry timestamps; duplicate-assignment cleanup.
- Weekly-report/PRD registration exits nonzero when the local markdown update fails.
- Various small honesty fixes: publish verify no longer fails intentionally-public docs,
  mermaid-embed failures are no longer masked, stale cron times corrected in SOPs, the
  Claude binary fallback fails loudly instead of silently using a broken wrapper.

### Added (from the prior unreleased batch)
- **GA4 connector** (`.agent/skills/ga4-connector/`): read-only Google Analytics 4 CLI
  for AI agents. Actions: `snapshot` (KPIs + % deltas vs previous period + top
  pages/sources/events/countries/devices + daily trend + new-vs-returning, one call),
  `report` (custom dimensions/metrics/filters), `realtime`, `top` presets, `meta`
  (dimension/metric discovery incl. custom definitions), `accounts`, `property`.
  Two-step headless OAuth helper reuses the shared work Google OAuth client
  (`analytics.readonly` scope); token auto-refreshes, cron-safe. Set your property id
  in `config.example.json` → `config.json` or via `set-default`. Design adapted from
  the official `googleanalytics/google-analytics-mcp` tool surface and
  `Bin-Huang/google-analytics-cli` (CLI-first JSON output). SKILL.md includes an
  analysis SOP: snapshot first, drill anomalies with segmented reports, weight by
  revenue/conversion over raw traffic, every insight ends in an owned action item.
  Prereq: enable Google Analytics Data API + Admin API on the Cloud project that
  owns your OAuth client.

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
