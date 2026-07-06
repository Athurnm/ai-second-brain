# agy-bridge

Call **non-Claude models as a co-processor** from inside this Claude Code harness, **prove the
cost savings**, and route by **model expertise + time of day**. Two backends:
- **agy**: Gemini 3.5 Flash / Gemini 3.1 Pro / GPT-OSS 120B via the Antigravity CLI.
- **zai**: GLM 5.2 via the z.ai GLM Coding Plan subscription (Anthropic-compatible endpoint).

The main session stays on real Anthropic Claude; only the bridge subprocess/request hits the
other model. Every task ends in a `claude_fallback` tier so quality never silently drops.

## Tasks & capabilities

A task resolves a **capability** → an ordered candidate list in `models.json` (an explicit
`chain` still overrides). Default mapping:

| `--task` | capability | chain (head → fallback) | claude_fallback |
| :-- | :-- | :-- | :-- |
| `harvest` | bulk-cheap | Gemini 3.5 Flash (High) → glm-5.2 → Gemini 3.1 Pro (Low) | haiku |
| `critic` | cross-lineage | glm-5.2 → GPT-OSS 120B → Gemini 3.1 Pro (High) | sonnet |
| `research` | reasoning | glm-5.2 → Gemini 3.1 Pro (High) → GPT-OSS 120B | main-loop |

Capability candidates are grounded in model strengths/context: GPT-OSS (128K) is excluded from
long-context/bulk; GLM-5.2 (cheap + strong reasoning) leads reasoning/critic; Flash (1M, fast)
leads bulk. `image` is NOT a bridge task → use the `gemini-image` skill.

## Cost / savings (the primary point)

Every attempt is logged to `dashboard-data/agy_usage_log.jsonl` with tokens + latency + cost.
**Nothing is treated as free.** Each model has a per-Mtok rate in `models.json` `model_prices`
(subscription backends included). For each answered call:
- `actual_usd` = tokens × the **ran model's** $/Mtok
- `counterfactual_usd` = tokens × the **claude_fallback tier's** $/Mtok (what Claude would cost)
- `saving_usd` = counterfactual − actual

Token counts: **z.ai = exact** (API `usage`); **agy = estimated** (CLI exposes none; chars/4,
flagged). GLM price is a seed estimate until confirmed at z.ai (flagged `estimated`).

- `python3 run.py --report` → savings by task + model, with the flat subscription fees shown as
  context (never folded into per-call cost).
- Dashboard: `python3 dashboard/server.py` → `localhost:3737` → **"💸 Cost / Savings" tab** reads
  `GET /api/agy-cost` (the `agy_cost_summary.json` that every call rolls up).

⚠️ **Decision locked (2026-07-04):** cost logs show Gemini 3.5 Flash ($1.50/$9) is pricier than
Haiku ($1/$5) per-call, and glm-5.2 ($0.60/$2.20) would save ~50%. You still keeps **Flash at
the head of `bulk-cheap`**: his Gemini subscription is rarely used, so utilizing idle subscription
capacity beats per-call savings. Do NOT re-secondary this to GLM based on `agy_usage_log` alone (see
`_bulk_cheap_note` in models.json). glm-5.2 stays as fallback #2.

## Time-of-day routing

`time_routing` in `models.json` is **`on`** (soft-demote: a backend in its peak window sinks to
the back of its chain but is still tried before the Claude fallback). It acts ONLY on VERIFIED
windows:
- **zai / GLM: VERIFIED** from the z.ai dashboard. GLM-5.2 + GLM-5-Turbo share one quota and burn
  it **3x during peak (14:00-18:00 UTC+8 = 13:00-17:00 WIB)**, **2x off-peak**, currently **1x
  off-peak through end of Sep 2026** (promo). So `peak_wib.zai = [[13,17]]`: during 13:00-17:00 WIB
  GLM is demoted (GPT-OSS leads critic, Gemini Pro leads research); the rest of the day GLM leads
  (cheap + strong). `--doctor` prints the live GLM quota multiplier; each GLM call logs `quota_mult`.
  After Sep 2026 set `offpeak_mult_after_promo` (2x) behaviour by editing the `quota` block.
- **agy / Gemini, GPT-OSS: UNVERIFIED** → `peak_wib.agy = []` (empty), so agy is NEVER demoted
  until measured. `python3 run.py --analyze` aggregates the SAME telemetry log → median latency +
  error rate per (backend × WIB hour) and suggests peak hours; once stable, fill `peak_wib.agy`.

Optional `probe.py` (run hourly via `/loop` or `schedule`) fills idle hours with a tiny prompt; its
rows feed `--analyze` only, never the cost report. `AGY_BRIDGE_FAKE_WIB_HOUR=NN` mocks the hour;
`--no-time-routing` ignores routing for one run.

## Setup

- **agy**: Google/Antigravity OAuth (done 2026-06-24). If `--doctor` shows `authenticated: NO`,
  run `agy` once interactively; re-run `agy models` and sync `known_agy_models` if the list changed.
  agy SILENTLY routes an unknown id to a default → run.py refuses ids not in `known_agy_models`.
  agy auth is flaky per-call → run.py retries once on an auth blip.
- **zai**: subscribe at https://z.ai/subscribe, `cp token.env.example token.env`, paste into
  `ZAI_API_TOKEN`. Real Anthropic-style server → errors on a bad model id (no silent fallback).

## Usage

```bash
python3 .agent/skills/agy-bridge/run.py --task harvest --prompt-file transcript.txt
python3 .agent/skills/agy-bridge/run.py --task critic  --prompt "Attack this plan: ..."
python3 .agent/skills/agy-bridge/run.py --task research --model glm-5.2 --backend zai --prompt "..."
python3 .agent/skills/agy-bridge/run.py --task harvest --list      # resolved (+advisory) chain
python3 .agent/skills/agy-bridge/run.py --report                   # cost / savings
python3 .agent/skills/agy-bridge/run.py --analyze                  # latency/error per backend×hour
python3 .agent/skills/agy-bridge/run.py --doctor                   # auth, prices, chains, routing
```

## The fallback contract (do not violate)

Exit `0` → stdout is the model's answer. Exit `3` → stdout is a JSON sentinel
`{"status":"fallback_to_claude","claude_fallback":"<tier>"}`; the calling Claude agent MUST do the
work itself at that tier, never fabricating a result or pretending the bridge succeeded.
