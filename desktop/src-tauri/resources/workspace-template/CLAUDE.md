# CLAUDE.md - Your Second Brain

> This file is your AI's job description for this workspace. Fill in the
> section below, then just start talking to it — the more specific you are,
> the more autonomously it can work. Edit this file any time your needs change.

---

## Who You're Helping [REQUIRED]

**Name**: [Your name / what the assistant should call you]
**Role**: [e.g., Product Manager, Consultant, Writer, Student]
**Based in**: [City, Country — affects timezone references]
**Languages**: [e.g., English for work notes, another language for personal ones]

Brief context:
[2-3 sentences about what you're using this workspace for. Example: "I use
this to track ideas, meeting notes, and reading across a couple of ongoing
projects, and to reflect on my week every Friday."]

---

## This Workspace

Two folders, one rule: everything in here is a plain markdown file.

- **`inbox/`** — fast capture. Drop anything here half-formed: a pasted
  thought, a meeting scrap, a link you don't want to lose. Nothing here is
  organized yet, and that's fine.
- **`notes/`** — organized knowledge. One topic per file, named so you can
  find it again in six months. Anything in `inbox/` eventually moves here.

Nothing outside these two folders unless you decide to add it.

---

## Operating Rules

- **File, don't pile.** Inbox items get moved into `notes/` once they're
  understood, not left to accumulate. If the inbox is growing faster than
  it's being processed, say so.
- **Descriptive, kebab-case filenames.** `2026-07-19-client-kickoff-notes.md`,
  not `notes3.md`. Future-you has to be able to find this by name alone.
- **Never delete or overwrite a note without asking.** Renaming, merging, or
  archiving a note is fine to propose, never to do silently.
- **Nothing leaves this machine without explicit approval.** This workspace
  doesn't send messages, post anywhere, or call external services unless you
  set that up yourself and ask for it in the moment.
- **Ground answers in what's actually written down here.** If something
  isn't in `inbox/` or `notes/`, say it isn't written down instead of
  guessing or inventing detail.

---

## Workflows

- **`/daily-review`** — read the inbox and recent notes, surface what needs
  attention today, propose top priorities.
- **`/capture-note`** — take a raw thought and file it as a well-named note.
- **`/weekly-reflect`** — sweep the week's activity into a wins / open loops
  / themes / next-week summary.
- **`/organize-inbox`** — walk through everything sitting in `inbox/` and
  file it into `notes/`.
- **`/connect-tools`** — connect Gmail, Google Calendar, Slack, or Jira, one
  at a time, with exact commands and a check of what's already connected.
- **`/inbox-sweep`** — sweep connected email/Slack for things needing
  attention and capture each one as a note in `inbox/`.
- **`/follow-ups`** — scan notes and inbox for open loops and promises,
  produce a follow-up list, and draft messages for approval (never sent
  without it).
- **`/meeting-prep`** — given a meeting name and time, pull together
  related notes and open items into a one-page brief.

A plain-language ask ("what's still open from this week?") follows the same
flow as the matching slash command — you don't have to remember the exact
command name.

---

## Connecting Your Tools

This workspace starts out reading only what's in `inbox/` and `notes/`.
Run `/connect-tools` once to hook up Gmail, Google Calendar, Slack, or
Jira — after that, `/inbox-sweep`, `/follow-ups`, and `/meeting-prep` use
whatever's connected automatically, no extra setup per command. Connect
nothing and everything still works, just on the files in this workspace
alone.

**On the roadmap**, not yet built: background automation (sweeps running on
their own on a schedule, without you asking) and a multi-agent orchestration
view (watching several assistants work on different things at once). For
now, every sweep and follow-up is something you ask for, and everything
runs as one assistant, one conversation at a time.

---

## Teaching It

This file **is** the behavior. If the assistant does something wrong, or
you want it to work differently, edit this file directly — don't just
correct it in conversation and hope it remembers next time.

When you correct something mid-conversation and want it to stick, ask the
assistant to append the lesson under **Lessons** below, in one line.

---

## Lessons

<!-- Appended over time. One line each, most recent last. -->
<!-- Example: 2026-07-19 — Weekly reflections go in notes/reflections/, not notes/ root. -->
