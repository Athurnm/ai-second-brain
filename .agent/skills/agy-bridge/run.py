#!/usr/bin/env python3
"""agy-bridge: call non-Claude models (Gemini / GPT-OSS via the Antigravity `agy` CLI,
GLM via the z.ai GLM Coding Plan) as a co-processor for a Claude Code agent, and PROVE
the cost savings.

Why this exists: Claude Code subagents can only run Claude tiers in `model:` frontmatter,
and pointing the whole session at z.ai would turn every call into GLM. This bridge calls
each backend in a scoped subprocess/request, so the main session stays on real Claude.

Three layers:
  1. COST TELEMETRY (primary): every attempt is logged with tokens + latency + per-Mtok
     cost + the Claude counterfactual (what the same work would cost on the task's
     claude_fallback tier). Powers `--report` and the localhost:3737 "Cost / Savings" tab.
  2. CAPABILITY routing: a task resolves a capability (bulk-cheap / reasoning /
     cross-lineage / long-context) -> ordered candidate models in models.json.
  3. TIME routing (measured, phased): `time_routing` off|advisory|on. 'advisory' logs the
     reorder it WOULD do (unverified peak_wib seed) but applies nothing; secondary to 'on' after
     `--analyze` confirms peak windows from the SAME telemetry log.

Cost contract: subscription backends are NOT free. Every model has a per-Mtok rate in
models.json `model_prices`; cost = tokens x rate for ALL backends.
Fallback contract: exit 0 = stdout is the model answer; exit 3 = stdout is a
{"status":"fallback_to_claude","claude_fallback":"<tier>"} sentinel the caller MUST honor.

Usage:
  run.py --task harvest --prompt-file x.txt        # run, logging cost
  run.py --task critic  --prompt "..."             # cross-model critic
  run.py --task research --model glm-5.2 --backend zai --prompt "..."   # force one model
  run.py --task harvest --list                     # show resolved (+reordered) chain
  run.py --report                                  # cost / savings summary by task
  run.py --analyze                                 # latency + error rate per backend x WIB hour
  run.py --doctor                                  # auth, prices, chains, routing status
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "models.json")
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DATA_DIR = os.environ.get("AGY_BRIDGE_DATA_DIR", os.path.join(REPO_ROOT, "dashboard-data"))
LOG_PATH = os.path.join(DATA_DIR, "agy_usage_log.jsonl")
SUMMARY_PATH = os.path.join(DATA_DIR, "agy_cost_summary.json")
WIB = timezone(timedelta(hours=7))

AUTH_MARKERS = (
    "authentication required", "please sign in", "please visit the url to log in",
    "authentication timed out", "waiting for authentication",
)
UNAVAIL_MARKERS = (
    "model not found", "unknown model", "not available", "unsupported model", "invalid model",
)

# ---------- config + time ----------

def load_config():
    with open(CONFIG, "r", encoding="utf-8") as fh:
        return json.load(fh)

def wib_now():
    """Return (hour:int, iso_ts:str) in WIB. Honors AGY_BRIDGE_FAKE_WIB_HOUR for tests."""
    try:
        now = datetime.now(WIB)
    except Exception:  # pragma: no cover
        out = subprocess.run(["date", "+%H|%Y-%m-%dT%H:%M:%S"], capture_output=True, text=True,
                             env={**os.environ, "TZ": "Asia/Jakarta"})
        h, _, ts = out.stdout.strip().partition("|")
        return int(h or 0), ts
    hour = now.hour
    fake = os.environ.get("AGY_BRIDGE_FAKE_WIB_HOUR")
    if fake not in (None, ""):
        hour = int(fake) % 24
    return hour, now.isoformat(timespec="seconds")

# ---------- pricing ----------

def model_price(model, cfg):
    """Return ([in_per_mtok, out_per_mtok], estimated:bool) for a ran model."""
    mp = cfg.get("model_prices", {})
    by_model = mp.get("by_model", {})
    by_family = mp.get("by_family", {})
    est_keys = mp.get("estimated_models", [])
    if model in by_model:
        return by_model[model], (model in est_keys)
    for fam, price in by_family.items():
        if fam.lower() in model.lower():
            return price, (fam in est_keys or model in est_keys)
    return None, True  # unknown -> flagged, treated as 0 cost

def claude_tier_price(tier, cfg):
    tiers = cfg.get("model_prices", {}).get("claude_tiers", {})
    return tiers.get(tier) or tiers.get("main-loop") or [0, 0]

def compute_cost(in_tok, out_tok, ran_model, fallback_tier, cfg):
    """Return dict of actual / counterfactual / saving USD using per-Mtok rates for ALL."""
    ap, est = model_price(ran_model, cfg)
    ap = ap or [0, 0]
    cp = claude_tier_price(fallback_tier, cfg)
    actual = (in_tok * ap[0] + out_tok * ap[1]) / 1_000_000.0
    counter = (in_tok * cp[0] + out_tok * cp[1]) / 1_000_000.0
    return {
        "actual_usd": round(actual, 6),
        "counterfactual_usd": round(counter, 6),
        "saving_usd": round(counter - actual, 6),
        "price_estimated": est,
    }

# ---------- chain resolution + time routing ----------

def resolve_task(cfg, task):
    tasks = cfg.get("tasks", {})
    if task not in tasks:
        sys.stderr.write(f"[agy-bridge] unknown task '{task}'. Known: {', '.join(tasks)}\n")
        sys.exit(2)
    return tasks[task]

def chain_for_task(spec, cfg):
    """Explicit chain wins (back-compat); else resolve from the task's capability."""
    if spec.get("chain"):
        return list(spec["chain"])
    cap = spec.get("capability")
    caps = cfg.get("capabilities", {})
    entry = caps.get(cap)
    if isinstance(entry, list):
        return list(entry)
    sys.stderr.write(f"[agy-bridge] task has no chain and capability '{cap}' is not a list\n")
    sys.exit(2)

