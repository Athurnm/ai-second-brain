# Visual Dashboard

A local web cockpit for your second brain. It runs on your machine at
`http://localhost:3737` and gives you a glanceable view over your `Dashboard.md`, your
calendar, your project docs, your to-do tracker, meeting health, and more, with a few
things you can act on directly (edit a ticket, trigger a routine, kick off an AI task).

It lives in `dashboard/` and is pure Python standard library (no pip install, no build
step), so it runs anywhere you have `python3`.

- [Start it](#start-it)
- [What you see, and what fills in over time](#what-you-see-and-what-fills-in-over-time)
- [The tabs](#the-tabs)
- [Where each panel gets its data](#where-each-panel-gets-its-data)
- [Keeping it running](#keeping-it-running)
- [Security](#security)

---

## Start it

```bash
python3 dashboard/server.py
```

Then open **http://localhost:3737** in your browser. To use a different port:

```bash
DASHBOARD_PORT=4000 python3 dashboard/server.py
```

The server serves the UI from `dashboard/public/` and exposes a small JSON API the
page polls. It is stateless: it reads your repo files live on each request, so it always
reflects the current state on disk.

---

## What you see, and what fills in over time

The dashboard is a **window onto your data, not a database of its own.** On a fresh clone
it is mostly an empty shell, and that is expected. Panels light up as you actually use the
brain:

- The **overview and notes** panel reads `Dashboard.md`, so it works as soon as you have one.
- The **calendar** panel works once you connect a calendar (see `docs/SETUP.md`).
- The **projects** panel lists the markdown docs under your `Clients/` folder, so it fills
  as you create PRDs, MOMs, and strategy docs.
- The **tracker, ledgers, meeting-health, routines, and AI-task** panels read state files
  under `journal/` that the matching skills and commands build up as you work. Until that
  state exists, those panels are empty or show "no data." That is normal, not a bug.

In other words: connect your tools, run your daily and weekly workflows, and the cockpit
gets richer on its own.

---

## The tabs

The exact panels evolve, but the shape is:

- **Work / Projects**: your active projects, the to-do tracker (create, edit, comment on
  tickets right in the page), momentum charts, and follow-ups.
- **Meetings**: recent meetings, transcripts and MOMs, and the health of your meeting
  recorder (see `docs/MEETING_RECORDER.md`).
- **System / Health**: output and pipeline metrics, scheduled-routine status (so a silent
  overnight failure is visible), token-usage and cost tracking, and a map of your harness.

Many list panels open a detail drawer when you click a row.

---

## Where each panel gets its data

| Panel | Reads from | Needs |
|---|---|---|
| Overview / notes | `Dashboard.md` | nothing (ships as a stub) |
| Calendar | your calendar connector | calendar set up in `docs/SETUP.md` |
| Projects | `Clients/<context>/**/*.md` | your own project docs |
| Tracker | `journal/state/tickets.json` | created as you add tickets |
| Ledgers | `journal/state/*.json` (commitments, waiting-on, decisions, outcomes) | the ledger skills/commands |
| Meeting health | `meeting-recorder/` + `journal/fathom_registry.json` | the meeting recorder |
| Routines | `dashboard-data/agent_heartbeat.jsonl` | your scheduled jobs writing heartbeats |
| Token usage | `journal/state/token_usage.json` | the token tracker |

If a source file does not exist yet, the panel degrades to empty rather than erroring the page.

---

## Keeping it running

For everyday use, just start it when you want it. If you want it always on, run it under
your OS process manager or a simple cron keepalive that restarts it if the port is not
listening. Because it is stdlib-only Python, the same `python3 dashboard/server.py` works
on macOS, Linux, and WSL.

---

## Security

- **It binds to localhost.** Do not expose port 3737 to your network. There is no
  authentication: anyone who can reach the port can read your data and use the action
  buttons.
- **It can run local commands on your behalf.** The action endpoints edit your local
  tracker files, and the optional AI-task and run-job buttons execute local scripts and can
  invoke the headless `claude` CLI. Those are conveniences for a single-user, on-your-own-machine
  setup. Run the dashboard only on a machine you control, and review what a button does before
  clicking it.
- **No data leaves your machine** from the dashboard itself, beyond the API calls your
  connectors already make (e.g. fetching your calendar).
