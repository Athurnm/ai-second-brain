# PRD Quality Rubric — The Crucible Scorecard

> Used by the Devil's Advocate Agent in STATE 3.
> **PASS Criteria**: Average ≥ 9.0 across all 6 dimensions. No single dimension below 7.

---

## Scoring Guide

| Score | Label | Meaning |
|---|---|---|
| 10 | **Exemplary** | Best-in-class. Could be published as a reference PRD. |
| 9 | **Excellent** | Comprehensive, specific, and actionable. Minor polish only. |
| 8 | **Strong** | Solid coverage with 1-2 areas needing more depth. |
| 7 | **Adequate** | Meets minimum bar but lacks precision in multiple areas. |
| 6 | **Below Standard** | Noticeable gaps. Needs rework on specific sections. |
| 5 | **Weak** | Multiple sections are vague, incomplete, or missing. |
| 1-4 | **Unacceptable** | Fundamentally incomplete. Restart required. |

---

## Dimension 1: Completeness (Weight: 1x)

**Question**: Are ALL template sections present and substantively filled?

| Score | Criteria |
|---|---|
| 10 | Every section filled with rich detail. No placeholders. Open Questions section is populated AND has owners/dates. |
| 9 | All sections filled. At most 1 minor gap (e.g., a risk without an owner). |
| 8 | All sections present. 2-3 minor gaps. |
| 7 | All sections present but some are thin (1-2 sentences where a paragraph is needed). |
| ≤6 | Missing sections, TBDs present, or sections with only headers and no content. |

**Red Flags** (auto-deduct 2 points each):
- Any section containing "TBD", "To be defined", "See [other doc]" without inline summary
- Missing RBAC table
- Missing rollout/migration plan

---

## Dimension 2: Depth & Specificity (Weight: 1x)

**Question**: Can someone unfamiliar with the project understand exactly what to build?

| Score | Criteria |
|---|---|
| 10 | Field-level validation rules, concrete SLA numbers, specific API endpoints, data schemas defined, error codes listed. |
| 9 | All key specs are concrete with numbers/constraints. At most 1 area could benefit from more precision. |
| 8 | Most specs are concrete. 2-3 features described at high level without field details. |
| 7 | Mix of concrete and vague. Some features say "support attachments" without size limits, types, or error handling. |
| ≤6 | Dominated by vague statements: "improve UX", "fast response times", "handle errors gracefully." |

**Red Flags** (auto-deduct 2 points each):
- Success metrics without instrumentation method
- Performance targets without p50/p95/p99 breakdown
- "Handle errors" without specifying which errors and how

---

## Dimension 3: Edge Cases & Unhappy Paths (Weight: 1x)

**Question**: What happens when things go wrong?

| Score | Criteria |
|---|---|
| 10 | ≥ 7 unhappy paths documented with explicit system behavior. Covers: network failure, timeout, invalid input, permission violation, concurrent modification, dependency outage, data corruption. |
| 9 | ≥ 5 unhappy paths. All critical failure modes covered with explicit handling. |
| 8 | ≥ 5 unhappy paths but 1-2 lack explicit handling details. |
| 7 | 3-4 unhappy paths. Some obvious failure modes missing. |
| ≤6 | ≤ 2 unhappy paths or only mentions "error handling" without specifics. |

**Mandatory Edge Cases** (must be addressed or explicitly marked N/A with justification):
- [ ] What if the external API/dependency is down?
- [ ] What if the user's session expires mid-action?
- [ ] What if concurrent requests conflict?
- [ ] What if input data is malformed or exceeds limits?
- [ ] What if a background job fails silently?

---

## Dimension 4: Testability (Weight: 1x)

**Question**: Can QA write test cases directly from this PRD without asking the PM a single question?

| Score | Criteria |
|---|---|
| 10 | Every user story has Gherkin AC. Every `Then` is objectively measurable (status codes, field values, time bounds). Test data requirements specified. |
| 9 | All stories have Gherkin. All `Then` clauses measurable. Minor: test data not specified for 1-2 stories. |
| 8 | All stories have Gherkin. 1-2 `Then` clauses are slightly subjective ("user sees appropriate message"). |
| 7 | Most stories have Gherkin. Some ACs are narrative rather than structured. |
| ≤6 | Stories lack Gherkin format. ACs are vague: "it should work", "user is satisfied." |

**Red Flags** (auto-deduct 2 points each):
- `Then` clause using words: "appropriate", "correctly", "properly", "as expected"
- User story without any acceptance criteria
- AC that requires PM interpretation to validate

---

## Dimension 5: Architectural Clarity (Weight: 1x)

**Question**: Can a senior engineer design the system from this PRD alone?

| Score | Criteria |
|---|---|
| 10 | Architecture diagram, sequence diagrams, data model, integration contracts (endpoints, payloads, auth), queue/event specs, caching strategy. |
| 9 | Architecture diagram + data model + integration contracts. At most 1 integration missing payload details. |
| 8 | Architecture diagram present. Data model implied but not explicit. Integration contracts partially defined. |
| 7 | Architecture diagram present but high-level. No data model. Integrations mentioned but not specified. |
| ≤6 | No diagrams. Architecture described only in prose. |

**Red Flags** (auto-deduct 2 points each):
- No Mermaid/visual diagram anywhere in the document
- External API integrations without error handling strategy
- Data flows described without mentioning persistence layer

---

## Dimension 6: Operational Readiness (Weight: 1x)

**Question**: Can we safely deploy, monitor, and roll back this feature?

| Score | Criteria |
|---|---|
| 10 | Phased rollout plan with traffic percentages, rollback triggers, monitoring dashboards, alerting rules, SLA definitions, incident playbook reference, on-call expectations. |
| 9 | Rollout plan + monitoring + rollback defined. At most 1 missing (e.g., no incident playbook). |
| 8 | Rollout plan present. Monitoring mentioned. Rollback described at high level. |
| 7 | Mentions "gradual rollout" but no specifics (percentages, cohorts, timing). |
| ≤6 | No rollout plan. No monitoring. Assumes "big bang" deployment. |

**Red Flags** (auto-deduct 2 points each):
- No rollback strategy
- No monitoring/alerting mentioned
- No SLA defined for the new system

---

## Scorecard Output Template

After evaluation, produce this table:

```markdown
## Crucible Quality Scorecard

| # | Dimension | Score | Key Findings |
|---|---|---|---|
| 1 | Completeness | X/10 | [1-line summary] |
| 2 | Depth & Specificity | X/10 | [1-line summary] |
| 3 | Edge Cases & Unhappy Paths | X/10 | [1-line summary] |
| 4 | Testability | X/10 | [1-line summary] |
| 5 | Architectural Clarity | X/10 | [1-line summary] |
| 6 | Operational Readiness | X/10 | [1-line summary] |
| | **AVERAGE** | **X.X/10** | |

**Verdict**: PASS ✅ / FAIL ❌
**Deficiencies** (if FAIL):
1. [Dimension]: [Specific gap] → [What must be added]
2. ...
```

---

## Revision Loop Rules

1. If FAIL, the Strategist receives ONLY the scorecard + deficiency list (NOT the original brief).
2. The Strategist revises the PRD to address each numbered deficiency.
3. The Devil's Advocate re-scores the revised PRD.
4. **Max 3 loops**. If still FAIL after loop 3 → escalate to user with current scores and remaining gaps.
