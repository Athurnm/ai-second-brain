#!/usr/bin/env python3
"""Shared helpers for the local meeting note-taker (recorder / transcribe / watcher).

Platform detection mirrors .agent/scripts/detect_platform.sh:
Darwin -> macos, Linux -> wsl (You's Linux is always WSL), Windows -> windows.
"""
import json
import os
import platform
import re
import sys

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(MODULE_DIR)
CONFIG_PATH = os.path.join(MODULE_DIR, "config.json")

def detect_platform():
    sysname = platform.system()
    if sysname == "Darwin":
        return "macos"
    if sysname == "Linux":
        return "wsl"
    return "windows"

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    plat = detect_platform()
    machine = dict(cfg.get("machines", {}).get(plat, {}))
    if machine.get("recordings_dir"):
        machine["recordings_dir"] = os.path.expanduser(machine["recordings_dir"])
    if machine.get("whispercpp_model"):
        machine["whispercpp_model"] = os.path.expanduser(machine["whispercpp_model"])
    cfg["platform"] = plat
    cfg["machine"] = machine
    return cfg

def slugify(title):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    return slug[:60] or "meeting"

def fmt_ts(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def parse_json_tail(text):
    """gcal_manager prints a 'Fetching events...' line before the JSON on
    stdout; parse from the first [ or { onward."""
    for i, ch in enumerate(text):
        if ch in "[{":
            return json.loads(text[i:])
    raise ValueError("no JSON found in output")

def load_gemini_key():
    """Reuse the Gemini API key from the gemini-image skill (metered, You's)."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    env_path = os.path.join(REPO_ROOT, ".agent", "skills", "gemini-image", "token.env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("ERROR: no GEMINI_API_KEY (env or .agent/skills/gemini-image/token.env)")
