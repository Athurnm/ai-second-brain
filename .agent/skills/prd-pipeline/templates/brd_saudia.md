# ExampleCo / ExampleProgram BRD Format (Client-Facing Feature Release Doc)

> **When to use this format:** Any BRD or feature doc that will be SHARED WITH the ExampleCo / ExampleProgram client.
> ExampleCo gave explicit feedback (via Teammate, 30 Jun 2026) that our standard BRD is **too technical**. They
> prefer the lightweight, visual, business-outcome "Feature Release Document" style below. This is the
> reference format Teammate shared (ExampleProgram Store feature release + Mega Menu Navigation docs).
>
> **Do NOT use this for internal eng specs.** Internal PRDs still follow `prd_template.md` (Gherkin, data
> models, edge cases, acceptance criteria). This format is the CLIENT-FACING skin: it communicates *what
> ships and why it matters to the user*, not how engineering builds it.

---

## Core principles (what makes it "not technical")

1. **Business-outcome language, not engineering language.** Talk discoverability, conversion, engagement,
   revenue, friction-reduction. NO data schemas, API contracts, Gherkin/Given-When-Then, acceptance
   criteria tables, edge-case matrices, rollback/SLA/monitoring sections, or RACI/sign-off bureaucracy.
2. **Visual-first.** Every feature ends with a **"Representation of …"** placeholder for the actual UI
   (Figma screenshot / mockup). The picture carries the spec; prose stays short. Use `[[SCREENSHOT: …]]`
   placeholders in the markdown so the Mermaid/image embed pass can drop them in.
3. **Scannable.** Short bullets, not paragraphs. One idea per bullet.
4. **Per-feature repeating block** (see structure A) so a multi-feature release reads consistently.
5. English (Work client doc). No em-dashes.

---

## Structure A — Multi-feature release ("Feature Release Document")

Use when one doc covers several enhancements shipping together.

```markdown
# Feature Release Document
## <Product / Surface> Enhancements    e.g. ExampleProgram Marketplace Enhancements

### Release Overview
<1 short paragraph: what this release focuses on and the user journey it improves.>

Below are the <N> features covered in this release:
1. <Feature one>
2. <Feature two>
3. <Feature three>

---

### 1. <Feature Name>

**Problem Statement**
<1-2 sentences: the user pain today.>

**Solution**
<1 sentence: what we introduce.>

**Key Features**
- <capability>
- <capability> (note configurable/time-bound logic in plain terms, e.g. "14 days from launch - configurable")

**User Impact**
- <benefit to the user>
- <benefit to the user>

**Success Metrics**
- <observable business metric: CTR, conversion, drop-off reduction, bounce rate>

**Representation**
[[SCREENSHOT: <what the image shows, e.g. finalised loading screen / Just-In label on PLP>]]

---

### 2. <Feature Name>
<repeat the same block>
```

---

## Structure B — Single feature ("Feature: <name>")

Use when the doc is one feature, especially navigation/UX-heavy ones.

```markdown
# Feature: <Feature Name>

## 1. Objective
Enhance <goal> by introducing:
1. <thing one>
2. <thing two>

<Optional benefit bullets:>
- Increase product visibility
- Enable brand marketing opportunities
- Create potential advertising revenue streams

## 2. Problem Statement
Currently, <current behaviour> creates challenges:
- <pain>
- <pain>
<1 sentence on how the solution reduces friction.>

## 3. Goals
- <business goal>
- <business goal>

## 4. UI/UX Navigation - Desktop
<Step label, e.g. "4a) Customer navigates the Mega Menu from the header">
[[SCREENSHOT: <desktop view>]]
<1-2 sentences of plain-language annotation under each screenshot.>

## 5. UI/UX Navigation - Mobile
<Mobile equivalent>
[[SCREENSHOT: <mobile view>]]
```

---

## Choosing A vs B
- **A** = a release bundling multiple discrete features → repeating Problem/Solution/Impact/Metrics block.
- **B** = a single feature where the *navigation/UX flow* is the point → Objective/Problem/Goals + annotated
  Desktop & Mobile walkthroughs.

When unsure, ask You which shape fits; default to A for a release, B for a single navigation/UX feature.
