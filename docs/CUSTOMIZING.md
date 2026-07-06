# Customizing Your CLAUDE.md

`CLAUDE.md` is the single most important file in this repo. It's your AI's operating manual — the difference between an AI that works generically and one that operates like a trained assistant who knows your work intimately.

This guide explains what each section does and how to write yours well.

---

## The Mental Model

Think of `CLAUDE.md` as a combination of:

- **Job description** — what your AI is responsible for
- **Playbook** — step-by-step for every recurring task
- **House rules** — what it can do autonomously vs. what needs your sign-off
- **Context brief** — who you are, what you work on, who the key people are

The AI reads this file at the start of every session. The more specific it is, the less you have to re-explain every time.

---

## Anatomy of CLAUDE.md

### 1. Who You're Helping

The first thing the AI needs to know is who it's working with.

**What to write:**

```markdown
## Who You're Helping

**Name**: Sarah
**Role**: Product Manager
**Based in**: Jakarta, Indonesia
**Languages**: English for client work, Indonesian for personal content

I manage product for two enterprise SaaS clients simultaneously.
I run 2-week sprints, write PRDs, attend 6–10 meetings per week,
and send a weekly report to each client's stakeholders.
```

**Why it matters:** The AI uses this to calibrate tone, language, and the level of detail it provides. A senior PM needs different responses than someone new to product.

---

### 2. Work Contexts

List every client, team, or project the AI will encounter.

**What to write:**

```markdown
## Work Contexts

Context 1: Acme Corp
  Products: B2B billing dashboard, admin portal
  Team: 4 engineers, 1 designer, 1 QA
  Stakeholders: Budi (CTO), Rina (COO)
  Language for docs: English
  Slack channels: #acme-product, #acme-eng
  Drive folder: "Acme Product Docs"

Context 2: Beta Startup
  Products: Mobile consumer app (iOS/Android)
  Team: 2 engineers, 1 designer
  Stakeholders: Founder (James)
  Language for docs: English
  Slack channels: #product, #general
```

**Why it matters:** Without this, the AI can't distinguish between "the dashboard" at Acme and "the dashboard" at Beta. It will ask you to clarify every time — or worse, mix them up.

---

### 3. Workflow Checklists

This is where most of the value lives. Define the exact steps for every recurring task.

**The key insight:** Don't describe the output — describe the process. The AI will follow it exactly, every time.

**Example — PRD workflow:**

```markdown
### PRD / Product Spec
1. Read Dashboard.md + journal/todo.md for active context
2. Search Drive for existing doc by title — if found, note revision
3. Draft in English, show as markdown for review
4. Wait for explicit approval before creating Google Doc
5. Create Google Doc: gdocs-create --account work
6. Register in master product tracker
```

**Example — Slack message workflow:**

```markdown
### Slack Message
1. Draft the full message
2. Show draft + target channel + reason for sending
3. Wait for explicit "send" — never send speculatively
4. Send via MCP Slack tools
```

**Tips:**
- Be specific about where content goes (which Drive folder, which tracker)
- Explicitly state approval gates ("wait for approval before X")
- Mention the tool to use at each step

---

### 4. Document Rules

Define language, format, and naming conventions per context.

```markdown
## Document Rules

Language:
- Acme Corp docs: English
- Beta Startup docs: English
- Personal LinkedIn posts: Indonesian

Format:
- Draft/review: markdown (I comment inline before approving)
- Final: clean, ready to export to Google Docs

Naming: YYYY-MM-DD_ClientName_DocType_Title
Example: 2026-05-17_Acme_PRD_BillingRedesign
```

---

### 5. Tool Routing

Tell the AI which tool to use for which operation. This prevents it from guessing.

```markdown
## Tool Routing

Google Workspace:
- Search/read files: MCP tools (mcp__claude_ai_Google_Drive__search_files)
- Create Google Doc: gdocs-create skill
- Update existing doc: Python update --id FILE_ID (never change title)

Slack:
- Read: slack-connector
- Write: draft first, show me, wait for approval

Meeting transcripts:
- First check Fathom connector
- If not found, ask me to provide notes
```

---

### 6. Approval Gates

The most important section for safety. Define what the AI must never do without asking first.

**Non-negotiables to include:**

```markdown
## Approval Gates

Never without explicit approval:
- Send any Slack message or DM
- Send any email
- Post to any social platform
- Delete any file (local or Drive)
- Push to any git remote
- Create calendar events
- Make purchases or API calls with cost implications

Can do autonomously:
- Draft and revise documents
- Search and read Drive, Slack, calendar
- Create local files
- Run read-only API queries
- Organize files into folders
```

---

### 7. Clients / Projects Detail

A per-client context block the AI references when working on that client's tasks.

```markdown
### Acme Corp

Status: Active
Key products: Billing dashboard, admin portal
My role: Embedded PM (3 days/week)
Drive folder: "Acme / Product"
Slack: #acme-product, #acme-eng
Key contacts:
  - Budi (CTO) — technical decisions
  - Rina (COO) — business priorities
  - Dev team lead: Marcus
Current focus: Q3 billing redesign
Known blockers: Waiting on legal approval for PCI scope
```

---

## The Minimal Viable CLAUDE.md

If you want to get started quickly, these 4 sections are enough:

1. **Who You're Helping** — name, role, 2 sentences of context
2. **Work Contexts** — list your clients/projects
3. **Approval Gates** — what needs sign-off
4. **One workflow checklist** — for your most common task

You can add the rest as you use it and notice gaps.

---

## Role-Based Examples

### Product Manager

Focus areas: PRD workflow, sprint planning, meeting notes, stakeholder updates.

Key things to define:
- Where PRDs live in Drive
- How to name documents
- Which Slack channels to monitor per client
- Who reviews your drafts before they're sent

### Consultant / Advisor

Focus areas: Client deliverables, proposals, meeting notes, engagement tracking.

Key things to define:
- One context block per engagement
- Deliverable format per client (some want slides, some want docs)
- Billing/time tracking if relevant
- Approval gate for anything sent to client

### Executive / Operator

Focus areas: Daily briefings, decision tracking, team communication, weekly reports.

Key things to define:
- Which calendar to pull (work vs personal)
- What "daily briefing" should include (meetings, priorities, blockers)
- Who on your team owns what
- Which Slack channels carry signal vs noise

---

## How to Iterate

Start with a minimal `CLAUDE.md`. Every time the AI does something wrong or you have to re-explain something, add a rule.

Common things people add over time:
- "Don't summarize what you just did at the end of every response"
- "When writing PRDs, always include a 'Non-goals' section"
- "Flag if a deliverable is overdue before starting new work"
- "Use bullet points, not numbered lists, for meeting notes"
- "Always check Drive for an existing doc before creating a new one"

Your `CLAUDE.md` becomes a living document. The more sessions you run, the sharper it gets.

---

## Common Mistakes

**Too generic:**
```markdown
# Bad
Be helpful and professional.

# Good
When drafting PRDs, follow the Work Standard Template:
Background → Goals → Non-Goals → User Stories → Success Metrics → Open Questions
```

**Missing approval gates:**
Without explicit approval gates, the AI may send messages or modify files it shouldn't. Always define what's off-limits.

**Forgetting language rules:**
If you work across languages, be explicit per context. "Write all Acme docs in English, all personal content in Indonesian" is much clearer than assuming the AI will infer it.

**No tool routing:**
Without tool routing, the AI picks tools based on what's available. It may create a Google Doc via MCP (which produces raw text) instead of `gdocs-create` (which produces a properly formatted editable doc). Be explicit.
