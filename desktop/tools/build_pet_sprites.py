#!/usr/bin/env python3
"""
build_pet_sprites.py — Pet Battler v2 asset pipeline.

Converts AI-generated pixel-art PNGs (solid magenta #FF00FF background,
optionally with a darker-magenta ground-shadow ellipse) into clean,
web-ready sprite sheets for the desktop app's canvas HUD renderer.

Pipeline per character/enemy/egg source image:
  1. Chroma-key magenta to alpha:
       - flood fill from the image border across "magenta-family" pixels
         (matches pure #FF00FF within ~60 euclidean RGB tolerance, and the
         broader darker-magenta family used for ground shadows), so the
         background AND any magenta shadow connected to it go transparent
         while magenta-colored pixels fully enclosed by the character
         silhouette (there are none in this set) would be left alone.
       - despill pass: opaque pixels touching the new transparent region
         that still read as a magenta/pink halo get pulled transparent too.
  2. Autocrop to the opaque content's bounding box + 2px transparent pad.
  3. Pixelize: LANCZOS-downscale (alpha-premultiplied, to avoid magenta
     fringing) so the sprite's content height is 96px, then quantize to an
     adaptive 24-color palette while preserving the alpha channel.
  4. Save as PNG.

Background plates (bg_journey, bg_battle) skip the chroma-key/crop steps:
downscale to 960px wide and quantize to 48 colors.

Usage:
  python3 tools/build_pet_sprites.py [--src DIR] [--out DIR]

Missing or zero-byte source files are reported and skipped — the engine
falls back to the legacy matrix renderer for whatever isn't produced here.
"""
import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

SPECIES = ["bit", "byte", "link", "pixel", "scribe"]
STATES = ["idle", "walk", "attack"]
ENEMIES = ["goblin", "slime", "golem", "reaper"]
CHAR_TARGET_H = 96
CHAR_PALETTE_COLORS = 24
BG_TARGET_W = 960
BG_PALETTE_COLORS = 48

MAGENTA = np.array([255, 0, 255], dtype=np.int32)
MAGENTA_TOLERANCE = 60  # euclidean, per spec


def expected_files():
    """(name-without-ext, kind) for every asset the engine expects."""
    out = []
    for sp in SPECIES:
        for st in STATES:
            out.append((f"{sp}_{st}", "character"))
    out.append(("egg_idle", "character"))
    for en in ENEMIES:
        out.append((f"enemy_{en}", "character"))
    out.append(("bg_journey", "background"))
    out.append(("bg_battle", "background"))
    return out


def magenta_family_mask(rgb):
    """Boolean mask: pixels that read as magenta (bg) or magenta-family
    shadow. Combines a strict euclidean-distance test against pure magenta
    (tolerance ~60) with a broader family test so the darker ground-shadow
    ellipse floods away too — measured shadow cores land around (114,22,89),
    well below a naive r>140 cutoff, so the family band goes down to r>90.
    Character outlines in this asset set are near-black (r,g,b all <40), so
    they stay well outside this band and keep blocking the flood from
    leaking into any body interior (verified against the pink "pixel"
    species body, which sits in the same magenta/pink hue family but is
    walled off by its outline ring)."""
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    dist2 = (r - int(MAGENTA[0])) ** 2 + (g - int(MAGENTA[1])) ** 2 + (b - int(MAGENTA[2])) ** 2
    strict = dist2 <= MAGENTA_TOLERANCE ** 2
    family = (r > 90) & (g < 100) & (b > 55) & (r > g + 30) & (b > g + 20)
    return strict | family


def flood_from_border(mask):
    """Scanline flood fill: True where a `mask` pixel is 4-connected to the
    image border through other `mask` pixels. Pure numpy/deque, no scipy."""
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    stack = deque()

    def seed_row(y):
        for x in range(w):
            if mask[y, x] and not visited[y, x]:
                stack.append((y, x))

    def seed_col(x):
        for y in range(h):
            if mask[y, x] and not visited[y, x]:
                stack.append((y, x))

    seed_row(0)
    seed_row(h - 1)
    seed_col(0)
    seed_col(w - 1)

    while stack:
        y, x = stack.pop()
        if visited[y, x]:
            continue
        row = mask[y]
        xl = x
        while xl - 1 >= 0 and row[xl - 1] and not visited[y, xl - 1]:
            xl -= 1
        xr = x
        while xr + 1 < w and row[xr + 1] and not visited[y, xr + 1]:
            xr += 1
        visited[y, xl:xr + 1] = True
        if y - 1 >= 0:
            up = mask[y - 1]
            vup = visited[y - 1]
            for xx in range(xl, xr + 1):
                if up[xx] and not vup[xx]:
                    stack.append((y - 1, xx))
        if y + 1 < h:
            dn = mask[y + 1]
            vdn = visited[y + 1]
            for xx in range(xl, xr + 1):
                if dn[xx] and not vdn[xx]:
                    stack.append((y + 1, xx))
    return visited


