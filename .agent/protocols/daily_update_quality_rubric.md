# Daily Update Quality Rubric Protocol

To ensure absolute accuracy, strategic focus, and zero information gaps in all daily briefings, this protocol establishes a mandatory 9-checkpoint grading and validation system that the AI Partner MUST complete during the update process.

---

## 📋 The 9 Checkpoints of the Quality Rubric

### 1. Source Citation Check
- **Criteria**: Every item marked as a priority (P0/P1) or ongoing strategic focus must be accompanied by a fresh source reference (e.g. Slack message timestamp, file path of today's changes, or recent meeting note).
- **Failure Condition**: Any priority item carried over from dashboard history that has no fresh confirming signals today must be tagged as `⚠️ STALE / UNVERIFIED` and downgraded from the immediate focus list.

### 2. Cross-Reference & Completion Check
- **Criteria**: Cross-check every open item in `journal/todo.md` and `Dashboard.md` against today's fresh Slack logs, Jira updates, and meeting notes.
- **Failure Condition**: If there is conversational evidence that an item has been completed (e.g., Teammate sharing a document on Slack, Teammate resolving a bug), the item must be updated to `Completed` rather than being repeated as an open task.

### 3. Signal Coverage Audit
- **Criteria**: Track and document the scan status of every source data channel.
- **Failure Condition**: If any channel connection fails (e.g., Unicode crash, timeout), all updates dependent on that channel must be clearly designated as `❓ UNVERIFIED due to scan failure on channel #<name>`.

### 4. Staleness Scoring
- **Criteria**: Check the last modified or mentioned date of every active task.
- **Failure Condition**: Any item with zero activity or mention in the last 7 days must be flagged as `[Stale - Needs Re-verification]` and not presented as an active, high-priority daily item.

### 5. Contradiction Guard
- **Criteria**: Compare historical priority logs in `Dashboard.md` with today's fresh conversational signals.
- **Failure Condition**: Fresh data (e.g., direct Slack directives or recent meeting notes) always overrides stale repository backlog records. Highlight and flag any discrepancies found.

### 6. Task Status Dissonance (Verification)
- **Criteria**: Check if current chat/conversational context suggests a change of state (e.g. "approved", "shipped", "blocked") that does not match the static repository metadata.
- **Failure Condition**: If conversation shows a task is blocked, but the backlog says "In Progress", it must be flagged for status adjustment.

### 7. Roster & Team Ownership Check
- **Criteria**: Match every updated client/PM item to its official owner and team as defined in `Clients/Work/organization-context.md` (e.g. B2C Super App to Teammate, Platform to Teammate, Marketplace to Teammate, E-commerce Core to Teammate).
- **Failure Condition**: Ensure tasks are categorized under the correct team boards. Do not cross-assign without highlighting it.

### 8. Direct Mention & Project Keyword Sweeper
- **Criteria**: Run a dedicated regex filter across all fetched Slack/Calendar messages to find:
  - Direct @mentions of Your Name.
  - Strategic keywords (You's Book, You's Podcast).
- **Failure Condition**: Any direct mention or core project keyword must be extracted and surfaced, even if the source channel is not on the primary high-priority list.

### 9. Rule & Technical Constraint Guard
- **Criteria**: Audit final output syntax to ensure strict compliance with repo guidelines:
  - **No Em-Dashes**: NEVER generate `—`. Always convert to `--` or `-`.
  - **No Title Changes**: Preserving absolute IDs of Google Drive items when performing syncs.
  - **Separation of Style**: Apply "Pyramid/Segitiga" style exclusively to personal LinkedIn content and "You" persona drafts. Professional PM and Client-related summaries must use standard clean markdown.

---

## 🛠️ How to Enforce the Rubric in the Phased Update
During **Step 2 (Summarize)** and **Step 3 (Prioritize)** of the *Phased Update Protocol*, the agent must run the output draft against this checklist and include a brief "Rubric Compliance Scorecard" indicating success or highlighting any unverified/stale items.

---

## 🌅 Mode-Specific Rubric Application

### Morning Mode
The following checkpoints are **mandatory** in morning mode:
- **Checkpoint 1**: Source Citation Check -- ensure overnight signals are properly cited.
- **Checkpoint 2**: Cross-Reference & Completion Check -- verify if any todo items were completed overnight.
- **Checkpoint 4**: Staleness Scoring -- flag items with no activity in 7+ days.
- **Checkpoint 7**: Roster & Team Ownership Check -- ensure correct team assignment.
- **Checkpoint 8**: Direct Mention & Project Keyword Sweeper -- catch any overnight @mentions.

Checkpoints 3, 5, 6, and 9 are **optional** in morning mode (data may not be complete yet).

### Evening Mode
All 9 checkpoints are **mandatory** in evening mode. No exceptions.

### Weekend Mode
Only Checkpoint 8 (Direct Mention & Keyword Sweeper) is mandatory on weekends. All others are optional.
