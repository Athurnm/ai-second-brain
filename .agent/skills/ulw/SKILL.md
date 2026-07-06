---
name: ulw
description: "Ultrawork mode. Plan, fan out parallel subagents, self-verify, drive to an explicit definition of done. For multi-part knowledge work (reports, PRDs, research sweeps, multi-step ops). Triggers: ulw, ultrawork, /ulw."
---

# ULW: Ultrawork Mode (knowledge-work adaptation)

The omo "ultrawork" pattern, adapted for You's PM and content work. Relentless, parallel, self-verifying execution toward an explicit definition of done. Reuses the routing table in CLAUDE.md (`## Subagents`) and the existing quality gates (`draft-reviewer`, `report-auditor`).

## When to use
Multi-part tasks with independent sub-work: weekly report, PRD, briefing, research sweep, multi-doc operations. Skip it for a single quick reply (spawn overhead is not worth it).

## Procedure

1. **Announce and frame.** Say "ULW MODE." Restate the task and write an explicit **Definition of Done**: a short checklist of acceptance criteria. If scope or criteria are ambiguous, ask 1 to 3 sharp questions BEFORE working (interview-mode lite). Do not prompt and pray.

2. **Decompose and route.** Break the task into subtasks. Tag each with a routing category from CLAUDE.md (harvest / lookup / draft / review / synthesize / strategize), which fixes its model and effort.

3. **Fan out in parallel.** Spawn all independent mechanical subtasks (harvest, lookup, first-pass drafts) as concurrent subagents in a SINGLE message (multiple Agent calls so they run at once). Use `harvester` for bulk reads. Keep synthesis and strategy in the main loop. Never synthesize while harvesting.

4. **Synthesize (main loop).** Weigh, prioritize, and write the deliverable yourself. Recency is not importance: weight by delivered milestones, then unblocked blockers, then active risks, then ongoing work (per the report rules in CLAUDE.md).

5. **Adversarial self-verify.** Before presenting, run the matching gate and fix everything it flags:
   - drafts (PRD / MOM / Slack / LinkedIn / weekly report): `draft-reviewer`
   - briefings and weekly reports: `report-auditor`
   - strategy or decisions: a quick adversarial pass that attacks from three angles (is it over-scoped? will the stakeholder buy it? which claims are unverified?).

6. **Check the Definition of Done.** Re-check every acceptance criterion from step 1. If any is unmet, loop back to the step that produces it. Do not stop halfway or hand over partial work without saying so.

7. **Deliver.** Present the result plus a one-line "checked:" note stating what was verified and which gate passed.

## Scaling up (heavy tasks)
If the work is large and highly parallel (broad audit, many documents, loop-until-criteria), propose running it as a **Workflow** instead: deterministic fan-out with explicit per-stage model and effort, adversarial verify stages, and loop-until-done. Ask You before launching, because it spends more tokens.

## Honest limits
True cross-turn "never stop until done" cannot be hard-enforced: a Stop hook can block an exit but cannot feed goals back to the model. ULW enforces within-turn relentlessness and uses the Definition of Done as the stop gate. For genuine unattended looping, use `/loop` or a Workflow.
