---
name: Project Tracking Update
description: The "Triple-Check" protocol for keeping Dashboard.md, todo.md, master_followup_tracker.md, and project backlogs perfectly synchronized. Prevents "hanging" tasks and ensures external dependencies are never forgotten.
---

# Project Tracking Update Skill

This skill defines the **mandatory** procedure for updating the project's source-of-truth documents. It runs whenever:
- A task is completed
- A status changes
- New information arrives that affects tracking
- An external dependency is resolved or becomes overdue

**Goal**: Zero drift between `Dashboard.md`, `todo.md`, and `master_followup_tracker.md`. No completed work left appearing active. No overdue external item left unmarked. **Special focus on Management Mandates (YourManager/P0) and Team Capacity.**

---

## The "Triple-Check" Protocol

When a task is completed or a status changes, perform ALL 7 steps in order.

### Step 1: Update the Daily Briefing & Priorities
- **Target**: `Dashboard.md` -> `## ☀️ Daily Briefing & Priority`
- **Actions**:
    - Mark the specific task checkbox as `[x]`.
    - If the task was blocking others, identify the *next* priority and add it.
    - Check the "Advisor's Note" section - does it still reflect reality? If the gap was just closed, rewrite it.
    - Update the `*(Last Updated: ...)*` timestamp.

### Step 2: Update the Daily Change Summary
- **Target**: `Dashboard.md` -> `## 📊 Daily Change Summary`
- **Actions**:
    - If today's summary section doesn't exist yet, create one: `## 📊 Daily Change Summary -- [Client] (Month DD, YYYY)`
    - Add the completed task: `- [x] **[Project Name]** Task Description`
    - If new files were created, add them under `**Created/Updated Master Docs**`

### Step 3: Update the Project Status Table
- **Target**: `Dashboard.md` -> `## Active Projects` -> [Specific Project]
- **Actions**:
    - Update **backlog checkboxes** (`[x]` for completed items)
    - Update the **Status** emoji if the project phase changed
    - If a milestone is done, advance to the next phase name

### Step 4: Synchronize Personal Todo
- **Target**: `journal/todo.md`
- **Actions**:
    - **Search broadly**: `grep` for key terms of the completed task across the entire file - it may appear under "Pekan Ini", "Immediate Priorities", "Active Tasks", or a project subsection.
    - **Mark ALL instances** as `[x]`. Tasks often appear in multiple sections.
    - **Consistency**: Ensure the wording matches the completion status in `Dashboard.md`.

### Step 5: Synchronize Master Follow-up Tracker (CRITICAL)
- **Target**: `journal/master_followup_tracker.md`
- **Actions**:

    #### For Self-Tasks (You completed something):
    - Find the item in **Immediate Priorities (Self)** table.
    - Change `[ ]` to `[x]` and Status from `PENDING` to `DONE`.
    - If this task was a prerequisite for an external follow-up, note it in that external item's "Notes" column.

    #### For External Tasks (Someone delivered something You was waiting on):
    - Find the item in **External Follow-ups (Delegated)** table.
    - Change Status to `DONE`.
    - **Cascade check**: Does this unblock a new self-task for You? If yes, add it to the Self section.

    #### Overdue Detection (Run during every update):
    - Scan ALL items in the External Follow-ups table.
    - If `Follow-up Date` < today AND Status is still `PENDING`:
        - Change Status to `🔴 OVERDUE`
        - Add a note: "Overdue since [date]. Consider Slack follow-up."
    - **YourManager Mandate Check**: If the overdue item is a YourManager/Management mandate, move it to the TOP of the Dashboard priorities and add a 🚨 emoji.
    - Surface overdue items in the Dashboard Advisor's Note.

### Step 6: Update Team Workload & Design reporting
- **Target**: `Dashboard.md` -> `Advisor's Note` or a specific `Team Health` section.
- **Actions**:
    - If a task involves Teammate (Platform) or Teammate (Marketplace), update the "Team Balance" context in the Advisor's note.
    - If a task involves the Design team (Mark/Karima/Ranin), ensure You's direct oversight is reflected in the next steps.

### Step 6: Synchronize Project Backlog (If Applicable)
- **Target**: `Clients/[Client]/[Product]/backlog.md`
- **Actions**:
    - Find and mark the task as completed.
    - If the backlog has a priority ranking, check if priorities need reshuffling.

