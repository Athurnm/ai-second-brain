---
name: Fathom Frame Grab
description: Pull still frames (screenshots) from a Fathom recording at given timestamps, by reading the authenticated HLS video stream. For grabbing demo/screen-share stills to drop into a BRD/PRD.
---

# Fathom Frame Grab

Fathom's API and MCP only ever return **transcript + summary**, never video frames, and
the `/calls/<id>` page is login-gated. This skill pulls actual **still frames** out of a
recording (e.g. a screen-share demo) so you can use them as screenshots in a doc.

How it works: with the authenticated user's `_fathom_session` cookie it reads the HLS VOD
playlist (`https://fathom.video/calls/<id>/video.m3u8`), downloads only the chunks covering
the requested timestamps, decodes the frame nearest each timestamp, and saves a JPG
(optionally cropped + scaled).

## When to use
- You asks for a screenshot of something shown during a Fathom-recorded demo/meeting
  (e.g. "grab the checkout screen from the ExampleCo demo for the BRD").
- You need a visual that exists only in a screen-share recording and no clean source
  screenshot is available.

## Auth (required)
Provide the `_fathom_session` cookie one of three ways:
1. `--cookie <value>`
2. env `FATHOM_SESSION=<value>`
3. `token.env` in this skill dir with `FATHOM_SESSION=<value>`

Get it from You's Chrome: DevTools → Application → Cookies → `https://fathom.video` →
click `_fathom_session` → copy the full value from the bottom "Cookie Value" panel. It is
`HttpOnly`, so it won't appear in JS; it must be read from DevTools. **Session cookies
expire** — if you get a `sign_in` redirect, ask You to refresh it.

## Usage
```bash
python3 .agent/skills/fathom-frame-grab/scripts/fathom_frame_grab.py \
  --call 724217462 \
  --at 25:20,26:00 \
  --out ./shots \
  --cookie <_fathom_session> \
  [--crop 16,152,924,690] [--scale 1.6] [--window 2.0] [--quality 90]
```
- `--call`: recording id or full `/calls/<id>` URL.
- `--at`: comma list of timestamps, seconds (`1520`) or `mm:ss` (`25:20`). Match the
  Fathom transcript/player timeline (the `?timestamp=` deep-link value).
- `--crop left,top,right,bottom` (px): trim the Fathom player chrome / webcam tiles. For a
  1280×720 screen-share with tiles on the right, `16,152,924,690` keeps just the shared
  window.
- `--scale`: upscale for legibility (1.6 ≈ good for a 720p share in a doc).
- `--window`: ± seconds of chunks to fetch around each ts (default 2). Increase if the
  exact frame is just outside.

## Gotchas (learned 2026-06-25, ExampleCo ExampleProgram demo)
- **Decode with PyAV, not ffmpeg.** The johnvansickle `ffmpeg-static` binary segfaults on
  these MPEG-TS chunks on WSL (kernel mismatch); `ffprobe` works but `ffmpeg` crashes even
  on `-c copy`. PyAV (`pip install av pillow`) uses its own libav and decodes fine.
- **WSL DNS is flaky** (Indonesia ISP hijacks UDP-53). The script retries every GET; a
  `HTTP 000 / Unable to find the server` usually succeeds on retry.
- **Quality** is whatever the screen-share was recorded at (typically 1280×720) and the
  frame carries the Fathom UI unless cropped. Fine for "visual context" in a BRD; for a
  pixel-clean asset, a fresh staging screenshot still beats it.

## Embedding into a Google Doc
The frames are local JPGs. To put them in a GDoc, the Docs API needs a public image URI, so:
upload each via the drive connector (`--share`), insert with `insertInlineImage`
(pattern in `scripts/embed_brd_gc_screenshots.py`), then restrict the source images back to
the domain. See `[[feedback_read_gdoc_before_overwrite]]` and the gdoc formatting SOP.