def normalize_entry(entry):
    if isinstance(entry, dict):
        return entry.get("backend", "agy"), entry["model"]
    return "agy", entry

def in_peak(backend, hour, cfg):
    for lo, hi in cfg.get("peak_wib", {}).get(backend, []):
        if lo <= hour < hi:
            return True
    return False

def zai_quota_mult(backend, hour, ts, cfg):
    """z.ai GLM quota multiplier: 3x in peak, else 1x (promo through promo_until) / 2x after."""
    if backend != "zai":
        return 1
    q = cfg.get("backends", {}).get("zai", {}).get("quota", {})
    if not q:
        return 1
    if in_peak("zai", hour, cfg):
        return q.get("peak_mult", 3)
    date_str = (ts or "")[:10]
    promo = q.get("promo_until", "")
    if promo and date_str and date_str <= promo:
        return q.get("offpeak_mult", 1)
    return q.get("offpeak_mult_after_promo", 2)

def apply_time_routing(chain, cfg, mode, hour):
    """Stable-sort so off-peak backends float to the front. Returns (chain_to_run, note)."""
    if mode == "off":
        return chain, None
    decorated = []
    for i, entry in enumerate(chain):
        backend, model = normalize_entry(entry)
        decorated.append((1 if in_peak(backend, hour, cfg) else 0, i, entry, backend, model))
    reordered = [d[2] for d in sorted(decorated, key=lambda d: (d[0], d[1]))]
    peaked = [f"{m}[{b}]" for p, _, _, b, m in decorated if p]
    if not peaked or reordered == chain:
        note = None
    else:
        order = " -> ".join(f"{m}[{b}]" for b, m in (normalize_entry(e) for e in reordered))
        verb = "would-run (advisory, not applied)" if mode == "advisory" else "reordered"
        note = f"WIB {hour}h: in-peak demoted [{', '.join(peaked)}]; {verb}: {order}"
    if mode == "advisory":
        return chain, note  # log only, apply nothing
    return reordered, note  # "on"

