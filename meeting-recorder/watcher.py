#!/usr/bin/env python3
"""Watcher daemon: turns finished local recordings into transcripts + MOM drafts.

Runs on the repo host (WSL or macOS). Polls <recordings_dir> from config.json;
for each finished recording (no .recording marker, file stable) it:
  1. Mixes Windows two-part captures (<base>.sys.wav + <base>.mic.wav) into one WAV.
  2. Transcribes via transcribe.py (whisper.cpp GPU -> Gemini CLI; never CPU).
  3. Registers the recording in journal/fathom_registry.json as "local-<epoch>"
     so /mom resolves it like a Fathom call (best-effort calendar match for title).
  4. Drafts a MOM via agy-bridge (harvest -> draft, templates/mom_work.md); if the
     bridge signals fallback_to_claude (exit 3), saves transcript only and flags
     the recording as "needs /mom manual".
  5. Writes heartbeat + activity log rows.

Usage:
  python3 watcher.py                 # poll loop (30s)
  python3 watcher.py --once          # single scan, then exit
  python3 watcher.py --file <audio>  # process one specific file, then exit
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

from common import REPO_ROOT, load_config, parse_json_tail, slugify
from transcribe import transcribe

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(MODULE_DIR, "state.json")
REGISTRY_PATH = os.path.join(REPO_ROOT, "journal", "fathom_registry.json")
TRANSCRIPTS_DIR = os.path.join(REPO_ROOT, "Clients", "Work", "meetings", "transcripts")
MOM_DIR = os.path.join(REPO_ROOT, "Clients", "Work", "meetings")
MOM_TEMPLATE = os.path.join(REPO_ROOT, "templates", "mom_work.md")
AGY_BRIDGE = os.path.join(REPO_ROOT, ".agent", "skills", "agy-bridge", "run.py")
HEARTBEAT = os.path.join(REPO_ROOT, ".agent", "scripts", "heartbeat.py")
ACTIVITY_LOG = os.path.join(REPO_ROOT, ".agent", "scripts", "activity_log.py")
GCAL = os.path.join(REPO_ROOT, ".agent", "skills", "google-calendar-connector", "gcal_manager.py")

AUDIO_EXTS = (".wav", ".m4a", ".mp3", ".ogg", ".flac")
WIB = datetime.timezone(datetime.timedelta(hours=7))

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"processed": {}}

def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)

def heartbeat(status, summary):
    try:
        subprocess.run([sys.executable, HEARTBEAT, "--job", "local-recorder",
                        "--status", status, "--summary", summary],
                       capture_output=True, timeout=30)
    except Exception:
        pass

def activity(target, summary):
    try:
        subprocess.run([sys.executable, ACTIVITY_LOG, "--actor", "agent",
                        "--action", "transcribe", "--project", "Other",
                        "--target", target, "--summary", summary],
                       capture_output=True, timeout=30)
    except Exception:
        pass

# ---------- discovery ----------

def mix_parts(base, ffmpeg):
    """Merge <base>.sys.wav + <base>.mic.wav into <base>.wav (Windows captures)."""
    sysw, micw, out = base + ".sys.wav", base + ".mic.wav", base + ".wav"
    parts = [p for p in (sysw, micw) if os.path.exists(p)]
    if not parts or os.path.exists(out):
        return
    cmd = [ffmpeg, "-y", "-v", "quiet"]
    for p in parts:
        cmd += ["-i", p]
    if len(parts) > 1:
        cmd += ["-filter_complex", "amix=inputs=2:duration=longest:normalize=0"]
    cmd += ["-ac", "1", "-ar", "16000", out]
    subprocess.run(cmd, check=True, timeout=1800)
    print(f"[watcher] mixed {len(parts)} part(s) -> {out}")

def find_candidates(rec_dir, state, ffmpeg):
    if not os.path.isdir(rec_dir):
        return []
    # first, mix any finished two-part Windows captures
    for f in os.listdir(rec_dir):
        if f.endswith(".sys.wav") or f.endswith(".mic.wav"):
            base = os.path.join(rec_dir, f.rsplit(".", 2)[0])
            if not os.path.exists(base + ".recording"):
                try:
                    mix_parts(base, ffmpeg)
                except subprocess.SubprocessError as e:
                    print(f"[watcher] mix failed for {base}: {e}", file=sys.stderr)

    out = []
    now = time.time()
    for f in sorted(os.listdir(rec_dir)):
        path = os.path.join(rec_dir, f)
        base, ext = os.path.splitext(path)
        if ext.lower() not in AUDIO_EXTS or base.endswith((".sys", ".mic")):
            continue
        if os.path.exists(base + ".recording"):
            continue  # still recording
        # a sidecar .json means the recorder finished cleanly -> final file;
        # the 60s stability window only guards files copied in manually
        if not os.path.exists(base + ".json") and now - os.path.getmtime(path) < 60:
            continue  # not stable yet
        if path in state["processed"]:
            continue
        out.append(path)
    return out

# ---------- registry + calendar ----------

def read_sidecar(base):
    meta_path = base + ".json"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def calendar_match(start_wib, cfg):
    """Best-effort: find a Work calendar event overlapping the recording start."""
    if not cfg.get("calendar_match", True):
        return None
    try:
        r = subprocess.run([sys.executable, GCAL, "list", "--profile", "work",
                            "--days-back", "2", "--days-forward", "0", "--json"],
                           capture_output=True, text=True, timeout=120)
        events = parse_json_tail(r.stdout)
        if isinstance(events, dict):
            events = events.get("events", [])
        for ev in events:
            raw = ev.get("start") or {}
            st = raw.get("dateTime") if isinstance(raw, dict) else raw
            if not st:
                continue
            ev_start = datetime.datetime.fromisoformat(st.replace("Z", "+00:00"))
            if ev_start.tzinfo is None:  # all-day/naive events: assume WIB
                ev_start = ev_start.replace(tzinfo=WIB)
            delta = abs((ev_start - start_wib).total_seconds())
            if delta <= 30 * 60:
                return ev.get("summary")
    except Exception as e:
        print(f"[watcher] calendar match skipped: {e}", file=sys.stderr)
    return None

def register_recording(audio_path, meta, matched, duration_sec):
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    rec_id = f"local-{int(time.time())}"
    start_utc = meta.get("start_utc")
    if start_utc:
        start_dt = datetime.datetime.fromisoformat(start_utc)
    else:
        start_dt = datetime.datetime.fromtimestamp(
            os.path.getmtime(audio_path), datetime.timezone.utc)
    start_wib = start_dt.astimezone(WIB)
    registry[rec_id] = {
        "recording_id": rec_id,
        "local_path": audio_path,
        "date_wib": start_wib.strftime("%Y-%m-%d"),
        "time_wib": start_wib.strftime("%H:%M"),
        "start_utc": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration": f"{max(1, round((duration_sec or 0) / 60))} min",
        "raw_title": meta.get("title", os.path.basename(audio_path)),
        "matched_meeting": matched,
        "match_source": "local-recorder",
        "confidence": "high" if matched else "medium",
        "client": "Work",
        "project": None,
        "participants": [],
        "transcript_language": None,
        "last_synced_utc": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REGISTRY_PATH)
    return rec_id, start_wib

def update_registry_entry(rec_id, **fields):
    """Merge fields into one registry entry (atomic write)."""
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    if rec_id not in registry:
        return
    registry[rec_id].update(fields)
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REGISTRY_PATH)

def find_related(matched, date_wib, exclude_id=None):
    """Other registry entries covering the same calendar meeting on the same
    date (Fathom + Vexa + local all land here, so this is the dedupe key).
    Returns [(rec_id, entry), ...]."""
    if not matched:
        return []
    key = matched.strip().lower()
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    return [(rid, e) for rid, e in registry.items()
            if rid != exclude_id and e.get("date_wib") == date_wib
            and (e.get("matched_meeting") or "").strip().lower() == key]

def link_related(rec_id, related):
    """Cross-reference duplicate recordings of one meeting, both directions."""
    if not related:
        return
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    ids = [rid for rid, _ in related]
    mine = registry.get(rec_id, {})
    mine["related_recordings"] = sorted(set(mine.get("related_recordings", []) + ids))
    for rid in ids:
        other = registry.get(rid)
        if other is not None:
            other["related_recordings"] = sorted(
                set(other.get("related_recordings", []) + [rec_id]))
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REGISTRY_PATH)

def existing_mom(related):
    """Path of an already-drafted MOM among related recordings, if any."""
    for rid, e in related:
        p = e.get("mom_path")
        if p and os.path.exists(os.path.join(REPO_ROOT, p)):
            return rid, p
    return None, None

# ---------- MOM drafting via agy-bridge ----------

def agy(task, prompt, workdir, model=None, backend=None):
    """Run agy-bridge; returns text or None on fallback_to_claude (exit 3).

    With model/backend set, tries that model first and falls back to the
    task's normal chain if it fails (agentic CLI models flake sometimes).
    """
    pf = os.path.join(workdir, f"prompt_{task}.txt")
    with open(pf, "w", encoding="utf-8") as f:
        f.write(prompt)
    cmd = [sys.executable, AGY_BRIDGE, "--task", task, "--prompt-file", pf]
    if model:
        r = subprocess.run(cmd + ["--model", model] +
                           (["--backend", backend] if backend else []),
                           capture_output=True, text=True, timeout=1200)
        if r.returncode == 0:
            return _strip_narration(r.stdout.strip())
        print(f"[watcher] forced model '{model}' failed, using default chain",
              file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if r.returncode == 3:
        return None
    if r.returncode != 0:
        raise RuntimeError(f"agy-bridge {task} failed: {r.stderr[-300:]}")
    return _strip_narration(r.stdout.strip())

def _strip_narration(text):
    """Drop agentic-CLI preamble ('I have created...') before the MOM body."""
    idx = text.find("# MOM")
    if idx == -1:
        idx = text.find("\n# ")
        idx = idx + 1 if idx != -1 else -1
    return text[idx:].strip() if idx > 0 else text

def draft_mom(transcript_md, title, start_wib, matched, scratch, cfg=None):
    cfg = cfg or {}
    with open(transcript_md, encoding="utf-8") as f:
        transcript = f.read()
    with open(MOM_TEMPLATE, encoding="utf-8") as f:
        template = f.read()

    facts = agy("harvest",
                "You are extracting raw facts from a meeting transcript for minutes.\n"
                "Return, as plain structured text: participants (from speaker labels/"
                "context), topics discussed with key points, decisions made with "
                "rationale, action items with owner and deadline if stated, notable "
                "quotes. Do NOT synthesize or prioritize; facts only. Keep the "
                "original language of quotes.\n\n=== TRANSCRIPT ===\n" + transcript,
                scratch)
    if facts is None:
        return None

    meeting_line = matched or title
    mom = agy("draft",
              "Write meeting minutes (MOM) in ENGLISH following EXACTLY this markdown "
              "template structure (replace placeholders, keep the section order and "
              "table formats). No em-dashes anywhere. Meeting: "
              f"{meeting_line}. Date: {start_wib.strftime('%Y-%m-%d')}, start "
              f"{start_wib.strftime('%H:%M')} WIB.\n\n=== TEMPLATE ===\n{template}\n\n"
              "=== EXTRACTED FACTS ===\n" + facts,
              scratch,
              model=cfg.get("draft_model"), backend=cfg.get("draft_backend"))
    return mom

# ---------- main processing ----------

def process(audio_path, cfg, state):
    name = os.path.basename(audio_path)
    base = os.path.splitext(audio_path)[0]
    meta = read_sidecar(base)
    title = meta.get("title") or os.path.splitext(name)[0]
    print(f"[watcher] processing: {name} ({title})")

    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    slug = slugify(title)
    transcript_md = os.path.join(TRANSCRIPTS_DIR, os.path.splitext(name)[0] + ".md")
    transcript_md, engine_note = transcribe(audio_path, transcript_md, cfg=cfg)

    duration = meta.get("duration_sec", 0)
    rec_id, start_wib = register_recording(audio_path, meta, None, duration)
    matched = calendar_match(start_wib, cfg)
    if matched:
        update_registry_entry(rec_id, matched_meeting=matched, confidence="high")
    video = base + ".mp4"
    if os.path.exists(video):
        update_registry_entry(rec_id, video_path=video)
        print(f"[watcher] video sidecar registered: {video}")

    # dedupe: one meeting -> one MOM (Vexa / Fathom / local all share the registry)
    related = find_related(matched, start_wib.strftime("%Y-%m-%d"), exclude_id=rec_id)
    link_related(rec_id, related)
    dup_rid, dup_mom = existing_mom(related)

    mom_path, status = None, "transcribed"
    if dup_mom:
        status = f"transcribed (duplicate of {dup_rid}, MOM draft skipped)"
        print(f"[watcher] {status} -> {dup_mom}")
    elif cfg.get("auto_draft", True):
        scratch = os.path.join(MODULE_DIR, "scratch")
        os.makedirs(scratch, exist_ok=True)
        try:
            mom = draft_mom(transcript_md, title, start_wib, matched, scratch, cfg)
        except RuntimeError as e:
            print(f"[watcher] draft failed: {e}", file=sys.stderr)
            mom = None
        if mom:
            mom_path = os.path.join(
                MOM_DIR, f"MOM_{slug}_{start_wib.strftime('%Y-%m-%d')}.md")
            header = (f"> Status: DRAFT (local pipeline, belum direview)\n"
                      f"> Source: local recording `{name}`, {engine_note}\n"
                      f"> Registry: {rec_id} | Review via /mom before sharing\n\n")
            with open(mom_path, "w", encoding="utf-8") as f:
                f.write(header + mom + "\n")
            status = "drafted"
            update_registry_entry(rec_id, mom_path=os.path.relpath(mom_path, REPO_ROOT))
            print(f"[watcher] MOM draft -> {mom_path}")
        else:
            status = "needs /mom manual (agy-bridge fallback_to_claude)"
            print(f"[watcher] {status}")

    state["processed"][audio_path] = {
        "rec_id": rec_id, "transcript": transcript_md, "mom": mom_path,
        "status": status,
        "ts": datetime.datetime.now(WIB).isoformat(timespec="seconds"),
    }
    save_state(state)
    heartbeat("ok", f"{name}: {status} ({rec_id})")
    activity(rec_id, f"local recording {name}: {status}")

def scan_once(cfg, state):
    rec_dir = cfg["machine"].get("recordings_dir", "")
    ffmpeg = cfg["machine"].get("ffmpeg", "ffmpeg")
    for path in find_candidates(rec_dir, state, ffmpeg):
        try:
            process(path, cfg, state)
        except Exception as e:
            print(f"[watcher] FAILED {path}: {e}", file=sys.stderr)
            state["processed"][path] = {
                "status": f"failed: {e}",
                "ts": datetime.datetime.now(WIB).isoformat(timespec="seconds")}
            save_state(state)
            heartbeat("fail", f"{os.path.basename(path)}: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single scan, then exit")
    ap.add_argument("--file", help="process one specific audio file, then exit")
    ap.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()

    cfg = load_config()
    state = load_state()
    if args.file:
        path = os.path.abspath(args.file)
        state["processed"].pop(path, None)
        process(path, cfg, state)
        return
    if args.once:
        scan_once(cfg, state)
        return
    print(f"[watcher] polling {cfg['machine'].get('recordings_dir')} "
          f"every {args.interval}s (Ctrl-C to stop)")
    while True:
        scan_once(cfg, state)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
