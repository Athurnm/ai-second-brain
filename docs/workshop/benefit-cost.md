# Buy Every Tool Separately vs Build Your Own: The Cost Math

> Companion page for the AI Second Brain workshop. Prices are mainstream paid-tier list prices as of July 2026 and an assumed rate of Rp 16,300/USD. Prices change; the shape of the argument does not.

## The "do it all" AI stack, bought as separate subscriptions

A knowledge worker who also creates content ends up paying for one tool per job. Here is a realistic stack, one tool per capability, no redundant duplicates:

| Capability | Representative tool | Plan | List price / month |
| :--- | :--- | :--- | ---: |
| General assistant | ChatGPT Plus | Plus | $20 |
| Meeting notes | Otter.ai | Pro | $17 |
| Automation between apps | Zapier | Professional | $30 |
| Docs and knowledge base AI | Notion AI | Business (AI bundled) | $20 |
| AI presentations | Gamma | Plus | $10 |
| Image generation and editing | Midjourney | Standard | $30 |
| Short-form video clipper | Opus Clip | Pro | $29 |
| Video editing | Descript | Creator | $35 |
| Avatar / script-to-video | HeyGen | Creator | $29 |
| **Total** | | | **$220 ≈ Rp 3,586,000** |

A few notes on the numbers:

1. **Meeting tools are substitutes, not additions.** Otter (~$17) and Fireflies (~$18) do the same job. You pick one. This table counts one.
2. **The expensive part is media.** Image, clipper, video editing, and avatar video alone are $123/month. This is exactly where separate subscriptions pile up for anyone making content.
3. **Prices shown are month-to-month list.** Most of these are ~20-35% cheaper billed annually, but so is Claude. The gap holds.

Beyond price, three structural problems:

1. **The tools do not know each other.** Your meeting notes tool cannot see your todo list. Your clipper cannot read your brand rules. Every tool holds a fragment of your context, and you are the integration layer.
2. **Each tool is someone else's roadmap.** You get the features they ship, at the pace they ship them.
3. **The count only grows.** Every new need means another subscription, another login, another silo.

## The second-brain approach

| Item | What it covers | Price / month |
| :--- | :--- | ---: |
| Claude Pro | The model + Claude Code agent. Runs every skill in this repo: meeting notes, reports, drafts, automation, docs, diagrams, images, video, data queries | $20 ≈ Rp 326,000 |
| AI Circle membership | Community, monthly live session, growing skill library, help when you are stuck | Rp 95,000 |
| **Total** | | **≈ Rp 421,000** |

**Savings: roughly Rp 3,165,000 per month (~88%)** against the nine-tool stack above.

The structural differences matter more than the savings:

1. **One context.** Your meetings, todos, documents, posts, and data live in one workspace the AI reads together. The report knows what the meeting decided. The post knows your brand rules.
2. **Tools on demand.** A "tool" here is a markdown file plus, at most, a small script. When a new need appears, you build the skill in an afternoon instead of buying another subscription.
3. **It remembers.** Correct it once and it keeps the correction across every future session. A separate tool cannot learn your preferences; your second brain does.
4. **You own it.** Local files, open template, no vendor deciding what your workflow looks like.

## Honest caveats

- The second brain automates the *AI layer* of these jobs: clipping, captions, image generation, drafting, automation, notes, reports, data pulls. For deep manual craft (frame-by-frame color grading, complex motion design) a dedicated editor still has its place. The math favors the second brain the moment your needs span two or more of the tools above, which for most people they already do.
- Claude Pro has usage limits; very heavy daily use may want the higher tier ($100/mo), which still undercuts a grown separate-tool stack.
- Level 1+ connectors need a one-time setup effort (Google OAuth is the heaviest step, 1-2 hours).
- Some media capabilities (image generation, avatar video) run on metered APIs billed per use, which for occasional use costs far less than a full monthly subscription to a dedicated tool.
