#!/usr/bin/env python3
"""Resolved harness capabilities: the programmatic consumer of the detect scripts.

detect_platform.sh and detect_runtime.sh both print KEY=VALUE lines, but a shell
script nobody calls is decoration -- detect_platform.sh shipped long ago and every
one of its references is prose telling an agent to run it by hand, while
meeting-recorder/common.py kept a second copy of the same table in Python. This
module is the single place that runs both, caches the answer in .agent/harness.json,
and hands the rest of the harness plain booleans and strings.

DESIGN RULE: callers ask capability questions, not vendor questions.

    import harness_config as hc
    if hc.can_spawn_subagents():   # not: if hc.runtime() == "claude-code"
        ...
    if hc.tier() == "cheap":       # split the job into smaller steps
        ...
    if "agy" in hc.backends():     # delegation is available without subagents
        ...

.agent/harness.json is GITIGNORED and regenerated on demand, same as
.agent/glm_mode.flag. It must never be committed: `update-harness` treats new
tracked files under .agent/ as template files and can overwrite them with
`git checkout --theirs`, which would silently replace a machine's real config
with another machine's.

Usage:
  python3 .agent/scripts/harness_config.py --show          # human readable
  python3 .agent/scripts/harness_config.py --json          # raw config
  python3 .agent/scripts/harness_config.py --refresh       # force re-detect
  python3 .agent/scripts/harness_config.py --set key=value # persist an answer
"""
import argparse
import json
import os
import subprocess
import sys
import time

SCHEMA = 1
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPT_DIR = os.path.join(REPO_ROOT, ".agent", "scripts")
CONFIG_PATH = os.path.join(REPO_ROOT, ".agent", "harness.json")

# Re-detect after this long. A session can change model or runtime between runs,
# so the cache is a cost guard, not a source of truth. Override for cron with
# HARNESS_CONFIG_TTL (seconds); 0 means always re-detect.
DEFAULT_TTL_SECONDS = 3600

# Returned whenever detection cannot run at all. Every value is the safe answer:
# no delegation, no enforcement, unknown tier, so callers degrade rather than
# call a tool that is not there.
FALLBACK = {
    "schema": SCHEMA,
    "detected_at": 0.0,
    "session_id": "",
    "runtime": "unknown",
    "entrypoint": "unknown",
    "model": "unknown",
    "tier": "unknown",
    "subagents": False,
    "hooks": False,
    "backends": [],
    "platform": "unknown",
    "repo_root": REPO_ROOT,
    "run_prefix": "",
    "run_suffix": "",
    "extra": {},
}

# ---------- detection ----------

def _run_detect(script, timeout=30):
    """Run a detect script and parse its KEY=VALUE lines into a dict.

    Returns {} on any failure. A missing or broken detect script degrades the
    config, it does not take the caller down with it."""
    path = os.path.join(SCRIPT_DIR, script)
    if not os.path.isfile(path):
        return {}
    try:
        out = subprocess.run(["bash", path], capture_output=True, text=True,
                             timeout=timeout, cwd=REPO_ROOT)
    except Exception:
        return {}
    if out.returncode != 0:
        return {}
    parsed = {}
    for line in (out.stdout or "").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            parsed[key.strip()] = value.strip()
    return parsed

def detect(write=True):
    """Run both detect scripts, merge, and (by default) write .agent/harness.json.

    Always returns a complete config dict, never raises."""
    cfg = dict(FALLBACK)
    cfg["extra"] = dict(_read_raw().get("extra") or {})   # user answers survive re-detect

    plat = _run_detect("detect_platform.sh")
    if plat:
        cfg["platform"] = plat.get("PLATFORM") or "unknown"
        cfg["repo_root"] = plat.get("REPO_ROOT") or REPO_ROOT
        cfg["run_prefix"] = plat.get("RUN_PREFIX") or ""
        cfg["run_suffix"] = plat.get("RUN_SUFFIX") or ""

    rt = _run_detect("detect_runtime.sh")
    if rt:
        cfg["runtime"] = rt.get("RUNTIME") or "unknown"
        cfg["entrypoint"] = rt.get("ENTRYPOINT") or "unknown"
        cfg["model"] = rt.get("MODEL") or "unknown"
        cfg["tier"] = rt.get("TIER") or "unknown"
        cfg["subagents"] = (rt.get("SUBAGENTS") == "yes")
        cfg["hooks"] = (rt.get("HOOKS") == "yes")
        cfg["backends"] = [b for b in (rt.get("BACKENDS") or "").split(",") if b]

    cfg["detected_at"] = time.time()
    cfg["session_id"] = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if write:
        _write(cfg)
    return cfg

# ---------- cache ----------

