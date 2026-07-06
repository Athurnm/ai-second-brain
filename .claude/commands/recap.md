---
description: "Previously on... - recap the last 1-2 Claude Code sessions: tasks, documents produced, decisions, unfinished work"
argument-hint: "[optional: how many sessions back]"
---

Session recap (opt-in continuity - costs tokens only when you ask for it):

1. List transcript files in `~/.claude/projects/-home-you-antigravity-projects-product-second-brain/` sorted by mtime (`ls -t *.jsonl | head -5`). Exclude the CURRENT session (newest file is usually this one - check size/mtime).
2. Read the 1-2 most recent PREVIOUS session transcripts. They are JSONL - extract from user/assistant messages: tasks You requested, documents produced (with Drive links/IDs), decisions made, and anything left half-finished.
3. Cross-check `Dashboard.md` daily sections and `journal/todo.md` so the recap reflects current state, not stale plans.
4. Output a "previously on" brief, max 10 lines: what was done, what was decided, what is still open. Lead with open/unfinished items.

$ARGUMENTS