### Step 7: Final Verification (The "Hang" Check)
- **Target**: ALL tracking files
- **Actions**:

    1. **Grep for Duplicates**: Search for key terms of the completed task across `Dashboard.md`, `todo.md`, and `master_followup_tracker.md`. Ensure no unchecked duplicates remain.
    
    2. **Conflict Check**: Verify consistency:
        - Dashboard says "Done" -> todo.md must also say "Done"
        - Master tracker says "DONE" -> todo.md must also say `[x]`
        - No file should say "In Progress" while another says "Done"
    
    3. **Orphan Check**: Look for tasks in `todo.md` that reference external people (Gaith, ExampleVendor, Teammate, Teammate, Teammate, etc.) but are NOT in `master_followup_tracker.md`. If found, add them to the tracker.
    
    4. **Staleness Check**: Are there items in `master_followup_tracker.md` with no Follow-up Date? Default them to **3 business days from now**.

---

## When to Invoke This Skill

| Trigger | Action |
|:---|:---|
| You says "done", "completed", "shipped" | Full 7-step protocol |
| You uploads a PRD or document | Steps 2, 3, 6 (add to summary, update project, update backlog) |
| Meeting summary processed | Steps 4, 5 (extract tasks to todo and tracker) |
| `/daily-update` executed | Step 5 overdue detection + Step 7 full verification |
| You mentions someone else's name + action | Step 5 only (add external follow-up) |
| Status change mentioned | Steps 1, 3, 4 (briefing, project table, todo) |

---

## Example Scenarios

### Scenario A: Task Completed - "RBAC Requirements Finalized"

1. **Dashboard Priorities**: Mark `[x] Review RBAC Requirements`.
2. **Dashboard Summary**: Add `- [x] **[Work Seller]** RBAC Requirements Finalized`.
3. **Project Table**: Update Seller Portal backlog. Next Action: "Order Fulfillment Workflow".
4. **todo.md**: Search "RBAC" - found in 2 places. Mark both `[x]`.
5. **master_followup_tracker.md**: Was RBAC blocking an external item? Check and update.
6. **Backlog**: Mark RBAC done in `Clients/Work/Seller Portal/backlog.md`.
7. **Verification**: Grep "RBAC" across all 3 files. Found an old `P0: RBAC` in the backlog? Mark it `[x]` too. No conflicts found.

### Scenario B: External Dependency Resolved - "Gaith delivered the roadmap reframe"

1. **Dashboard**: Update Advisor's Note to reflect that the blocker is resolved.
2. **Dashboard Summary**: Add `- [x] **[Work]** Gaith delivered Q2 roadmap reframe`.
3. **Project Table**: Update milestone in relevant Work section.
4. **todo.md**: Find "Follow up Gaith on Q2 Roadmap reframing" and mark `[x]`.
5. **master_followup_tracker.md**: 
    - External table: Change Gaith's reframe item to `DONE`.
    - Self table: Add new task "Review Gaith's reframe and provide feedback" if applicable.
6. **Backlog**: N/A (strategic item, not engineering task).
7. **Verification**: Grep "Gaith" and "roadmap" - ensure no stale references remain active.

### Scenario C: Overdue Detection during Daily Update

1. Scan `master_followup_tracker.md` External section.
2. Found: Gaith's "Reframe roadmap" was due May 1, today is May 3, status still PENDING.
3. Change status to `🔴 OVERDUE`.
4. Update Dashboard Advisor's Note: "🔴 1 overdue: Gaith's roadmap reframe (was due May 1). Suggest Slack follow-up."
5. No changes needed in todo.md or backlog (task not completed, just flagged).

---

## Anti-Patterns to Avoid

| Bad Pattern | Why It's Bad | Correct Behavior |
|:---|:---|:---|
| Updating only `todo.md` | Dashboard and tracker get out of sync | Always update all 3 files |
| Adding external tasks to `todo.md` only | You loses visibility on WHO owes WHAT | Must also add to `master_followup_tracker.md` |
| No follow-up date on external items | Items silently rot with no accountability | Default to +3 business days |
| Marking "Done" in one file only | Creates contradictions across the system | Grep and verify consistency |
| Silent updates | You doesn't know what changed | Always report: "Updated X, marked Y done, flagged Z overdue" |