def despill(rgba, transparent_mask, passes=2):
    """Pull opaque pixels touching newly-transparent pixels transparent too
    if they still read as a magenta/pink halo — cleans the fringing chroma
    keying leaves on anti-aliased edges."""
    h, w = rgba.shape[:2]
    alpha = rgba[..., 3]
    trans = transparent_mask.copy()
    for _ in range(passes):
        touch = np.zeros_like(trans)
        touch[1:, :] |= trans[:-1, :]
        touch[:-1, :] |= trans[1:, :]
        touch[:, 1:] |= trans[:, :-1]
        touch[:, :-1] |= trans[:, 1:]
        opaque = ~trans
        r = rgba[..., 0].astype(np.int32)
        g = rgba[..., 1].astype(np.int32)
        b = rgba[..., 2].astype(np.int32)
        halo = (r > 200) & (b > 200) & (g < 120)
        spill = touch & opaque & halo
        if not spill.any():
            break
        trans |= spill
    alpha = alpha.copy()
    alpha[trans] = 0
    rgba = rgba.copy()
    rgba[..., 3] = alpha
    return rgba


def chroma_key(im):
    """RGB(A) PIL Image -> RGBA numpy array with magenta bg/shadow removed."""
    rgba = np.array(im.convert("RGBA"))
    rgb = rgba[..., :3]
    bg_candidate = magenta_family_mask(rgb)
    transparent = flood_from_border(bg_candidate)
    rgba[transparent, 3] = 0
    rgba = despill(rgba, transparent)
    return rgba


def autocrop(rgba, pad=2):
    alpha = rgba[..., 3]
    ys, xs = np.where(alpha > 0)
    if len(ys) == 0:
        return rgba  # fully transparent — nothing to crop, caller will flag
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    cropped = rgba[y0:y1, x0:x1]
    h, w = cropped.shape[:2]
    out = np.zeros((h + pad * 2, w + pad * 2, 4), dtype=np.uint8)
    out[pad:pad + h, pad:pad + w] = cropped
    return out


def premultiplied_resize(rgba, target_h):
    im = Image.fromarray(rgba, mode="RGBA")
    w, h = im.size
    if h == 0:
        return im
    scale = target_h / h
    target_w = max(1, round(w * scale))
    arr = np.array(im).astype(np.float32)
    a = arr[..., 3:4] / 255.0
    premult = np.concatenate([arr[..., :3] * a, arr[..., 3:4]], axis=-1).astype(np.uint8)
    pim = Image.fromarray(premult, mode="RGBA")
    pim = pim.resize((target_w, target_h), Image.Resampling.LANCZOS)
    parr = np.array(pim).astype(np.float32)
    pa = parr[..., 3:4]
    safe_a = np.where(pa > 0, pa, 1.0)
    rgb_un = np.clip(parr[..., :3] / (safe_a / 255.0), 0, 255)
    out = np.concatenate([rgb_un, pa], axis=-1).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def quantize_preserving_alpha(im, colors):
    alpha = im.split()[3]
    rgb = im.convert("RGB")
    quant = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGBA")
    quant.putalpha(alpha)
    return quant


def process_character(src_path, dst_path, log):
    im = Image.open(src_path)
    rgba = chroma_key(im)
    rgba = autocrop(rgba, pad=2)
    if rgba[..., 3].max() == 0:
        log.append(f"  ! {src_path.name}: fully transparent after keying, skipped")
        return False
    resized = premultiplied_resize(rgba, CHAR_TARGET_H)
    final = quantize_preserving_alpha(resized, CHAR_PALETTE_COLORS)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(dst_path, "PNG", optimize=True)
    log.append(f"  ✓ {src_path.name} -> {dst_path.name} ({final.width}x{final.height})")
    return True


def process_background(src_path, dst_path, log):
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    scale = BG_TARGET_W / w
    target_h = max(1, round(h * scale))
    im = im.resize((BG_TARGET_W, target_h), Image.Resampling.LANCZOS)
    im = im.quantize(colors=BG_PALETTE_COLORS, method=Image.Quantize.MEDIANCUT).convert("RGB")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst_path, "PNG", optimize=True)
    log.append(f"  ✓ {src_path.name} -> {dst_path.name} ({im.width}x{im.height})")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dir of raw <species>_<state>.png etc.")
    ap.add_argument("--out", required=True, help="dir to write processed sprites into")
    args = ap.parse_args()
    src_dir = Path(args.src)
    out_dir = Path(args.out)

    log = []
    made, missing, failed = 0, [], []
    for name, kind in expected_files():
        src_path = src_dir / f"{name}.png"
        dst_path = out_dir / f"{name}.png"
        if not src_path.exists() or src_path.stat().st_size == 0:
            missing.append(name)
            log.append(f"  ✗ {name}.png: MISSING/empty in {src_dir} — matrix fallback will be used")
            continue
        try:
            ok = process_character(src_path, dst_path, log) if kind == "character" else process_background(src_path, dst_path, log)
            if ok:
                made += 1
            else:
                failed.append(name)
        except Exception as e:  # noqa: BLE001 — report and keep going
            failed.append(name)
            log.append(f"  ✗ {name}.png: FAILED ({e})")

    print(f"Pet sprite pipeline: {src_dir} -> {out_dir}")
    for line in log:
        print(line)
    print(f"\n{made} produced, {len(missing)} missing (fallback), {len(failed)} failed.")
    if missing:
        print("Missing:", ", ".join(missing))
    if failed:
        print("Failed:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
