---
name: hyperplan
description: "Adversarial review. Stress-test a plan, decision, or draft with 5 hostile critics attacking from orthogonal angles in parallel, then keep only what survives. Triggers: hyperplan, hpp, /hyperplan, adversarial review, pre-mortem, stress-test this."
---

# HYPERPLAN: Adversarial Review (PSB adaptation)

Adapted from oh-my-openagent's hyperplan. Five hostile critics attack the target from orthogonal angles, then the main loop keeps only the points that survive. This is not consensus building; it is a pre-mortem. Weak assumptions get exposed before You commits.

## When to use
High-stakes, hard-to-reverse, or stakeholder-facing work: Loyalty Alliance Phase-0 decisions, a PRD before sign-off, a pitch or proposal to YourManager, AI Circle strategy, a roadmap commitment, a risky Slack/email. NOT for routine drafts (that is what `draft-reviewer` is for).

## Procedure

1. **Announce and frame.** Say "HYPERPLAN MODE." Restate the target in one line and confirm where it lives (file path, Drive doc, or pasted text). If the target is vague or not provided, ask You to point to the doc or paste it BEFORE spawning anything.

2. **Spawn 5 critics IN PARALLEL.** One message, five `hyperplan-critic` subagents, each with exactly one lens below. Pass each the same target plus its lens. Each reads the target and returns its 3 to 5 strongest attacks. For model diversity, spawn **strategist** and **contrarian** with `model: opus`; the other three run at the agent default.

   - **Skeptic** (simplicity): over-scope, complexity, scope creep, gold-plating, "flexibility for later." Weapon: "Cut it. Prove it is needed today."
   - **Stakeholder** (buy-in): the decision-maker's and affected teams' view (YourManager, the client, ops, eng). "Will they approve? Who is not bought in? What is the cross-team cost?"
   - **Evidence** (rigor): unverified claims, numbers with no source, assumptions stated as facts. "Where is the data? What is assumed?"
   - **Strategist** (structure and second-order): structural flaws, what breaks at scale, downstream and long-term effects, hidden dependencies. "What did you not consider? What breaks in six months?"
   - **Contrarian** (blind spots): the orthodox assumption everyone shares, the option nobody proposed. "What if the opposite is true?"

3. **Synthesize in the main loop** (judgment work, keep it on the flagship model). For every attack, rule it: SURVIVED (real, must address) / PARTIAL / REFUTED. Be honest; do not rubber-stamp the plan and do not rubber-stamp the critics.

4. **Output:**
   - **Survivors**, ranked by severity, each with a concrete fix or the question that must be answered.
   - **Refuted**, briefly, so You sees they were considered and dismissed on purpose.
   - **Verdict**: GO / GO WITH CHANGES (list them) / RETHINK.
   - If the target is a draft, give the specific edits. If a decision, give the revised recommendation.

## Scaling
Default is 5 critics, single pass. For a board-level or irreversible call, offer a second round: fix the survivors, then re-run the critics on the revised version, repeating until a round surfaces nothing new (loop-until-dry). Ask before spending the extra round; do not auto-run it.

## Notes
- Critics are read-only and return attacks only. The main loop owns the synthesis and the final call. Never let a critic's opinion be the decision.
- Reuses the routing table in CLAUDE.md: critics are the review/strategize tier; synthesis stays in the main loop.
- This complements, does not replace, `draft-reviewer` (mechanical pre-send checks) and `report-auditor` (rubric audit).
