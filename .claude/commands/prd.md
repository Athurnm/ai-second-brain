---
description: Draft or revise a Work PRD - Drive-first dedupe, English, quality-gated, registered in Master Product List
argument-hint: "<feature/product name or brief>"
---

PRD workflow (Work):

> **ExampleCo / ExampleProgram client-facing BRD?** If the deliverable is a BRD or feature doc that will be SHARED
> WITH the ExampleCo / ExampleProgram client, do NOT use the technical PRD pipeline below. ExampleCo told us (via Teammate,
> 30 Jun 2026) our standard BRD is too technical. Use the lightweight, visual, business-outcome
> "Feature Release Document" format in `.agent/skills/prd-pipeline/templates/brd_exampleco.md`
> (Problem → Solution → Key Features → User Impact → Success Metrics → screenshot, or the
> Objective/Problem/Goals + Desktop/Mobile-walkthrough variant). Still English, no em-dashes, still
> draft-reviewed and Drive-published, but no Gherkin / data models / acceptance-criteria / sign-off bloat.
> Internal eng PRDs continue to use the full pipeline.

1. Read `Dashboard.md` and `journal/todo.md` for active context.
2. Search Work Drive for an existing PRD by title (MCP `search_files`). If found, read it - this becomes a REVISION: follow the Drive Update Protocol in CLAUDE.md (update in place via file ID, never retitle, add a changelog row).
3. Interview before drafting (Prometheus pattern): for a from-scratch or major-revision PRD, ask the owner sharp scoping questions and wait for answers first. Skip for light edits. Cover the basics (problem, target users, success metric, scope boundaries / what is explicitly NOT included, constraints/dependencies) AND the demand-reality forcing questions below; these are what separate a real PRD from a solution looking for a problem. Ask only the ones the brief leaves genuinely ambiguous; don't interrogate when the answer is already on the table.
   - **Who is desperate?** Name the specific user/team blocked today and how urgent it is for them (must-have now vs nice-to-have). Vague "users want X" is a red flag.
   - **What do they do today instead?** The real baseline to beat is the current workaround (a manual process, a competitor, a spreadsheet), not "nothing." Name it.
   - **Observed or assumed?** Is the problem evidenced (a ticket, Slack thread, meeting, or data point, with the link) or are we assuming it? If assumed, say so explicitly.
   - **Narrowest wedge?** The smallest first slice that delivers value and could ship on its own. Resist bundling.
   - **How will we know it worked?** Restate the success metric as a number or observable behavior change, not "improve UX."
   Then follow the 4-state pipeline in `.agent/skills/prd-pipeline/SKILL.md` (Harvest → Draft → Crucible ≥9.0/10 → Tickets). Delegate State 1 (Harvest) to the `harvester` subagent to keep this context lean. For light edits, draft directly. Template reference: `templates/prd_work.md`.
4. Draft in ENGLISH as a markdown artifact for the owner to review. No em-dashes. Follow the authoring rules at the top of `templates/prd_work.md`: **spec content goes in a TABLE, parallel items go in real bullets, a connected argument goes in one paragraph.** Never write bare consecutive sentence-lines: markdown renders those as one wall-of-text paragraph. "Lists one item per line" means every BULLET gets a line, NOT every sentence. Blank line before every table and every list.
4b. **MCP companion gate (standing rule, 17 Jul 2026).** If the product exposes an API or ships an SDK, the PRD MUST include the "MCP Companion" requirement block from the template: every API/SDK capability ships a matching MCP tool with the same capability, auth, and tenant scoping, versioned and documented in the same release. Capability parity is a release gate, not a later phase. If the product exposes no API and no SDK, drop the block. Do NOT present an API/SDK PRD without it.
5. Before presenting: run `python3 scripts/readability_gate.py --source <path>` (blocks walls of text, missing blank lines, em-dashes), then spawn the `draft-reviewer` subagent (type "PRD"). Fix issues in the SOURCE, then present.
6. After the owner approves, publish with the one command that does convert + diagram embed + format pass + share + restrict-last + verify, in the only order that works:
   `bash scripts/publish_prd.sh --file <path> --title "PRD: ..." [--share Teammate@examplevendor.com]`
   To revise an existing doc, pass `--id <DOC_ID>` instead of `--title`. Never hand-run the individual steps: doing so is how docs shipped as walls of text and one was left publicly shared (16-17 Jul 2026).
7. Register in the Master Product List: `python3 .agent/skills/master-product-list/register_prd.py`
8. Link the Doc URL to the spreadsheet: `python3 .agent/skills/work-link-sync/link_sync.py`
9. Confirm with the file ID + Drive link (Drive Operation Verification - no ID returned means the operation FAILED).

This is synthesis-heavy work: if the session is on a low-tier model, tell the owner before drafting.

Request: $ARGUMENTS
