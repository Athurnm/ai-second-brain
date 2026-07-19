# AI Second Brain Desktop

A free, native desktop chat UI over **your own logged-in Claude Code CLI**.
It's not a standalone chat client and it doesn't talk to any API on your
behalf — every session it opens is a real `claude` CLI process running on
your machine, with a workspace folder of markdown files as its working
directory, so whatever `CLAUDE.md` and `.claude/commands/` you have there
load exactly as they would if you ran `claude` in a terminal.

Built with Tauri v2 (Rust shell, vanilla JS frontend — no bundler, no CDN,
no embedded terminal). Ships as a native binary for Linux, macOS, and
Windows.

## Auth: subscription, not API key

This app never talks to `api.anthropic.com` directly and never asks you for
an API key or stores a credential file of its own. It authenticates purely
by spawning the `claude` CLI binary already installed and logged in on your
machine, and driving it over stdin/stdout as a subprocess (`stream-json` in,
`stream-json` out). Usage is billed the same way a terminal session would
be, against your existing Claude subscription — this app has no separate
billing relationship with Anthropic and no way to run up a bill you didn't
already agree to.

If `claude` isn't installed or isn't logged in, the app doesn't silently
fall back to some other mode. It walks you through installing and
authenticating it on first run (see **Onboarding** below), and if that ever
breaks later, it surfaces an honest error instead of degrading quietly.

## Installing the Claude Code CLI

If you don't already have it:

**macOS / Linux**
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows (PowerShell)**
```powershell
irm https://claude.ai/install.ps1 | iex
```

**Any OS, via npm**
```bash
npm install -g @anthropic-ai/claude-code
```

Then run `claude` once in a terminal and complete the login flow. The app
checks for both of these on first launch and will tell you which step is
still missing.

## Onboarding (first run)

The first time you launch the app, it checks three things in order and
walks you through whichever one isn't ready yet:

1. **Is the CLI installed?** If not, you'll see the install command for
   your OS with a copy button, and a button to re-check once you've run it.
2. **Are you logged in?** The app runs a trivial, throwaway prompt against
   the CLI to confirm. If it fails, you'll be told to run `claude` in a
   terminal once and complete login, then come back and re-check.
3. **Where's your workspace?** You'll be offered a one-click "create my
   workspace" option (see below), or you can point the app at any existing
   folder of your own.

Once a workspace is configured, launches skip straight past all of this —
onboarding only runs when there's nothing configured yet.

## Your workspace

A **workspace** is just a folder of markdown files: an `inbox/` for quick
capture, a `notes/` folder for organized knowledge, a `CLAUDE.md` that
describes how you want the assistant to behave, and a `.claude/commands/`
folder of slash commands that show up in the app's left rail.

On first run, the app offers to create one for you from a small bundled
starter template — a generic `CLAUDE.md` persona, a README, and four
example commands (`/daily-review`, `/capture-note`, `/weekly-reflect`,
`/organize-inbox`). It's markdown only: no scripts, no hooks, nothing that
runs automatically without you asking for it.

You can also point the app at **any existing folder** instead — including
a more elaborate personal harness you've built yourself, if you have one.
The app doesn't require any particular structure beyond the `.claude/commands/`
convention; an empty command list just means an empty left rail.

### Where the workspace path comes from

Resolved in this order at launch:

1. **`ASB_WORKSPACE` environment variable** — if set, must point at an
   existing directory. This is the escape hatch for pointing a build at a
   folder you manage entirely yourself; if it's set but invalid, the app
   tells you so rather than silently falling through.
2. **A small config file** the app writes for itself in its own app-data
   directory (`workspace.json`), recording the folder you picked or created
   last time.
3. **First-run onboarding**, if neither of the above is present.

Nothing about workspace resolution depends on any particular machine layout
or username — it's either an env var you set, or a path you picked through
the UI.

## Permission modes

Every session runs under one of two permission modes, chosen per-session:

- **Manual** — every file edit and tool call needs your explicit approval.
- **Accept Edits** — file edits are auto-approved; anything riskier still
  prompts.

There is no "skip every prompt" mode in this app. That capability exists in
the underlying CLI, but this app deliberately doesn't expose or enable it —
if you want that level of autonomy, run the CLI directly in a terminal
yourself.

## Running in dev

From the `desktop/` directory:

```bash
npm install   # first time only
npm run tauri dev
```

This launches the vanilla frontend (`src/`, no bundler, no CDN) and the
Rust/Tauri shell together, with hot-reload on frontend changes and a
recompile-and-relaunch on Rust changes.

## Building

```bash
npm run tauri build
```

Produces a native bundle for whatever platform you're building on
(AppImage/deb on Linux, an installer on macOS, an NSIS installer on
Windows), per `bundle.targets` in `src-tauri/tauri.conf.json`.

## How it finds the CLI binary

The CLI binary is resolved at runtime, never hardcoded to a path:

- **Windows**: checks the npm global install location under `%APPDATA%`,
  then falls back to a `PATH` scan for `claude.exe` / `claude.cmd`.
- **macOS / Linux**: scans `PATH` first, then checks common install
  locations in order (`~/.local/bin`, `~/.claude/local`, `/usr/local/bin`,
  `/opt/homebrew/bin`, `~/.npm-global/bin`).

This is the same resolution logic used by both the onboarding CLI check and
the actual session spawn, so "detected" and "used" can never disagree.

## Platform notes

- **WSL2 on Windows**: if you're running this inside WSL2 with a GUI
  environment (WSLg), windows render the same as native Linux — no
  separate X server needed. If a window fails to appear, check that WSLg is
  active on the Windows side.
- **Windows-side CLI reached from WSL**: if your `claude` binary lives on
  the Windows side and you're running the app from inside WSL, sessions
  aren't byte-identical to a native WSL terminal session — reported `cwd`
  can come back in a Windows-flavored form, and Windows-side tools (e.g.
  PowerShell) become available that a native WSL terminal wouldn't have.
  None of this affects which workspace loads or what commands are
  available; it only affects tool inventory and cosmetic path formatting.
  For exact parity with a native terminal, install a native `claude` CLI on
  whichever side you're actually working from — resolution is a plain
  fallback scan, so it picks up whichever binary is closest.

## How it inherits your workspace

Every spawned `claude` process runs with your configured workspace folder
as its working directory. That's the whole mechanism: the CLI loads that
folder's `CLAUDE.md` for operating instructions, discovers
`.claude/commands/*.md` for slash commands (surfaced in the app's left-rail
launcher), and sees whatever else you've put in that folder — the same way
a terminal session started in that directory would. Session identity
(`--session-id` / `--resume`) is tracked per chat so a conversation can be
closed and reopened without losing context, backed by the same on-disk
Claude Code session store the CLI already maintains.
