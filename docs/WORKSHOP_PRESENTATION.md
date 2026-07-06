# Workshop Slide Deck: AI Second Brain 🧠
*From AI-Using to AI-Native Product Leader*

This document serves as your complete slide-by-slide presentation deck, talk track, and live demo script for your Secondary parting gift workshop on **Friday at 4:00 PM WIB**. All talk tracks have been translated into professional, engaging English.

---

## Slide 1: Title & Welcome
* **Visual**: Clean, premium dark background. Title in bold Google Fonts: **AI Second Brain: Transitioning from AI-Using to AI-Native Product Talent**. Subtitle: *A Parting Gift for Secondary Product Teams by Your Name.*
* **Format**: Large typography, HSL/gradient accent.
* **Talk Track (English)**:
  > "Hello everyone! Thank you so much for joining me on this Friday afternoon. As you all know, tomorrow is my last day at Secondary. Before I head out, I wanted to leave you all with a parting gift—something that has fundamentally transformed how I work and stay productive.
  > 
  > Over the past year, I’ve spent hundreds of hours experimenting with AI. I didn't just use ChatGPT web browser tabs to write emails; I built a fully integrated **AI Second Brain** that runs locally on my machine. Today, I want to unpack this setup for you for free, and help anyone interested get it running on their own machine."

---

## Slide 2: The Product Manager's Nightmare
* **Visual**: Split screen. 
  * Left: A chaotic list of files, Slack messages, Google Doc tabs, calendar events, and Fathom transcripts. 
  * Right: A clean, single dashboard and automated inbox folder.
* **Talk Track (English)**:
  > "As Product Managers, our biggest enemy isn't changing roadmaps or complex requirements—it's **administrative overhead and context switching**. 
  > We attend 6 to 10 meetings a week, write dozens of pages of PRDs, sync with multiple stakeholders, compile weekly progress reports, and track endless action items across teams. 
  > 
  > The result? We spend 70% of our week on repetitive administrative tasks, leaving only 30% for high-leverage strategic thinking. The AI Second Brain is designed specifically to reverse that ratio."

---

## Slide 3: What is an "AI-Native" Talent?
* **Visual**: A simple progression diagram:
  ```
  [ AI-Unaware ] ──> [ AI-Using ] ──> [ AI-Native ]
  (No AI tools)      (Copy-paste to     (AI is an agentic
                      ChatGPT web)       partner with system
                                         & file access)
  ```
* **Talk Track (English)**:
  > "There is a massive chasm between being **AI-Using** and being **AI-Native**.
  > *   **AI-Using**: You have a task, you open your web browser, paste some text into ChatGPT, ask it to clean up grammar or draft an email, and paste it back. This is mechanical, high-friction, and doesn't scale.
  > *   **AI-Native**: You design a system where the AI has direct, secure access to your local workspace files. The AI understands your project context, knows your stakeholders, and automates heavy lifting in the background while you focus on engineering or user conversations. You never copy-paste—you just invoke your partner."

---

## Slide 4: The 3-Layer Architecture
* **Visual**: A simple layered block diagram:
  ```
  ┌────────────────────────────────────────────────────────┐
  │  Layer 3: AI Interface (CLAUDE.md / Dashboard.md)     │
  ├────────────────────────────────────────────────────────┤
  │  Layer 2: Automation Engine (.agent/skills & scripts)  │
  ├────────────────────────────────────────────────────────┤
  │  Layer 1: Knowledge Base (Clients/, journal/todo.md)   │
  └────────────────────────────────────────────────────────┘
  ```
* **Talk Track (English)**:
  > "The system we are setting up today relies on three distinct layers:
  > 1.  **Layer 1 - Knowledge Base**: A local, markdown-based folder structure containing your client context, PRDs, roadmaps, and todo lists. It is lightweight, fast, and completely under your control.
  > 2.  **Layer 2 - Automation Engine**: Modular skills and scripts (`.agent/skills/`) that interface with Google Drive, Slack, Calendar, Figma, and Fathom.
  > 3.  **Layer 3 - AI Interface**: Guided by your `CLAUDE.md` (the AI's operating manual) and synchronized via `Dashboard.md` (your project's active state)."

---

## Slide 5: Live Demo — Real PM Workflows 🪄
* **Visual**: Black screen with a glowing "LIVE DEMO" badge. Columns showing 4 real-world workflows You uses.
* **Interactive Steps for You**:
  Show how your terminal agent solves actual daily work:
  
  ### 1. The Daily Standup & Update (`daily_update_runner.py`)
  *   **Action**: Run the daily sync command.
  *   **Magic**: Watch the agent pull calendar events, scan Drive updates, check whitelisted Slack channels, and automatically compile a clean daily update in `Dashboard.md`.
  
  ### 2. Action Item Generator (Meeting Transcript Processing)
  *   **Action**: Drop a raw meeting transcript (from Fathom or Google Docs) into `inbox/`.
  *   **Magic**: Ask the companion: `"organize my inbox"`. Watch the AI parse the discussion, identify decisions and blockers, generate sprint-ready user stories, and automatically file the meeting notes under the correct folder.
  
  ### 3. Weekly Status Report Generator
  *   **Action**: Ask the AI: `"draft my weekly progress report"`.
  *   **Magic**: The AI automatically harvests all daily achievements and blocker statuses across the week, synthesizes them into an executive summary, and formats a perfect progress report.
  
  ### 4. Smart Scheduling (`/schedule`)
  *   **Action**: Type a schedule command: `"schedule a reminder for tomorrow at 9 AM to follow up with engineering on checkout bugs"`.
  *   **Magic**: The agent registers a background schedule task that automatically prompts you or notifies you when the time arrives.
