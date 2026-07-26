# Download the desktop app

The AI Second Brain desktop app is free. No account needed to download it.

**Version 0.3.0**

| Your computer | Download |
| :--- | :--- |
| Windows | [AI Second Brain 0.3.0 installer (.exe)](https://dl.brianarfi.com/releases/0.3.0/AI%20Second%20Brain_0.3.0_x64-setup.exe) |
| macOS | [AI Second Brain 0.3.0 (.app.tar.gz)](https://dl.brianarfi.com/releases/0.3.0/AI%20Second%20Brain.app.tar.gz) |
| Linux | [AI Second Brain 0.3.0 (.AppImage)](https://dl.brianarfi.com/releases/0.3.0/AI%20Second%20Brain_0.3.0_amd64.AppImage) |

Once installed it updates itself: it checks on launch and offers the new
version, and you can also check any time from the app menu.

**Windows may warn you** that the publisher is unknown, because the installer
is not code-signed yet. Choose "More info" and then "Run anyway". **macOS** may
say the same; right-click the app and choose Open the first time.

**Linux:** make it executable before running it.

```bash
chmod +x "AI Second Brain_0.3.0_amd64.AppImage"
./"AI Second Brain_0.3.0_amd64.AppImage"
```

## What it is

A native chat window over the `claude` CLI you already have installed. It
spawns a real CLI process on your machine and drives it, so your sessions run
with whatever `CLAUDE.md` and commands live in the workspace folder you point
it at — including this harness.

On first run it walks you through picking which AI powers it. You do not need
a paid subscription: the default option installs a local proxy that uses free
AI accounts you already have. If you do subscribe to something (Claude, GLM,
Kimi), pick it there instead and the wizard connects it.

It also needs the `claude` command-line tool installed, which is the engine it
drives. The wizard checks for it and walks you through installing it if it is
missing.

## Where the source lives

The app is developed in a separate private repo. This repo holds the harness
itself — the commands, skills, and agent setup you can run directly from a
terminal, with or without the app.
