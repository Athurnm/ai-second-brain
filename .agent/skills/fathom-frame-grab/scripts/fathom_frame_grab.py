#!/usr/bin/env python3
"""Grab still frames from a Fathom recording at given timestamps.

Why this exists: Fathom's API/MCP only return transcript + summary, never video
frames, and the /calls/<id> page is login-gated. But with the authenticated user's
`_fathom_session` cookie we can read the HLS VOD playlist
(https://fathom.video/calls/<id>/video.m3u8), download just the chunks covering the
wanted timestamps, and decode a frame. Useful for pulling product/demo screenshots
straight out of a screen-share recording (e.g. to drop into a BRD/PRD).

Auth: pass the session cookie via --cookie, or env FATHOM_SESSION, or a token.env in
the skill dir with `FATHOM_SESSION=<value>`. Get it from Chrome DevTools ->
Application -> Cookies -> fathom.video -> `_fathom_session` (full value). Session
cookies expire, so refresh when you get a sign_in redirect.

Decode note: the johnvansickle ffmpeg-static segfaults on these TS chunks on some
WSL kernels, so we decode with PyAV (its own libav). `pip install av pillow`.

Usage:
  python3 fathom_frame_grab.py --call 724217462 --at 1520,1560 --out ./shots
  python3 fathom_frame_grab.py --call https://fathom.video/calls/724217462 \
      --at 25:20,26:00 --out ./shots --crop 16,152,924,690 --scale 1.6
"""
import argparse, os, re, sys, time, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_cookie(arg):
    if arg:
        return arg.strip()
    if os.environ.get("FATHOM_SESSION"):
        return os.environ["FATHOM_SESSION"].strip()
    env = os.path.join(SKILL_DIR, "token.env")
    if os.path.exists(env):
        for line in open(env):
            line = line.strip()
            if line.startswith("FATHOM_SESSION=") and "=" in line:
                return line.split("=", 1)[1].strip()
    sys.exit("No Fathom session cookie. Pass --cookie, set FATHOM_SESSION, or add it to token.env.")

def http_get(url, cookie, tries=6, binary=True):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Cookie": f"_fathom_session={cookie}"})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                final = r.geturl()
                if "sign_in" in final:
                    sys.exit("Redirected to sign_in: the session cookie is expired/invalid. Refresh _fathom_session.")
                data = r.read()
                return data if binary else data.decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(2)  # WSL DNS over UDP is flaky; TCP retries usually win
    raise SystemExit(f"GET failed after {tries} tries: {url} ({last})")

def parse_ts(s):
    s = s.strip()
    if ":" in s:
        parts = [int(x) for x in s.split(":")]
        return parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(s)

def recording_id(call):
    m = re.search(r"(\d{6,})", call)
    return m.group(1) if m else call

def parse_playlist(text):
    """Return list of (cum_start_seconds, duration, chunk_path)."""
    chunks, t = [], 0.0
    dur = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            dur = float(line[len("#EXTINF:"):].split(",")[0])
        elif line and not line.startswith("#"):
            chunks.append((t, dur or 6.0, line))
            t += dur or 6.0
            dur = None
    return chunks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", required=True, help="Recording id or /calls/<id> URL")
    ap.add_argument("--at", required=True, help="Comma list of timestamps: seconds or mm:ss")
    ap.add_argument("--out", default="./fathom_shots")
    ap.add_argument("--cookie", help="_fathom_session value (else env/token.env)")
    ap.add_argument("--window", type=float, default=2.0, help="+/- seconds of frames to dump around each ts")
    ap.add_argument("--crop", help="left,top,right,bottom in px (e.g. 16,152,924,690)")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--quality", type=int, default=90)
    args = ap.parse_args()

    try:
        import av  # noqa
        from PIL import Image  # noqa
    except ImportError:
        sys.exit("Needs PyAV + Pillow: pip install av pillow")
    import av
    from PIL import Image

    cookie = load_cookie(args.cookie)
    rid = recording_id(args.call)
    os.makedirs(args.out, exist_ok=True)
    targets = [parse_ts(x) for x in args.at.split(",")]
    crop = tuple(int(x) for x in args.crop.split(",")) if args.crop else None

    m3u8 = http_get(f"https://fathom.video/calls/{rid}/video.m3u8", cookie, binary=False)
    chunks = parse_playlist(m3u8)
    if not chunks:
        sys.exit("Empty playlist (auth ok but no chunks?)")
    total = chunks[-1][0] + chunks[-1][1]
    print(f"recording {rid}: {len(chunks)} chunks, ~{int(total)}s")

    for tgt in targets:
        # collect chunk indices covering [tgt-window, tgt+window]
        lo, hi = tgt - args.window, tgt + args.window
        idxs = [i for i, (cs, d, _) in enumerate(chunks) if cs + d >= lo and cs <= hi]
        if not idxs:
            print(f"  ts {tgt}: out of range"); continue
        buf = b""
        for i in idxs:
            buf += http_get("https://fathom.video" + chunks[i][2], cookie)
        tmp = os.path.join(args.out, f"_tmp_{int(tgt)}.ts")
        open(tmp, "wb").write(buf)
        base = chunks[idxs[0]][0]
        # decode, pick frame nearest tgt
        best, best_d = None, 1e9
        container = av.open(tmp)
        vs = container.streams.video[0]
        first = None
        for frame in container.decode(video=0):
            if frame.pts is None:
                continue
            t = float(frame.pts * vs.time_base)
            if first is None:
                first = t
            g = base + (t - first)
            d = abs(g - tgt)
            if d < best_d:
                best_d, best = d, frame.to_image()
        container.close()
        os.remove(tmp)
        if best is None:
            print(f"  ts {tgt}: no frame decoded"); continue
        if crop:
            best = best.crop(crop)
        if args.scale != 1.0:
            w, h = best.size
            best = best.resize((int(w * args.scale), int(h * args.scale)), Image.LANCZOS)
        mm, ss = int(tgt) // 60, int(tgt) % 60
        out = os.path.join(args.out, f"frame_{mm:02d}m{ss:02d}s.jpg")
        best.save(out, quality=args.quality)
        print(f"  ts {tgt} -> {out} (nearest {best_d:.1f}s)")

    print("Done:", args.out)

if __name__ == "__main__":
    main()
