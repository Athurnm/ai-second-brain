<div align="center">

# 🧠 AI Second Brain

**An AI partner that runs inside your editor, knows how you work, learns as you correct it, and does the recurring work for you.**

So you spend your week deciding instead of compiling.

![Built for Claude Code](https://img.shields.io/badge/built%20for-Claude%20Code-E8A33D?style=flat-square)
![Runs on macOS · WSL · Windows](https://img.shields.io/badge/runs%20on-macOS%20·%20WSL%20·%20Windows-3A4557?style=flat-square)
![First run 15 minutes](https://img.shields.io/badge/first%20run-15%20minutes-6FB5AC?style=flat-square)
![Any agentic harness](https://img.shields.io/badge/core-harness%20agnostic-97A0B0?style=flat-square)

[What it does](#what-it-does-every-day) · [It learns you](#it-learns-you) · [Capabilities](#capability-catalog) · [How it stays cheap](#multi-agent-setup-faster-and-cheaper) · [Get started](#getting-started)

</div>

---

## Monday, 9:00 a.m.

Last week happened across eight meetings, three Slack channels, a dozen Google Docs, and a to-do list you half-updated. The weekly report is due before standup.

So you open ten tabs and start the archaeology. Scrub each transcript. Remember what got decided. Copy the parts that matter, paste them somewhere, slowly shape a narrative. Ninety minutes later you have a report and no morning left.

Now the same Monday, with a second brain:

```
You:  "Write this week's progress report."
```

It already knows your meetings happened. It reads all eight transcripts at once, pulls the decisions and the action items, weighs what actually mattered against your to-do list, drafts the report in your format and language, runs a quality check, and hands you a real Google Doc to review.

You spend your ninety minutes deciding what to do about what it found.

That is the whole idea. **Take the overhead off your desk. Give the thinking back to you.**

```
   YOUR WEEK, BEFORE                         YOUR WEEK, WITH A SECOND BRAIN
   ┌─────────────────────────────┐          ┌─────────────────────────────┐
   │ ███████████████ admin   70% │          │ █████ admin             30% │
   │ ██████ real work        30% │          │ ███████████ real work   70% │
   └─────────────────────────────┘          └─────────────────────────────┘
     compiling · formatting ·                  deciding · designing ·
     chasing · copy-pasting                    creating · thinking
```

---

## Why It Is Different

Not a chat box. A system that carries your context, reaches your tools, and gets sharper the longer you use it.

- 🧠 **Knows you.** One file describes who you are, your projects, your rules, your languages. It reads that before every task.
- 🖐️ **Holds your tools.** Google Docs, Drive, Slack, Calendar, meeting recorders, Jira, analytics, image and video. It acts in the real services, not just talks about them.
- 📚 **Learns and remembers.** Correct it once and it keeps the lesson across every future session. It does not start from zero each morning.
- 🤖 **Runs a team, not a chat.** Big jobs fan out to a fleet of cheap fast workers in parallel, then one flagship model synthesizes. Faster and far cheaper.
- 🔒 **Guardrails that hold.** Nothing is sent, posted, or deleted without your explicit approval. Credentials never leave your machine.
- ⚡ **Fifteen minutes to first value.** A conversational brain with no API keys or OAuth, then connect real tools when you are ready.

---

## The Gap This Closes: AI-Using → AI-Native

Most people use AI like a vending machine: walk over, paste in a task, carry the answer back by hand. Every single time. It works, but it never compounds, and it never touches your actual tools.

```
   AI-USING                              AI-NATIVE
   ────────                              ─────────
   you ──▶ copy ──▶ [ web chat ]         "write this week's report"
       ◀── paste ◀──     │                         │
       every time,       │                         ▼
       by hand           ▼               ┌──────────────────────┐
                    a paragraph          │   your second brain  │
                                         │  • knows your work   │
                                         │  • holds your tools  │
                                         │  • learns your rules │
                                         │  • runs your SOPs    │
                                         └──────────┬───────────┘
                                                    ▼
                                          a finished doc, in Drive,
                                          ready to share
```

The jump from left to right is not a smarter prompt. It is **setup**: giving the AI your context, your tools, and your standard procedures so it can finish the job instead of handing you a paragraph. Most people stay on the left because that setup is the hard part.

**This repo is that setup, done.** Clone it, tell it who you are, connect the tools you already use, and you have a personal operating system for knowledge work. It is built for Claude Code, and the core instructions work with any agentic harness.

---

## It Learns You

A web chat forgets you the moment you close the tab. A second brain does the opposite: every correction makes it sharper, permanently. It carries two kinds of memory.

**The memory you write.** `CLAUDE.md` is a plain file you edit by hand: your role, your projects, your languages, your house rules. Change a rule there and every future session respects it.

**The memory it writes for you.** When you correct it in conversation, the `/learn` command distills the lesson and saves it, so the next session already knows without being told again.

```
   Monday
   You:  "Never send a Slack message without asking me first."
   You:  /learn
         ✔ saved to memory

   Thursday, next week, next month
   →  it asks before every send, without being reminded
```

Over weeks this adds up. Your voice, your formatting, the people who own what, the decisions already made, the mistakes it should never repeat. The brain you use in month three is measurably better tuned to you than the one you started with, because it kept every lesson along the way.

---

## Who This Is For

If a large share of your week is **repetitive, structured deliverables**, this is built for you:

- **Product managers.** PRDs, meeting notes, weekly reports, action-item tracking across teams.
- **Consultants, founders, and operators.** People who live in documents, meetings, and status updates.
- **Content creators.** Drafting, researching, and publishing on a schedule, in a consistent voice.
- **Anyone** drowning in meetings, Slack, and Google Docs who wants AI that *does* the work, not a chat box that talks about it.

---

## What It Is: Three Layers

Most AI tools are a blank chat box. This repo gives that box a **job description**, **standard operating procedures**, and **hands that reach your real tools**.

```
   YOU SAY:  "draft the PRD for the new checkout flow"
                              │
   ┌──────────────────────────────────────────────────────────┐
   │  CLAUDE.md       THE BRAIN     who you are, your rules,    │
   │                                your languages, your memory │
   ├──────────────────────────────────────────────────────────┤
   │  .claude/        THE REFLEXES  saved commands, subagents,  │
   │                                guardrail hooks             │
   ├──────────────────────────────────────────────────────────┤
   │  .agent/skills/  THE HANDS     Drive · Docs · Slack ·      │
   │                                Calendar · meetings · Jira  │
   └──────────────────────────────────────────────────────────┘
                              │
   YOU GET:  a real Google Doc, in your format, ready to share
```

1. **`CLAUDE.md` is the brain.** It states who you are, which projects you run, which language each document should be in, and the rules it must follow. It grows as you teach it. The more specific it is, the more autonomously the AI can act.
2. **`.claude/` is the reflexes.** Commands are saved workflows: draft a PRD, write meeting notes, produce a weekly report. Subagents split big jobs across cheaper helpers. Hooks enforce your rules automatically, for example asking before anything is sent to Slack.
3. **`.agent/skills/` are the hands.** Each one is a small script that reads or writes a real service: create a Google Doc from markdown, post a Slack message as you, pull a meeting transcript, fetch a sprint board, update a tracking sheet.

---

## What It Does, Every Day

Not a feature list. This is what one real week of use looks like, drawn from the activity log:

- **Every morning:** "prep my day." It sweeps calendar, Slack, email, and yesterday's meetings, then hands back the five things that matter before you open your laptop.
- **Every evening:** "close my day." It scores what got done against the morning plan, updates tomorrow's carryover, and asks if it should remember any correction you made.
- **After every meeting:** "write the notes." Transcript in, structured minutes out, action items filed to your tracker with owners and due dates.
- **All day:** "reply to this," "update this ticket's status," "draft the BRD for X." In a typical week that is dozens of Slack replies drafted, dozens of tickets synced, and a stack of documents published to Drive, each one gated by your approval before it goes out.
- **On a schedule:** the weekly executive report, the weekly plan, the content calendar. Each one harvests a week of scattered work and returns a finished draft.

The point is not any single trick. It is that the boring, structured 70% of the week runs on rails, so your attention goes to the 30% that needs a human.

---

## Capability Catalog

The repo ships dozens of skills and commands. A representative slice of what you can ask, in plain language:

| Area | What you can ask it to do |
| :--- | :--- |
| **Communication** | Sweep Slack across many channels and draft a reply in your voice; send email as you; post to a WhatsApp channel and forward to groups; reply inside a Google Doc comment thread. Every send is approval-gated. |
| **Documents** | Turn markdown into a real, formatted Google Doc; make surgical in-place edits (add links, insert table rows, embed diagrams) without clobbering your hand edits; export a branded PDF; draft and quality-gate a PRD. |
| **Meetings** | Record and transcribe a meeting locally on your own machine; turn any transcript into clean minutes with decisions and action items filed to your tracker. |
| **Reporting and ops** | A morning briefing and evening recap; a weekly executive report that weighs what mattered; a PRD pipeline; a live visual dashboard of every project. |
| **Data** | Query Jira sprints and flag anyone overloaded; pull funnels and retention from Mixpanel; run SQL against Metabase; sweep your calendar into a clean view. |
| **Design and media** | Generate and edit images from a prompt; render carousel slides; build diagrams from a description; assemble slide decks. |
| **Content and video** | Plan and draft posts in your voice with an anti-AI-tell pass; cut a long video into captioned vertical shorts; distribute one recording across platforms; produce a growth report. |
| **Learning** | Remember a correction permanently via `/learn`; keep your dashboard, to-do list, and trackers in sync automatically. |
| **Under the hood** | Fan a big job out to parallel workers; route bulk work to cheaper models with a guaranteed fallback; run a quality-gate reviewer before anything reaches you. |

### One recording, everywhere

The same pattern powers a content pipeline that would otherwise cost half a day and a stack of subscriptions:

```
   record once  ─▶  auto-edit  ─▶  "post it"  ─▶  YouTube + Instagram
                                                   + LinkedIn + Facebook
                                                   + WhatsApp channel ─▶ groups
```

Hand it a raw recording. It transcribes, scores the most compelling segments, cuts a captioned vertical clip with a branded closing frame, and on one approval uploads it to YouTube and Instagram natively, cross-posts to LinkedIn and Facebook, publishes to a WhatsApp channel, and forwards it across your WhatsApp groups with human-like pacing. You record, and you say the word. The distribution runs itself.

---

## How It Works

You talk to it in plain language. It maps your request to the right workflow and tools.

```
You:  "Write meeting notes from this morning's call and share to the team."

 AI   ① pulls the transcript from your meeting recorder
  │   ② drafts notes in your required language and format
  │   ③ runs a quality-review pass
  │   ④ creates a real Google Doc
  ▼   ⑤ asks before sharing  ─────────────────────▶  ✅ shared
```

You never memorize commands. A natural request like "draft a PRD for the new checkout flow" follows the same standard procedure as typing `/prd`, because `CLAUDE.md` routes both to the same workflow file.

**Runs on your machine, across machines.** The repo detects whether it is on macOS, WSL, or Windows at the start of each session and adapts how it runs your tools. Your credentials and notes stay local. Nothing is uploaded to a third party beyond the API calls the AI makes on your behalf.

**Guardrails that hold.** Sensitive actions such as sending a message or deleting a file are gated by hooks that fire no matter what, so a fast session never turns into an accident.

---

## Multi-Agent Setup: Faster and Cheaper

Here is the part that makes it economical to run every day.

A big job such as a weekly report, a deep-research brief, or a large PRD is rarely one kind of work. It is mostly **bulk reading**, a little **focused analysis**, and a bit of **careful synthesis**. Run all of it on one expensive model and you overpay for the reading. Run all of it on one cheap model and the thinking falls apart.

So this repo splits the job. One strategist directs; a fleet of cheap, fast workers does the reading in parallel; only the distilled facts come back for synthesis.

```
                    ┌────────────────────────────────────┐
   "write this      │      MAIN SESSION · Opus 4.8        │  plans + synthesizes
    week's   ──────▶│      the strategist                 │  (smart, pricey)
    report"         └─────────────────┬──────────────────┘
                                      │ spawns a fleet, all at once
          ┌──────────┬───────────────┼───────────────┬──────────┐
          ▼          ▼               ▼               ▼          ▼
      ┌───────┐  ┌───────┐       ┌───────┐       ┌───────┐  ┌───────┐
      │harvest│  │harvest│       │harvest│   …   │harvest│  │review │   Haiku 4.5
      │ mtg 1 │  │ mtg 2 │       │ mtg 3 │       │ Slack │  │ pass  │   (cheap, fast)
      └───┬───┘  └───┬───┘       └───┬───┘       └───┬───┘  └───┬───┘
          │   each reads ~12K of raw source, returns ~1.5K of facts   │
          └──────────┴───────────────┬───────────────┴──────────┘
                                     ▼
                    ┌────────────────────────────────────┐
                    │  Opus reads 15K of clean facts      │
                    │  → writes the finished report       │
                    └────────────────────────────────────┘
```

Two things save money and time at once. The **bulk reading**, usually the largest share of tokens, runs on a model that costs a fifth as much. And the **parallel workers** finish in the time a single agent would spend reading one file. The flagship spends its pricey tokens only where judgment is actually required.

A third saving comes from **prompt caching**: the large, stable parts of a prompt such as your `CLAUDE.md` or a long document are cached and reread at about a tenth of the normal input price across a session.

Two subagents ship as working examples: a **harvester** that reads many sources and returns structured facts without trying to write the final document, and a **reviewer** that checks a draft against your rules before it reaches you.

### Which Model for Which Job

Use the cheapest model that can do the subtask well. Match the tier to the work, not the other way around.

| Tier | Model | Model ID | Context | Price /1M (in / out) | Use it for |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bulk** | Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | $1 / $5 | Mechanical work with no judgment: bulk reading, formatting, extraction, classification. The default for harvester and reviewer subagents. |
| **Scoped** | Claude Sonnet 4.6 | `claude-sonnet-4-6` | 1M | $3 / $15 | Scoped research, code exploration, in-scope synthesis. The best balance of speed and intelligence for focused subtasks. |
| **Flagship** | Claude Opus 4.8 | `claude-opus-4-8` | 1M | $5 / $25 | The main session for synthesis-heavy work: planning, weighing tradeoffs, writing the final deliverable. |
| **Frontier** | Claude Fable 5 | `claude-fable-5` | 1M | $10 / $50 | The most demanding long-horizon, autonomous work, where one run may plan, build, and verify across many steps. When correctness matters more than cost. |

A practical default: run the main session on **Opus 4.8**, delegate bulk work to **Haiku 4.5** subagents, and reach for **Sonnet 4.6** when a subtask needs real research rather than mechanical effort. Move the main session up to **Fable 5** for the hardest end-to-end jobs.

> Model IDs are exact strings. Use them as written, with no date suffix. Prices are list API prices and may change; check the provider's pricing page for current figures.

### What It Saves on a Real Job: the Weekly Report

The weekly report is the clearest case, because it is mostly bulk reading wrapped around a little synthesis, exactly the shape the diagram above is built for. Take a representative week:

- **8 meeting transcripts** at ~12K tokens each, plus written notes, dashboard sections, the to-do list, and Slack history: about **150K tokens of raw source**.
- Of that, only about **15K tokens of distilled facts** actually matter for writing the report.

| | **A. One flagship agent does it all** | **B. This repo: Haiku harvests, Opus synthesizes** |
| :--- | :--- | :--- |
| Who reads the 150K of sources | Opus, in one growing context | 9 Haiku workers, in parallel |
| What the flagship then carries | all **150K** of raw transcript, re-read every turn | only the **15K** of facts |
| Reading cost (150K input) | 150K × $5/1M = **$0.75** | 150K × $1/1M = **$0.15** |
| Synthesis (~10 drafting turns) | 150K × 10 = 1.5M token-reads | 15K × 10 = 150K token-reads |
| Wall-clock to read sources | 8 transcripts, one after another | 8 transcripts at once (~1/8 the time) |

Two levers pull at the same time:

1. **Tier swap.** Every token of bulk reading moves from Opus to Haiku, a flat, exact **5x cheaper** (input $5 to $1, output $25 to $5). Same work, on the model the work actually needs.
2. **Context compression.** In version A the 150K of raw transcript sits in the flagship's window and is re-processed on *every* drafting turn. In version B the flagship only ever holds 15K of facts, so the drafting phase re-reads **10x less**. Usually the bigger saving, and it makes the report *better*, because the model reasons over clean facts instead of hunting through raw transcripts.

```
   COST OF ONE WEEKLY REPORT   (illustrative, from list prices)

   One flagship agent does everything
   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ~$2.00

   This repo · Haiku harvests, Opus synthesizes
   ▓▓▓▓  under $0.50            ← ~4-5x cheaper, and finishes faster
```

> These figures are an **illustrative model from list prices, not a published benchmark.** Your exact numbers depend on how many meetings you had, transcript length, and caching. The two levers and their direction hold regardless: bulk work on a 5x-cheaper tier, and a flagship context that never bloats with raw source. The same pattern applies to deep-research briefs, large PRDs, and any gather-then-synthesize job.

---

## Getting Started

### The 15-minute path (no API keys, no OAuth)

```bash
git clone https://github.com/BrianArfi/ai-second-brain.git
cd ai-second-brain
bash install.sh
claude
```

`install.sh` checks your tooling, creates `CLAUDE.md` from the template, and prepares `.env`. Open `CLAUDE.md`, describe who you are and how you work, then start talking. That alone gives you a brain that drafts, summarizes, and organizes in your voice, with no connectors needed yet.

### The full path (connect your real tools)

```
   ① clone + install.sh  ──▶  ② fill CLAUDE.md  ──▶  ③ connect tools  ──▶  ④ talk
```

1. **Fill in `CLAUDE.md`.** Describe yourself, your work contexts, and your rules. `docs/CUSTOMIZING.md` explains each section.
2. **Connect the tools you actually use** with `docs/SETUP.md`: Google, Slack, calendars, meeting recorders, Jira, step by step. You do not need all of them; there is a section on choosing only the skills you need. Budget 2-4 hours, mostly for Google OAuth.
3. **Start talking.** Ask it to organize a file, draft a document, or summarize a meeting.

Deeper references:

- **`docs/SETUP.md`** for the full install and authentication guide.
- **`docs/CUSTOMIZING.md`** for how to write a strong `CLAUDE.md`.
- **`docs/ARCHITECTURE.md`** for how the pieces fit together.
- **`docs/INSTALL_ID.md`** untuk panduan instalasi langkah demi langkah dalam Bahasa Indonesia (workshop companion).

---

## Folder Structure

```
.agent/skills/      Connectors and skills (Drive, Docs, Slack, Calendar, meetings, Jira, and more)
.agent/scripts/     Shared helpers, including the machine detection used at session start
.agent/workflows/   Reusable multi-step workflow definitions
.claude/commands/   Saved workflows you can invoke by name or in plain language
.claude/agents/     Subagent definitions (harvester, reviewer)
.claude/hooks/      Automatic guardrails (send confirmation, formatting checks)
docs/               Setup, customizing, and architecture guides
CLAUDE.md.template  Rename to CLAUDE.md and make it yours
```

---

<div align="center">

**Ready to start?**

Read `docs/SETUP.md`, fill in your `CLAUDE.md`, and let your second brain get to work.

</div>