# ---------- backends ----------

def load_token(cfg, backend):
    spec = cfg.get("backends", {}).get(backend, {})
    env = spec.get("token_env")
    if env and os.environ.get(env):
        return os.environ[env].strip()
    tf = spec.get("token_file")
    if tf:
        path = tf if os.path.isabs(tf) else os.path.join(HERE, tf)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == env:
                        return v.strip().strip('"').strip("'")
    return None

def run_agy(model, prompt, timeout, known):
    """Returns (ok, text, reason, meta). agy has no usage field -> tokens estimated."""
    meta = {"latency_ms": 0, "in_tok": 0, "out_tok": 0, "tokens_estimated": True}
    if known and model not in known:
        return False, "unknown-id (not in known_agy_models)", "unknown-id", meta
    cmd = ["agy", "-p", prompt, "--model", model, "--print-timeout", f"{timeout}s", "--sandbox"]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
    except subprocess.TimeoutExpired:
        meta["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return False, f"timeout after {timeout}s", "timeout", meta
    meta["latency_ms"] = int((time.monotonic() - t0) * 1000)
    out = (proc.stdout or "").strip()
    low = (out + "\n" + (proc.stderr or "")).lower()
    if any(m in low for m in AUTH_MARKERS):
        return False, "transient auth blip", "auth", meta
    if any(m in low for m in UNAVAIL_MARKERS):
        return False, "model unavailable", "unavailable", meta
    if proc.returncode != 0 and not out:
        return False, (proc.stderr or "non-zero exit").strip(), "error", meta
    if not out:
        return False, "empty output", "empty", meta
    meta["in_tok"] = max(1, len(prompt) // 4)   # estimate
    meta["out_tok"] = max(1, len(out) // 4)
    return True, out, "ok", meta

def run_zai(model, prompt, timeout, cfg):
    """Returns (ok, text, reason, meta). z.ai returns EXACT usage."""
    meta = {"latency_ms": 0, "in_tok": 0, "out_tok": 0, "tokens_estimated": False}
    spec = cfg.get("backends", {}).get("zai", {})
    base = (spec.get("base_url") or "").rstrip("/")
    token = load_token(cfg, "zai")
    if not base:
        return False, "no zai base_url", "error", meta
    if not token:
        return False, "no zai token (z.ai/subscribe; set ZAI_API_TOKEN or token.env)", "no-credential", meta
    body = json.dumps({
        "model": model,
        "max_tokens": int(spec.get("max_tokens", 2048)),
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(base + "/v1/messages", data=body, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("x-api-key", token)
    req.add_header("authorization", f"Bearer {token}")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        meta["latency_ms"] = int((time.monotonic() - t0) * 1000)
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            return False, f"zai auth {e.code}: {detail}", "auth", meta
        if e.code in (400, 404):
            return False, f"zai model/request {e.code}: {detail}", "unavailable", meta
        return False, f"zai http {e.code}: {detail}", "error", meta
    except Exception as e:
        meta["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return False, f"zai request failed: {e}", "error", meta
    meta["latency_ms"] = int((time.monotonic() - t0) * 1000)
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    usage = data.get("usage") or {}
    meta["in_tok"] = int(usage.get("input_tokens", 0)) or max(1, len(prompt) // 4)
    meta["out_tok"] = int(usage.get("output_tokens", 0)) or max(1, len(text) // 4)
    meta["tokens_estimated"] = not usage
    if not text:
        return False, "zai empty content", "empty", meta
    return True, text, "ok", meta

def run_entry(backend, model, prompt, timeout, cfg, known):
    if backend == "agy":
        return run_agy(model, prompt, timeout, known)
    if backend == "zai":
        return run_zai(model, prompt, timeout, cfg)
    return False, f"unknown backend '{backend}'", "error", {"latency_ms": 0, "in_tok": 0, "out_tok": 0, "tokens_estimated": True}

# ---------- telemetry ----------

def log_call(row):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

def read_log():
    rows = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return rows

def aggregate(rows):
    """Cost/usage summary from log rows (ok answers only carry tokens/cost)."""
    by_task, by_model, by_day = {}, {}, {}
    totals = {"calls": 0, "answers": 0, "in_tok": 0, "out_tok": 0,
              "actual_usd": 0.0, "counterfactual_usd": 0.0, "saving_usd": 0.0}
    for r in rows:
        if r.get("task") == "probe":
            continue  # probe rows feed --analyze (latency) only, never the cost report
        totals["calls"] += 1
        if not r.get("ok"):
            continue
        totals["answers"] += 1
        t = r.get("task", "?"); m = f"{r.get('model','?')}[{r.get('backend','?')}]"; d = (r.get("ts_wib", "")[:10] or "?")
        a, c, s = r.get("actual_usd", 0), r.get("counterfactual_usd", 0), r.get("saving_usd", 0)
        it, ot = r.get("input_tokens", 0), r.get("output_tokens", 0)
        for bucket, key in ((by_task, t), (by_model, m), (by_day, d)):
            b = bucket.setdefault(key, {"answers": 0, "in_tok": 0, "out_tok": 0,
                                        "actual_usd": 0.0, "counterfactual_usd": 0.0, "saving_usd": 0.0})
            b["answers"] += 1; b["in_tok"] += it; b["out_tok"] += ot
            b["actual_usd"] += a; b["counterfactual_usd"] += c; b["saving_usd"] += s
        for k, v in (("in_tok", it), ("out_tok", ot), ("actual_usd", a),
                     ("counterfactual_usd", c), ("saving_usd", s)):
            totals[k] += v
    for bucket in (by_task, by_model, by_day):
        for b in bucket.values():
            for k in ("actual_usd", "counterfactual_usd", "saving_usd"):
                b[k] = round(b[k], 4)
            b["saving_pct"] = round(100 * b["saving_usd"] / b["counterfactual_usd"], 1) if b["counterfactual_usd"] else 0.0
    for k in ("actual_usd", "counterfactual_usd", "saving_usd"):
        totals[k] = round(totals[k], 4)
    totals["saving_pct"] = round(100 * totals["saving_usd"] / totals["counterfactual_usd"], 1) if totals["counterfactual_usd"] else 0.0
    return {"totals": totals, "by_task": by_task, "by_model": by_model, "by_day": by_day}

def write_summary(cfg):
    summary = aggregate(read_log())
    summary["subscriptions"] = {k: v for k, v in cfg.get("subscriptions", {}).items() if not k.startswith("_")}
    _, ts = wib_now()
    summary["generated_wib"] = ts
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    return summary

# ---------- reports ----------

def cmd_report(cfg):
    s = write_summary(cfg)
    t = s["totals"]
    print("=== agy-bridge cost / savings ===")
    print(f"calls={t['calls']} answers={t['answers']}  tokens in/out={t['in_tok']}/{t['out_tok']}")
    print(f"actual ${t['actual_usd']}  vs  Claude-counterfactual ${t['counterfactual_usd']}  ->  SAVED ${t['saving_usd']} ({t['saving_pct']}%)")
    print("\nby task:")
    for k, b in sorted(s["by_task"].items()):
        print(f"  {k:9s} answers={b['answers']:4d}  actual ${b['actual_usd']:<9} counter ${b['counterfactual_usd']:<9} saved ${b['saving_usd']} ({b['saving_pct']}%)")
    print("\nby model:")
    for k, b in sorted(s["by_model"].items(), key=lambda kv: -kv[1]["saving_usd"]):
        print(f"  {k:34s} answers={b['answers']:4d}  saved ${b['saving_usd']} ({b['saving_pct']}%)")
    subs = s.get("subscriptions", {})
    if subs:
        total = sum(subs.values())
        print(f"\nflat subscriptions (context, not per-call): {subs}  = ${total}/mo")
        print(f"net vs subscriptions this log: saved ${t['saving_usd']} - ${total}/mo fees")
    print(f"\nlog: {LOG_PATH}")

def cmd_analyze(cfg):
    rows = read_log()
    if not rows:
        print("no telemetry yet. Run some --task calls (or probe.py) first.")
        return
    cell = {}  # (backend, hour) -> {lat:[], err:int, n:int}
    for r in rows:
        b = r.get("backend", "?"); h = r.get("wib_hour", -1)
        c = cell.setdefault((b, h), {"lat": [], "err": 0, "n": 0})
        c["n"] += 1
        if r.get("ok"):
            c["lat"].append(r.get("latency_ms", 0))
        else:
            c["err"] += 1
    print("=== latency (median ms) + error-rate per backend x WIB hour ===")
    backends = sorted({b for b, _ in cell})
    for b in backends:
        print(f"\n{b}:")
        lats = []
        for h in range(24):
            c = cell.get((b, h))
            if not c:
                continue
            med = int(statistics.median(c["lat"])) if c["lat"] else None
            if med is not None:
                lats.append(med)
            errpct = round(100 * c["err"] / c["n"]) if c["n"] else 0
            print(f"  {h:02d}h  n={c['n']:3d}  median={med if med is not None else '-':>6}ms  err={errpct}%")
        if lats:
            base = statistics.median(lats)
            hot = []
            for h in range(24):
                c = cell.get((b, h))
                if c and c["lat"] and statistics.median(c["lat"]) > 1.5 * base:
                    hot.append(h)
            print(f"  baseline median={int(base)}ms; suggested peak hours (>1.5x): {hot or 'none yet'}")
    print("\n(Once these stabilize, copy peak hours into peak_wib in models.json and set time_routing:'on'.)")

# ---------- doctor ----------

def doctor(cfg):
    hour, ts = wib_now()
    mode = cfg.get("time_routing", "off")
    print(f"WIB now: {ts} (hour {hour})   time_routing: {mode}")
    has = shutil.which("agy")
    print(f"agy on PATH: {'yes' if has else 'NO'}")
    if has:
        authed = False
        for _ in range(2):
            try:
                p = subprocess.run(["agy", "-p", "Reply with exactly: PONG", "--print-timeout", "12s"],
                                   capture_output=True, text=True, timeout=25)
                blob = (p.stdout + p.stderr).lower()
                authed = ("pong" in blob) and not any(m in blob for m in ("authentication", "sign in", "oauth", "log in"))
            except subprocess.TimeoutExpired:
                authed = False
            if authed:
                break
        print(f"agy authenticated: {'yes' if authed else 'NO -> run `agy` once interactively'}")
    print(f"zai token: {'present' if load_token(cfg, 'zai') else 'MISSING -> z.ai/subscribe, set ZAI_API_TOKEN or token.env'}")
    known = cfg.get("known_agy_models", [])
    print(f"\nper-backend peak status @WIB {hour}h: ", end="")
    print(", ".join(f"{b}={'PEAK' if in_peak(b, hour, cfg) else 'off'}" for b in cfg.get("peak_wib", {}) if not b.startswith("_")))
    print(f"zai/GLM quota multiplier now: {zai_quota_mult('zai', hour, ts, cfg)}x (3x peak 13-17 WIB, 1x off-peak through Sep)")
    print("\neffective chains (capability -> reordered):")
    for task, spec in cfg.get("tasks", {}).items():
        base = chain_for_task(spec, cfg)
        run_chain, note = apply_time_routing(base, cfg, mode if mode != "off" else "off", hour)
        labels = []
        for entry in run_chain:
            b, m = normalize_entry(entry)
            flag = " [!unknown]" if b == "agy" and known and m not in known else ""
            labels.append(f"{m}[{b}]{flag}")
        print(f"  {task:9s} ({spec.get('capability','-')})  {' -> '.join(labels)}  || claude:{spec['claude_fallback']}")
        if note:
            print(f"             time-routing: {note}")
    log_rows = len(read_log())
    print(f"\ntelemetry log: {LOG_PATH}  ({log_rows} rows)")

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description="agy-bridge: GLM/Gemini/GPT-OSS co-processor + cost telemetry")
    ap.add_argument("--task", choices=["harvest", "critic", "research", "draft"])
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--model", help="force a single model id")
    ap.add_argument("--backend", choices=["agy", "zai"], help="backend for --model (default agy)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--list", action="store_true", help="print resolved chain, run nothing")
    ap.add_argument("--no-time-routing", action="store_true", help="ignore time_routing for this run")
    ap.add_argument("--report", action="store_true", help="print cost/savings summary")
    ap.add_argument("--analyze", action="store_true", help="print latency/error per backend x WIB hour")
    ap.add_argument("--doctor", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.doctor:
        return doctor(cfg)
    if args.report:
        return cmd_report(cfg)
    if args.analyze:
        return cmd_analyze(cfg)
    if not args.task:
        ap.error("--task is required (unless --doctor/--report/--analyze)")

    spec = resolve_task(cfg, args.task)
    hour, ts = wib_now()
    mode = "off" if args.no_time_routing else cfg.get("time_routing", "off")

    if args.model:
        chain = [{"backend": args.backend or "agy", "model": args.model}]
        note = None
    else:
        base = chain_for_task(spec, cfg)
        chain, note = apply_time_routing(base, cfg, mode, hour)

    if note:
        sys.stderr.write(f"[agy-bridge] {note}\n")

    if args.list:
        norm = [f"{m}[{b}]" for b, m in (normalize_entry(e) for e in chain)]
        print(f"task={args.task} capability={spec.get('capability','-')} mode={mode} chain={norm} claude_fallback={spec['claude_fallback']}")
        if note:
            print(f"time-routing: {note}")
        return

    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as fh:
            prompt = fh.read()
    elif args.prompt:
        prompt = args.prompt
    else:
        ap.error("provide --prompt or --prompt-file")

    known = cfg.get("known_agy_models", [])
    fallback_tier = spec["claude_fallback"]
    tried = []
    answer = None
    for entry in chain:
        backend, model = normalize_entry(entry)
        ok, text, reason, meta = run_entry(backend, model, prompt, args.timeout, cfg, known)
        if not ok and backend == "agy" and reason == "auth":
            sys.stderr.write(f"[agy-bridge] {model}[agy]: auth blip, retrying once\n")
            ok, text, reason, meta = run_entry(backend, model, prompt, args.timeout, cfg, known)
        cost = compute_cost(meta["in_tok"], meta["out_tok"], model, fallback_tier, cfg) if ok else \
            {"actual_usd": 0, "counterfactual_usd": 0, "saving_usd": 0, "price_estimated": False}
        log_call({
            "ts_wib": ts, "wib_hour": hour, "task": args.task, "backend": backend, "model": model,
            "input_tokens": meta["in_tok"] if ok else 0, "output_tokens": meta["out_tok"] if ok else 0,
            "tokens_estimated": meta["tokens_estimated"], "latency_ms": meta["latency_ms"],
            "ok": ok, "reason": reason, "time_routing": mode,
            "quota_mult": zai_quota_mult(backend, hour, ts, cfg),
            **{k: cost[k] for k in ("actual_usd", "counterfactual_usd", "saving_usd", "price_estimated")},
        })
        tried.append({"backend": backend, "model": model, "ok": ok, "note": None if ok else f"{reason}: {text}"})
        if ok:
            sys.stderr.write(f"[agy-bridge] answered by {model}[{backend}] "
                             f"(in/out {meta['in_tok']}/{meta['out_tok']} tok, saved ${cost['saving_usd']})\n")
            answer = text
            break
        sys.stderr.write(f"[agy-bridge] {model}[{backend}] failed ({reason}); trying next\n")

    write_summary(cfg)
    if answer is not None:
        print(answer)
        return
    print(json.dumps({"status": "fallback_to_claude", "task": args.task,
                      "claude_fallback": fallback_tier, "tried": tried}))
    sys.exit(3)

if __name__ == "__main__":
    main()
