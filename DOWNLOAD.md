# Download the desktop app

The AI Second Brain desktop app is free. Grab an installer from the
[Releases page](https://github.com/BrianArfi/ai-second-brain/releases) —
Windows (`.exe`/`.msi`), macOS (`.dmg`), and Linux (`.deb`/`.AppImage`).

Once installed it updates itself: it checks on launch and offers the new
version, and you can also check any time from the app menu.

## What it is

A native chat window over the `claude` CLI you already have installed. It
spawns a real CLI process on your machine and drives it, so your sessions run
with whatever `CLAUDE.md` and commands live in the workspace folder you point
it at — including this harness.

On first run it walks you through picking which AI powers it. You do not need
a paid subscription: the default option installs a local proxy that uses free
AI accounts you already have. If you do subscribe to something (Claude, GLM,
Kimi), pick it there instead and the wizard connects it.

## Where the source lives

The app is developed in a separate private repo. This repo holds the harness
itself — the commands, skills, and agent setup you can run directly from a
terminal, with or without the app.
