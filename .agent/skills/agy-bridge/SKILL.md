# agy-bridge

## OPTIONAL - Claude-only mode is fully supported

This bridge is an **optional cost saver, not a dependency**. If you have no subscription to any
non-Claude model (no Antigravity `agy` CLI, no z.ai GLM Coding Plan, no Kimi Code), you don't need
to set anything up here: every caller resolves a `claude_fallback` tier per task and every call
into the bridge falls back to that Claude tier (haiku/sonnet/main-loop per capability)
automatically. `run.py` detects the no-backend case up front and returns the same
`fallback_to_claude` sentinel the normal fallback path uses, with no network calls and no per-model
failure noise. Run `--doctor` any time to confirm you're in Claude-only mode and see what
configuring a backend would take. The rest of this file describes the (optional) cost-saving setup.

## What this is

Call **non-Claude models as a co-processor** from inside this Claude Code harness, **prove the
cost savings**, and route by **model expertise + time of day**. Two backends:
- **agy**: Gemini 3.5 Flash / Gemini 3.1 Pro / GPT-OSS 120B via the Antigravity CLI.
- **zai**: GLM 5.2 via the z.ai GLM Coding Plan. **RETIRED 2026-07-27** (subscription ended; live
  calls error out). Removed from every chain, backend definition kept for cost-history replay and
  a one-line restore. Do NOT pass `--backend zai` or re-add it to a chain without a passing
  `--doctor` probe first.

The main session stays on real Anthropic Claude; only the bridge subprocess/request hits the
other model. Every task ends in a `claude_fallback` tier so quality never silently drops.

## Tasks & capabilities

A task resolves a **capability** → an ordered candidate list in `models.json` (an explicit
`chain` still overrides). Default mapping:

| `--task` | capability | chain (head → fallback) | claude_fallback |
| :-- | :-- | :-- | :-- |
| `harvest` | bulk-cheap | Gemini 3.5 Flash (High) → Gemini 3.1 Pro (Low) | haiku |
| `critic` | cross-lineage | GPT-OSS 120B → Gemini 3.1 Pro (High) → kimi-latest | sonnet |
| `research` | reasoning | Gemini 3.1 Pro (High) → GPT-OSS 120B | main-loop |
| `draft` | draft | Gemini 3.5 Flash (High) → Gemini 3.1 Pro (High) | sonnet |

Capability candidates are grounded in model strengths/context: GPT-OSS (128K) is excluded from
long-context/bulk; Flash (1M, fast) leads bulk and draft; Gemini Pro leads reasoning; GPT-OSS
leads critic for lineage diversity against the Gemini-heavy rest of the stack. `image` is NOT a bridge task → use the `gemini-image` skill.

## Cost / savings (the primary point)

Every attempt is logged to `dashboard-data/agy_usage_log.jsonl` with tokens + latency + cost.
**Nothing is treated as free.** Each model has a per-Mtok rate in `models.json` `model_prices`
(subscription backends included). For each answered call:
- `actual_usd` = tokens × the **ran model's** $/Mtok
- `counterfactual_usd` = tokens × the **claude_fallback tier's** $/Mtok (what Claude would cost)
- `saving_usd` = counterfactual − actual

Token counts: **agy = estimated** (CLI exposes none; chars/4, flagged). Historical z.ai rows in the
log carry exact counts from the API `usage` field; they stay valid for replay.

⚠️ **Since the z.ai retirement every live backend is `agy`, which is flat-rate**, so `actual_usd`
is $0 on essentially every new row and `saving_usd` equals the full Claude counterfactual. Read
`--report` as "Claude quota avoided", not as money saved against a metered bill.

**Flat-rate backends (agy):** the owner pays a flat Antigravity subscription, so a call to `agy` has
$0 marginal cost. `models.json` `backends.agy.flat_rate: true` marks this; `run.py` records
`actual_usd=0` + `cost_model:"subscription_flat"` for those rows and keeps the would-be per-token
figure in `metered_equiv_usd` so it isn't lost. `saving_usd` for a flat-rate call is the full
`counterfactual_usd` (what the same work would have cost on Claude), not `counter - metered`.
zai/kimi stay metered (real per-token quota, `zai_quota_mult`/promo windows can run out) unless
their own `flat_rate` flag is confirmed later. `--report`/`--analyze` label backends
flat-rate/metered and print `claude_quota_saved_usd` (sum of `counterfactual_usd` routed to
flat-rate backends). Old log rows (pre-fix, no `cost_model`) are reinterpreted correctly at
read time in `aggregate()` from the backend's current `flat_rate` flag, not from stored fields.

- `python3 run.py --report` → savings by task + model, with the flat subscription fees shown as
  context (never folded into per-call cost).
- Dashboard: `python3 dashboard/server.py` → `localhost:3737` → **"💸 Cost / Savings" tab** reads
  `GET /api/agy-cost` (the `agy_cost_summary.json` that every call rolls up).

⚠️ **Decision locked (2026-07-04), now moot on the cost axis:** cost logs showed Gemini 3.5 Flash
($1.50/$9) pricier per-call than Haiku ($1/$5), with glm-5.2 ($0.60/$2.20) ~50% cheaper. the owner
kept **Flash at the head of `bulk-cheap`** anyway, because his Gemini subscription was otherwise
idle and utilizing it beat per-call savings. With z.ai retired 2026-07-27 the cheaper alternative
is gone, so Flash leads on the original rationale alone. See `_bulk_cheap_note` in models.json.

## Time-of-day routing

`time_routing` in `models.json` is **`on`** (soft-demote: a backend in its peak window sinks to
the back of its chain but is still tried before the Claude fallback). It acts ONLY on VERIFIED
windows:
- **zai / GLM: RETIRED 2026-07-27.** The `peak_wib.zai = [[13,17]]` window and the quota-multiplier
  block are now dead config, kept only so historical log rows replay correctly. Nothing routes to
  zai any more, so time routing has no live effect on any chain.
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
- **zai**: RETIRED 2026-07-27, no setup needed. To restore: re-subscribe at https://z.ai/subscribe,
  refresh `ZAI_API_TOKEN` in `token.env`, confirm with `--doctor`, then clear `backends.zai.retired`
  and re-add the candidate to the chains you want it in.

## Usage

```bash
python3 .agent/skills/agy-bridge/run.py --task harvest --prompt-file transcript.txt
python3 .agent/skills/agy-bridge/run.py --task critic  --prompt "Attack this plan: ..."
python3 .agent/skills/agy-bridge/run.py --task research --model "Gemini 3.1 Pro (High)" --prompt "..."
python3 .agent/skills/agy-bridge/run.py --task harvest --list      # resolved (+advisory) chain
python3 .agent/skills/agy-bridge/run.py --report                   # cost / savings
python3 .agent/skills/agy-bridge/run.py --analyze                  # latency/error per backend×hour
python3 .agent/skills/agy-bridge/run.py --doctor                   # auth, prices, chains, routing
```

## The fallback contract (do not violate)

Exit `0` → stdout is the model's answer. Exit `3` → stdout is a JSON sentinel
`{"status":"fallback_to_claude","claude_fallback":"<tier>"}`; the calling Claude agent MUST do the
work itself at that tier, never fabricating a result or pretending the bridge succeeded.
