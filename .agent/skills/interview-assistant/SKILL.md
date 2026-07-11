---
name: Interview Assistant
description: 'Automate candidate pre-interview preparation (CV analysis, question banks, dynamic rubrics) and post-interview assessment (transcript analysis, scorecards, onboarding recommendations) for any job role.'
---

# Interview Assistant Skill

## Purpose
Prepare and execute candidate interview loops and assessments for **any role** (Product, Marketing, Engineering, Design, Sales, Operations, etc.) at Work or Secondary. It generates custom interview plans and post-interview assessments dynamically tailored to the target role's seniority and the candidate's CV.

## Capabilities
1. **CV Parsing & Analysis**: Extract text from CV PDF or Drive files and analyze key strengths to validate and risks to probe.
2. **Dynamic Rubric Building**: Combine 4 core professional dimensions with 3 dynamically generated technical dimensions specific to the target role.
3. **Pre-Interview Plan**: Generate a custom question bank (warm-up, claims verification, custom technical, case study scenario, ways of working) and 3-level evaluation rubric, and upload it as a Google Doc on Drive.
4. **Post-Interview Assessment**: Fetch the Fathom transcript, grade the candidate against the custom rubric, write detailed critiques, and generate actionable onboarding SLAs for the hiring manager, uploaded in-place.

---

## Relationship to Other Skills
* **Google Docs Creator**: Used to upload the finalized interview plans and assessments as editable Google Docs.
* **Work Drive Connector**: Used to update documents in-place (preserving file ID and links) and search Drive.
* **Fathom Connector**: Used to list meetings and download recorded interview transcripts.

---

## Workflow: Pre-Interview Plan

### Step 1: Context Harvesting & CV Extraction
Ask the user for the **Target Role** (and seniority, e.g., Senior PM, Junior Frontend Developer) and **Company Context** (Work, Secondary, ClientB, etc.).
If they provide a CV:
* **Local PDF**: Run the parser script:
  ```bash
  timeout 180s python3 .agent/skills/interview-assistant/scripts/cv_parser.py --file "path/to/cv.pdf"
  ```
* **Drive File ID**: Run the parser script with Drive ID:
  ```bash
  timeout 180s python3 .agent/skills/interview-assistant/scripts/cv_parser.py --drive-id "DRIVE_FILE_ID" --account work
  ```
* **Raw Text**: Read the text directly from the chat prompt.

### Step 2: CV Strength & Risk Analysis
Examine the CV text and identify:
1. **Strengths to Validate**: Specific metrics, relevant past projects, tool/platform experience.
2. **Risks to Probe**: Job tenures (e.g. 5 roles in 3.5 years), execution-only focus, unquantified claims, or lack of strategic autonomy.

### Step 3: Dynamic Rubric Construction
Every interview plan must evaluate the candidate on a 3-level rubric across **7 dimensions**:
1. **Core Dimension 1: Action Bias & Problem-Solving** (Core)
2. **Core Dimension 2: Quantitative Ownership & Honesty** (Core)
3. **Core Dimension 3: Communication & Collaboration** (Core)
4. **Core Dimension 4: Strategic Thinking & OKR Alignment** (Core)
5. **Technical Dimension 5: [Dynamically generated based on target role]**
6. **Technical Dimension 6: [Dynamically generated based on target role]**
7. **Technical Dimension 7: [Dynamically generated based on target role]**

Define the grading criteria (Entry / Junior / Medior / Senior) for each dynamic technical dimension.

### Step 4: Question Bank Design
Draft tailored questions:
* **Warm-up**: Focus on career story and reasons behind job transitions.
* **CV Claims Verification**: Ask for the **step-by-step strategy** behind their CV numbers to verify they were the driver rather than a passive executor.
* **Technical Questions**: Probe platform mechanics, coding architectures, or design frameworks.
* **Case Study Role-Play ("The Resource/Budget Crunch")**: Read them a custom role-play scenario with three complications (performance drop, stakeholder request, resource cut) to evaluate action bias, trade-offs, and composure.
* **Ways of Working**: Probe conflict management, failure ownership, and reporting practices.

### Step 5: Document Creation (Google Doc)
Use the template at `templates/interview_plan_template.md`. Write the document to a local markdown file first (e.g. `Clients/[Client]/[Candidate]_Interview_Plan.md`), then create it as a Google Doc on Work's Drive:
```bash
timeout 180s python3 .agent/skills/gdocs-create/gdocs_create.py create-doc --title "Interview Plan & Assessment Rubric - [Candidate Name] ([Target Role])" --file "path/to/local.md" --account work
```

---

## Workflow: Post-Interview Assessment

### Step 1: Fetch the Interview Transcript
Search Fathom for the recorded Google Meet:
```bash
timeout 180s python3 .agent/skills/fathom-connector/scripts/fathom_client.py --action list --limit 10
```
Retrieve the transcript of the specific meeting ID:
```bash
timeout 180s python3 .agent/skills/fathom-connector/scripts/fathom_client.py --action transcript --id "MEETING_ID"
```

### Step 2: Evaluation & Scorecard Grading
Evaluate the transcript against the 7 dimensions defined in the **Interview Plan**.
* **Verdict Options**: HIRE ([Level]), HIRE (with guardrails), or NO HIRE.
* **Integrity Guardrail**: Any sign of dishonesty or inability to substantiate CV claims on Dimension 2 leads to a **NO HIRE** verdict.
* **Strategic Guardrail**: If they cannot explain the step-by-step strategy details of their past projects, they are strictly classified as an **Executor/Junior** and cannot be hired at a Senior/Lead level.

### Step 3: Document Generation (Assessment)
Use the template at `templates/candidate_assessment_template.md`. Integrate the interviewer's feedback and draft the assessment locally.
Include:
* Executive Summary & Verdict
* Scorecard table (Dimensions 1-7, ratings, justifications)
* Detailed Case & CV Analysis (analyzing how they explained their project step-by-step, their team dynamic, and case role-play performance)
* Actionable onboarding & coaching SLAs for the hiring manager (e.g., prescriptive workflows in first 30 days, technical reviews in first 60 days, limits on strategic autonomy).

### Step 4: In-Place Google Doc Update
Update the existing Drive document **in-place** (preserving the file ID, link, and sharing permissions) using standard Markdown tables (`| ... |` border pipes only, no whitespace-tab tables):
```bash
timeout 180s python3 .agent/skills/work-drive-connector/gdrive_manager.py update --id "DRIVE_FILE_ID" --file "path/to/assessment.md" --convert
```

---

## Rules of Engagement
1. **Role-Agnostic Adaptation**: Tailor all technical questions and rubrics to the specific role and seniority requested by the user. Do not copy PM/Digital Marketing templates blindly.
2. **Step-by-Step Strategic Validation**: During assessment, verify if the candidate explained the step-by-step strategy details of their CV claims. If they didn't, mark it as a gap and limit them to an executor/junior role.
3. **No Em-Dashes**: Use hyphens (`-`) or double hyphens (`--`) exclusively in all documents and reports.
4. **Standard Tables**: Always use standard Markdown tables (`|` pipe borders) for Changelog and Scorecard to ensure correct rendering in Google Docs.
