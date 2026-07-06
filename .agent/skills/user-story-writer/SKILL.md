---
name: User Story Writer
description: 'Turn features into sprint-ready stories that are Independent, Negotiable, Valuable, Estimable, Small, and Testable. Use when: write user stories, user story, acceptance criteria, story points.'
---

# User Story Writer Skill

## Purpose
Turn features into sprint-ready user stories validated against INVEST criteria with Gherkin acceptance criteria. This skill produces **individual, well-crafted stories** - not full PRDs.

## When to Use
- Writing stories during backlog grooming or sprint planning
- Translating PRD requirements into sprint-ready stories
- Quick backlog additions from Slack threads, meetings, or ad-hoc ideas
- Training junior PMs on good story format

## When NOT to Use
- If you need a **full PRD**, use the `PRD Pipeline` skill instead
- If you're **improving an existing PRD's quality**, use the `Marketplace Product Manager` skill instead

## Relationship to Other Skills
- **PRD Pipeline** creates entire PRDs with 8+ embedded stories. This skill creates 1 story at a time with deeper INVEST validation.
- **Marketplace Product Manager** enforces PRD-level quality. This skill enforces story-level quality.
- If a PRD already exists for the project, this skill should **reference its Req IDs** and extend its stories rather than duplicating them.

---

## Process

### Step 1: Context Check

Before writing any story, scan for context files. Check in this order:

1. **Client/Project directory** - Look for existing PRDs, requirements docs, or specs in `Clients/[Client]/[Project]/`
2. **`personas.md`** - Search for persona definitions at client or project level
3. **`product.md`** - Search for roadmap or product context at client or project level
4. **Existing PRD** - If a PRD exists for this project, extract relevant Req IDs and existing stories

Report what you found:
> "I found [X] in your project files. [Persona Y]'s main frustration is '[Z].' I'll write the user story from their perspective."

If no context files exist:
> "I didn't find personas.md or product.md in your project. I'll work with what you've given me. Consider creating these files for richer stories in the future."

### Step 2: Gather Feature Details

If the user hasn't provided enough context, ask:
> "I need to understand the capability before writing stories:
> 1. What feature or capability are we adding?
> 2. Who is the user? (their role, what they're trying to accomplish)
> 3. What problem does this solve for them?
>
> Or point me to a PRD and I'll extract stories from it."

### Step 3: Craft the Story

Use the template at `templates/user_story_template.md`. The core format:

```
As a [user type],
I want to [action/capability],
So that [benefit/outcome tied to persona goals].
```

Rules:
- The "As a" must reference a real user role, not a generic "user"
- The "I want to" must be a specific, concrete action
- The "So that" must connect to a real user goal or pain point
- No em-dashes - use hyphens (`-`) only

### Step 4: Validate Against INVEST

Check each criterion and note any concerns:

| Criterion | Question | Pass/Fail |
|---|---|---|
| **I**ndependent | Can this be delivered without waiting for other stories? | |
| **N**egotiable | Are implementation details flexible (not prescribing HOW)? | |
| **V**aluable | Does this deliver value the user can see or feel? | |
| **E**stimable | Is the scope clear enough for the team to estimate effort? | |
| **S**mall | Can this be completed in a single sprint? | |
| **T**estable | Are there clear pass/fail criteria below? | |

> [!WARNING]
> If a story fails **Small**, suggest how to decompose it into smaller stories.
> If a story fails **Independent**, note the dependency explicitly.

### Step 5: Write Acceptance Criteria (Gherkin)

Minimum 3 ACs per story covering:
1. **Happy path** - the main success scenario
2. **Alternate path** - a valid but different way to accomplish the goal
3. **Error/edge case** - what happens when something goes wrong

Format:
```
Given [precondition with specific values],
When [user action - specific and concrete],
Then [observable, measurable outcome].
```

Rules (inherited from PRD Pipeline standards):
- Every `Then` must be **objectively measurable** by QA
- Bad: "system works correctly", "user sees appropriate message"
- Good: "response status is 200", "error toast displays 'Invalid email format'"
- Include specific values, not vague descriptions

### Step 6: Edge Cases & Technical Notes

List what could go wrong and what the boundaries are:
- Input limits (character counts, file sizes, etc.)
- Concurrent user scenarios
- Permission boundaries
- Network/timeout failures

If a PRD exists, cross-reference its unhappy paths and edge cases.

### Step 7: Sizing & Decomposition

Estimate story size using T-shirt sizing:

| Size | Guideline |
|---|---|
| **S** | < 1 day of work. Single endpoint, simple UI change, config update. |
| **M** | 1-3 days. New feature with 1-2 components, moderate complexity. |
| **L** | 3-5 days. Multi-component feature, integrations, or complex logic. |
| **XL** | > 5 days. **Too large - must be decomposed.** |

If XL, suggest decomposition into smaller stories and present them.

---

## Batch Mode

When the user asks to write multiple stories (e.g., "write all stories for Feature X"):

1. List all stories you plan to write as a numbered outline first
2. Get user confirmation on the list
3. Write each story using the full template
4. Number stories with a consistent ID scheme: `US.[Feature].[Number]` (e.g., `US.REFUND.01`)

---

## Output

Use the template at `templates/user_story_template.md` for all output. Write the story to the appropriate project directory or present it inline if no specific project context exists.

---

## Rules of Engagement

1. **No fluff** - Output stories directly. No preambles.
2. **Persona language** - Use the persona's vocabulary and perspective, not generic PM-speak.
3. **Connect to JTBD** - The "So that" must link to persona goals or frustrations.
4. **Be specific on edge cases** - These often become bugs later.
5. **No em-dashes** - Use hyphens (`-`) exclusively.
6. **Cross-reference PRDs** - If one exists, link back to Req IDs.
