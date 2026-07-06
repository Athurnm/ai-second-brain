---
description: Extract durable lessons from this session into harness memory - You confirms before anything is saved
argument-hint: "[optional: the specific lesson, or 'promote' to graduate a recurring memory into CLAUDE.md]"
---

Memory dir: `~/.claude/projects/-home-you-antigravity-projects-product-second-brain/memory/`

1. Read `MEMORY.md` (the index) first so you do not duplicate existing memories.
2. Review THIS session for extractable patterns:
   - (a) corrections You made to your output or process
   - (b) stated preferences ("selalu...", "jangan...", "always", "never")
   - (c) durable project facts (IDs, owners, formats, source-of-truth decisions)
   - (d) tool workarounds that took more than one attempt
   Skip: one-off facts, anything already indexed, trivia, things derivable from the repo or git history.
3. For each candidate, draft a memory file in the EXISTING convention:
   - filename prefix by type: `feedback_*.md` (corrections/preferences), `project_*.md` (client/project facts), `user_*.md` (You's style), `reference_*.md` (external docs/IDs)
   - frontmatter: `name`, `description`, `metadata.type`
   - body: 3-10 lines - the rule/fact, when it applies, evidence (quote what You said + absolute date). For feedback: include **Why:** and **How to apply:** lines.
4. Show the drafts to You. WAIT for explicit confirmation. Never save unconfirmed.
5. On approval: write the file(s) AND add one index line each to `MEMORY.md` (same format as existing entries).
6. **Promote mode** (when $ARGUMENTS says "promote" or a feedback memory has been re-confirmed across 3+ sessions): propose the exact CLAUDE.md or `.claude/commands/*` edit that makes it a standing rule, show the diff, apply only on approval, then mark the memory file "promoted to <file> on <date>" instead of deleting it.

$ARGUMENTS