* **Talk Track (English)**:
  > "Let's look at how this works in real life. I don't use simple toy examples. The system runs my actual daily routines.
  > 
  > First, my **Daily Update**. By running one command, the AI sweeps my calendar, Slack channels, and recent documents, updating my dashboard in seconds.
  > 
  > Second, **Action Item Generation**. I drop a raw, chaotic meeting transcript from Fathom into the `/inbox` folder. The AI automatically structures the meeting minutes, files it away, and extracts sprint-ready user stories.
  > 
  > Third, **Weekly Progress Reports**. The AI automatically harvests the week's achievements to draft a structured executive status report.
  > 
  > And fourth, **Smart Scheduling**. I can tell the AI to set timers, background schedules, and follow-ups. Everything is automated, centralized, and frictionless."

---

## Slide 6: The AI Partner's Brain — `CLAUDE.md`
* **Visual**: Clean code screenshot highlighting specific sections of `CLAUDE.md`:
  * **Who You're Helping** (Your role, timezone, and project focus).
  * **Workflow Checklists** (Strict, step-by-step checklists the AI must follow).
  * **Document Rules** (Formatting styles and naming conventions).
* **Talk Track (English)**:
  > "The reason this AI is so reliable—and never hallucinates—is a file called `CLAUDE.md`.
  > 
  > This is your AI's **Job Description and Operating Manual**. It tells the AI exactly who you are, what projects you care about, and the strict rules it must follow. For example: *'Never send a Slack message without my explicit approval'* or *'Always keep comments preserved'*. 
  > Every time you start a chat session, the AI reads this file first and acts exactly like a highly trained personal assistant who already knows your entire job."

---

## Slide 7: Safety & Local-First Guardrails 🔒
* **Visual**: Security shield icon. Bullet points:
  * 100% Local Files (sensitive data never leaves your computer).
  * Strict `.gitignore` (tokens, cookies, and keys are blocked from git).
  * Explicit Approval Required (AI cannot send Slack messages or write to APIs without terminal confirmation).
* **Talk Track (English)**:
  > "A quick word on security and data privacy because we are using this for work. 
  > 
  > First, **everything is local-first**. Your sensitive documents, roadmap drafts, and todo lists remain on your physical hard drive. The AI only reads them when you run your local agent session.
  > 
  > Second, the repository is pre-configured with a robust `.gitignore` file, ensuring your access keys and tokens are never uploaded to GitHub.
  > 
  > Third, there is an ironclad rule in the system: the AI has no autonomy to write to external APIs—like posting to Slack or updating Google Drive—without your explicit confirmation at the terminal."

---

## Slide 8: Interactive Workshop: The 15-Minute Quick-Start ⚡
* **Visual**: Two columns on screen.
  * Left: **Option A: Agent-Driven Setup (Let the AI do it!) [RECOMMENDED]**
    * Just prompt: *"Set up this repository, rename CLAUDE.md.template, and configure my companion"*
  * Right: **Option B: Manual Setup (Do it yourself)**
    * Copy files, edit templates, and write configurations manually.
* **Talk Track (English)**:
  > "Now, it's your turn! For those who just wanted a quick demo, we can transition to a Q&A now. 
  > 
  > For the hands-on crew, let's start our **15-Minute Quick-Start**. And here's the best part: we have two ways to do this. 
  > 
  > You can choose **Option B** and copy files or change templates manually. Or, you can choose **Option A** and experience the power of an Agentic Second Brain right now—by simply **asking the AI to do the setup for you**! 
  > If you are using VS Code (with an agentic AI extension) or Claude Code, you can literally type a single prompt: *'Configure my local companion and rename CLAUDE.md for me'*, and the AI will execute the terminal commands and set up your workspace autonomously. Let's open our editors and try it!"

---

## Slide 9: Level 2: Advanced Connectors & AI-Led Dependency Install 🔗
* **Visual**: Visual flow representing:
  * **Option A: Let the AI install requirements & prep env files** (Prompt: *"Read SETUP.md, install Python packages in a venv, and copy .env"*).
  * **Option B: Manual install** (`pip install -r requirements.txt`, `cp .env.example .env`).
  * Creating a Google Cloud project & downloading `credentials.json`.
* **Talk Track (English)**:
  > "For those who want to unlock the full potential—like automated daily updates, Google Drive document syncing, or whitelisted Slack channel feeds—we will move to **Level 2**.
  > 
  > Once again, you don't need to struggle with the terminal. You can just prompt the AI: *'Read SETUP.md, install the Python requirements in my terminal, and duplicate the environment files.'* 
  > 
  > The only thing you'll need to do manually is the security authentication: setting up a free Google Cloud project and dropping in your `credentials.json`. The AI will handle the rest, install all packages, and verify your system. Let's configure our credentials!"

---

## Slide 10: Parting Gift & CTA 🎁
* **Visual**: Sleek design featuring a QR Code linking to your LinkedIn profile (`linkedin.com/in/you`) and a banner for the **AI Circle** community.
* **Talk Track (English)**:
  > "It has been an absolute honor working with all of you here at Secondary. I hope this AI Second Brain helps you work faster, eliminate administrative burnout, and become truly AI-native talents.
  > 
  > If you want to keep in touch, continue discussing advanced AI workflows, or join my subscription-based community, please scan this QR code to join **AI Circle** and connect with me on LinkedIn. 
  > Let's stay connected and build the future together. Thank you!"
