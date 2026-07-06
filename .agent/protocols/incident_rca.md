# Incident RCA Protocol (mini-SOP)

Lightweight root-cause-analysis procedure for Work operational incidents (outages, data issues, failed releases). Adapted from gstack's `/investigate` discipline. Use it for any postmortem (e.g. the GCP outages) so the writeup has a real root cause and concrete prevention, not just a narrative.

**When to use:** any incident worth a writeup, especially recurring ones. For a one-line "fixed a typo" note, skip this.

**Language:** English (Work). Deliver as a markdown artifact; convert to a GDoc only if it's going to stakeholders.

## Iron Law
**No prevention actions, no "resolved" claim, until the root cause is established and verified.** Symptoms are not causes. "Restarted the service and it works now" is a mitigation, not a root cause. If the cause is still unknown, say so explicitly and label the writeup PRELIMINARY.

## Four phases (do them in order, don't skip ahead)

### 1. Investigate (facts only, no theories yet)
- Build a **timeline** in WIB: when it started, who noticed, what was observed, what was done, when it recovered. Timestamp every entry.
- Pull the evidence: Slack threads (link them), Fathom of any incident call, dashboards/logs, the exact error. Quote the verbatim error/signal, don't paraphrase.
- State the **blast radius**: who/what was affected, for how long, and how it was detected (alert vs a human noticing — detection gap is itself a finding).

### 2. Analyze (narrow to the cause)
- Run **5 Whys** from the symptom down to a cause you can point at. Stop when the next "why" leaves the system you control.
- Separate **trigger** (what set it off this time) from **root cause** (the latent condition that made the trigger possible). A billing card expiring is a trigger; "no alerting + no backup payment method on the GCP billing account" is the root cause.
- If multiple causes are plausible, list them and mark which are confirmed vs suspected.

### 3. Verify the hypothesis
- Confirm the proposed root cause **explains the full timeline** — every symptom, the recovery, and why it recurred if it recurred. If something doesn't fit, the cause is incomplete; go back to phase 2.
- Quote the specific evidence that proves the cause (the log line, the config, the Slack confirmation). An unverified cause stays labeled "suspected" and the writeup stays PRELIMINARY.

### 4. Prevention (concrete, owned, dated)
- Exactly **3 prevention actions** (more dilutes; fewer is usually under-thinking it). Each must name **what / owner / due date** and attack the root cause, not the symptom.
- Split into: **Detect** (would we catch it faster next time?), **Prevent** (would this specific cause recur?), **Mitigate** (if it recurs, smaller blast radius?). One per bucket is a good default.
- Cross-check ownership against the source: don't default actions to You when another team clearly owns them (see [[feedback_ownership_not_brian_by_default]]). File each as a ticket and link it.

## Output format
```
# RCA: <incident> — <date WIB>   [RESOLVED | PRELIMINARY]
## Summary (3 lines: what broke, impact, root cause)
## Timeline (WIB, timestamped)
## Root cause (trigger vs latent cause; evidence quoted)
## Prevention (3 actions: what / owner / due / ticket link, tagged Detect/Prevent/Mitigate)
## Open questions (if PRELIMINARY)
```

## Notes
- This complements `/hyperplan` (pre-decision adversarial review) and the quality gates; it is for *after* something broke.
- For a recurring incident, link the prior RCA and state explicitly why the earlier prevention didn't hold — a recurrence means a prevention action failed or was never done.