def _read_raw():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _write(cfg):
    """Write the cache. A read-only or full disk is not fatal -- the caller
    already has the config it asked for, it just will not be cached."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass

def _is_stale(cfg, max_age):
    if cfg.get("schema") != SCHEMA:
        return True
    # A new Claude Code session can be a different model, so a session change
    # invalidates the cache regardless of age.
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if sid and cfg.get("session_id") != sid:
        return True
    if max_age <= 0:
        return True
    try:
        return (time.time() - float(cfg.get("detected_at") or 0)) > max_age
    except (TypeError, ValueError):
        return True

def load(max_age=None, refresh=True):
    """Return the resolved config, re-detecting when the cache is stale.

    refresh=False reads the cache only and falls back to safe defaults, for
    hot paths that must not shell out."""
    if max_age is None:
        try:
            max_age = float(os.environ.get("HARNESS_CONFIG_TTL", DEFAULT_TTL_SECONDS))
        except (TypeError, ValueError):
            max_age = DEFAULT_TTL_SECONDS
    cfg = _read_raw()
    if cfg and not _is_stale(cfg, max_age):
        merged = dict(FALLBACK)
        merged.update(cfg)
        return merged
    if not refresh:
        merged = dict(FALLBACK)
        merged.update(cfg)
        return merged
    return detect()

# ---------- convenience predicates ----------
# Branch on these, not on runtime().

def can_spawn_subagents():
    """True when the runtime can spawn typed subagents. When False, delegation
    goes through agy-bridge and the main loop works inline."""
    return bool(load().get("subagents"))

def has_hooks():
    """True when the runtime has a hook system. When False, Python-side gates
    are the ONLY enforcement layer and must not be skipped."""
    return bool(load().get("hooks"))

def tier():
    """Main-loop strength: flagship | mid | cheap | unknown."""
    return load().get("tier") or "unknown"

def backends():
    """Non-main-loop model backends available for delegation, e.g. ['agy', 'zai']."""
    val = load().get("backends")
    return list(val) if isinstance(val, list) else []

def runtime():
    """Vendor name. For logging and for the two places that genuinely need it
    (transcript path, agy CLI). Do not branch capability on this."""
    return load().get("runtime") or "unknown"

def entrypoint():
    return load().get("entrypoint") or "unknown"

def model():
    return load().get("model") or "unknown"

def platform():
    """macos | wsl | windows | unknown, from detect_platform.sh."""
    return load().get("platform") or "unknown"

def repo_root():
    return load().get("repo_root") or REPO_ROOT

def run_prefix():
    return load().get("run_prefix") or ""

def run_suffix():
    return load().get("run_suffix") or ""

def extra(key=None, default=None):
    """Answers that detection cannot infer, persisted by setup. Survives re-detect."""
    ex = load().get("extra")
    ex = ex if isinstance(ex, dict) else {}
    return ex if key is None else ex.get(key, default)

def set_extra(key, value):
    """Persist one answer into harness.json without re-running detection."""
    cfg = load()
    ex = cfg.get("extra")
    cfg["extra"] = dict(ex) if isinstance(ex, dict) else {}
    cfg["extra"][key] = value
    _write(cfg)
    return cfg

# ---------- CLI ----------

def _show(cfg):
    order = ("runtime", "entrypoint", "model", "tier", "platform",
             "subagents", "hooks", "backends", "repo_root")
    width = max(len(k) for k in order)
    print("Harness config  (%s)" % CONFIG_PATH)
    for key in order:
        val = cfg.get(key)
        if isinstance(val, bool):
            val = "yes" if val else "no"
        elif isinstance(val, list):
            val = ", ".join(val) or "(none)"
        print("  %-*s  %s" % (width, key, val if val not in (None, "") else "(unset)"))
    ex = cfg.get("extra") or {}
    for key in sorted(ex):
        print("  %-*s  %s" % (width, key, ex[key]))
    print("")
    print("  delegation      %s" % ("typed subagents" if cfg.get("subagents")
                                    else ("agy-bridge only" if cfg.get("backends")
                                          else "none, main loop works inline")))
    print("  enforcement     %s" % ("hooks + python gates" if cfg.get("hooks")
                                    else "python gates only"))

def main():
    ap = argparse.ArgumentParser(description="Resolved harness capabilities.")
    ap.add_argument("--show", action="store_true", help="print the resolved config")
    ap.add_argument("--json", action="store_true", help="print the raw config as JSON")
    ap.add_argument("--refresh", action="store_true", help="force re-detection")
    ap.add_argument("--set", metavar="KEY=VALUE", action="append", default=[],
                    help="persist an answer detection cannot infer (repeatable)")
    args = ap.parse_args()

    cfg = detect() if args.refresh else load()
    for pair in args.set:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            print("skipped (expected KEY=VALUE): %s" % pair, file=sys.stderr)
            continue
        cfg = set_extra(key.strip(), value.strip())

    if args.json:
        print(json.dumps(cfg, indent=2, sort_keys=True))
    else:
        _show(cfg)
    return 0

if __name__ == "__main__":
    sys.exit(main())
