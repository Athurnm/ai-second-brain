# AI-speed factor: what the research actually supports

> Deep-research run 16 Jul 2026 (99-agent harness: 5 search angles, 15 sources fetched,
> every claim adversarially verified by 3 independent voters against the primary source;
> 2 headline-friendly claims refuted and excluded). Question: how many manual human-hours
> does one hour of delegated AI-agent work substitute, for the work-hours tracker's
> `--ai-speed` factor?

## Bottom line

The exact quantity (manual-hours substituted per autonomous agent-hour, quality-adjusted)
has **no direct RCT-grade measurement as of mid-2026**. The literature brackets it between
a peer-reviewed net floor (~1.1× per task once review/rework is counted) and a
vendor-affiliated gross ceiling (~8-9×). Triangulated per category:

- **Drafting / comms / MoM / synthesis**: ×2.5-3 (confidence: medium)
- **Research / harvesting**: ×2-3 (confidence: low-medium)
- **Coding / dashboards / automation**: ×1-2 (confidence: medium, strong counter-evidence)
- **Blended for the owner's PM mix**: ×2-2.5 conservative-defensible; ×3 = optimistic edge (confidence: medium)

**Tracker default set to ×2.5** (was ×3, assumed). Override per sweep: `--ai-speed N`.

## Verified evidence chain

1. **Assisted (copilot-style) speedups are only 1.15-1.67×** on realistic knowledge work
   (all verified 3-0 against primary sources):
   - Support agents +15% resolutions/hour, N=5,172 field. Brynjolfsson et al., QJE. [arxiv.org/pdf/2304.11771](https://arxiv.org/pdf/2304.11771)
   - BCG consultants +25.1% speed, +40% quality on in-frontier tasks, N=758 RCT. Dell'Acqua et al. 2023. [ssrn 4573321](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4573321)
   - Professional writing: 40% less time, +18% quality, N=453 RCT. Noy & Zhang, Science 2023. [doi:10.1126/science.adh2586](https://www.science.org/doi/10.1126/science.adh2586)
   - Copilot 55.8% faster, but a single contrived greenfield task. Peng et al. 2023. [arxiv 2302.06590](https://arxiv.org/abs/2302.06590)
   These are human-with-AI numbers, NOT delegation ratios — they bound the human-side gain from below.
2. **Net delegation value per task collapses to ~1.1× once review/rework is counted**:
   GDPval (OpenAI, Sept 2025) "AI drafts once, expert reviews and fixes" scenario:
   GPT-5 1.12× faster / 1.18× cheaper vs unaided experts (naive no-review scenario >11×).
   [arxiv 2510.04374](https://arxiv.org/html/2510.04374v1)
3. **Gross ceiling ~8-9 manual-minutes per agent-minute**: Perplexity Computer telemetry,
   N=10,000 matched pairs, Jun 2026 — but vendor-affiliated, LLM-estimated counterfactual
   baselines, zero quality adjustment. Ceiling, not estimate (verified 2-1).
   [arxiv 2606.07489](https://arxiv.org/abs/2606.07489)
4. **Agent-as-teammate (closest to the parallel-sessions pattern)**: replacing a human
   teammate with a GPT-4o agent → ~1.5× output per remaining human, humans shift from
   doing to reviewing, real-money field test showed ~constant quality for text. Ju & Aral,
   MIT, preregistered RCT N=2,234. [arxiv 2503.18238](https://arxiv.org/pdf/2503.18238)
5. **Counter-evidence (why coding gets ×1-2)**: METR RCT 2025 — experienced OSS devs were
   **19% SLOWER** with AI on familiar repos (CI +2..+39%); late-2025 follow-up still no
   measured positive speedup (-18% original cohort, -4% new devs, CIs cross zero).
   Outside-frontier BCG tasks went net-negative (-19pp correctness).
   [arxiv 2507.09089](https://arxiv.org/abs/2507.09089) · [metr.org 2026-02-24](https://metr.org/blog/2026-02-24-uplift-update/)
6. **Self-perception is miscalibrated by ~40pp**: METR devs believed +20% while measured
   -19%; experts predicted +38-39%. Gut-feel factors (including the old ×3) can't anchor this.

## Refuted claims (do NOT cite these)

- "Perplexity 87% time saving = 7.5× substitution ratio" — refuted 0-3 (estimated
  counterfactual baseline, not observed human work).
- "GDPval win-rates (Opus 4.1 47.6% wins+ties) imply majority of delegated outputs need
  substantive rework" — refuted 0-3 (largest loss category was "acceptable but subpar").

## Caveats that stay true regardless of factor

- Capability drift: strongest RCTs are 2023 GPT-4-era; METR used early-2025 tools; ratios
  are model-era specific. Revisit the factor ~quarterly.
- No study covers PM deliverables specifically; PRDs sit near the high-stakes boundary
  where evidence weakens.
- The factor only stays honest if the owner's own review/steering time counts as human time
  (the tracker's `attention_h` approximates this) and parallel streams are counted
  per-stream deliberately (they are — that is what `effective_h` means).
