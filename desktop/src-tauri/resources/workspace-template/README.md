# Your Workspace

This folder was created by AI Second Brain Desktop the first time you ran it.
It's just plain files — nothing here is proprietary or locked to the app.

## Folder map

```
CLAUDE.md          How you've told the assistant to behave. Edit it any time.
README.md          This file.
inbox/              Fast, unsorted capture.
notes/              Organized knowledge, one topic per file.
.claude/commands/   Slash commands the app's left rail reads from.
```

## How commands show up in the app

The app's left rail lists every `.md` file under `.claude/commands/` in this
workspace as a runnable command. Each file needs a short frontmatter block at
the top:

```markdown
---
description: One line describing what this command does
argument-hint: optional hint text shown next to the input
---

The actual instructions the assistant follows when you run this command.
```

The `description` is what shows up in the app; `argument-hint` is optional.

## Adding your own command

Copy an existing file in `.claude/commands/`, rename it, and edit the
frontmatter and body. It appears in the app the next time commands are
loaded — no restart needed, no build step.

## Connecting your tools

Run `/connect-tools` once to hook up Gmail, Google Calendar, Slack, or
Jira. Once something is connected, `/inbox-sweep`, `/follow-ups`, and
`/meeting-prep` use it automatically — you don't reconnect per command.
Nothing is connected by default, and nothing leaves this machine without
you setting it up and approving it in the moment.

**Roadmap:** background automation (sweeps that run on a schedule instead
of only when asked) and a multi-agent orchestration view (several
assistants working in parallel, visible in one place) are both planned but
not built yet. Today, every sweep is something you ask for, one assistant
at a time.

## It's just files

This workspace is portable. You can `git init` it, sync it, back it up, or
open and edit any file in it with a plain text editor outside the app — the
app is a window onto these files, not a database that owns them.
