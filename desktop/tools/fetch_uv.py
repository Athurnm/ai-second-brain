#!/usr/bin/env python3
"""Fetch the `uv` binary Tauri bundles as a sidecar.

The app ships `uv` so it can build a managed Python virtualenv for the harness's Python-backed
skills without ever asking the user to install Python. `uv` is a single static binary with no
runtime dependencies of its own, which is exactly why it was picked over vendoring CPython.

The binaries are NOT committed: they are ~15-35 MB each and there is one per platform. This
script downloads the right one for a target triple and drops it in `src-tauri/binaries/` under
the target-suffixed name Tauri's `externalBin` mechanism expects. CI runs it before
`tauri build`; developers run it once before their first local build.

Usage:
    python3 tools/fetch_uv.py                 # current host target
    python3 tools/fetch_uv.py --target <triple>
    python3 tools/fetch_uv.py --version 0.5.11

Stdlib only, so it runs on a bare CI image before any dependency install step.
"""

from __future__ import annotations

import argparse
import io
import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# Pinned rather than "latest": a silent uv upgrade between two builds of the same app version
# would make the shipped runtime non-reproducible. Bump deliberately.
DEFAULT_UV_VERSION = "0.5.11"

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "src-tauri" / "binaries"

# Tauri target triple -> the asset name uv publishes on GitHub Releases.
ASSETS: dict[str, str] = {
    "x86_64-unknown-linux-gnu": "uv-x86_64-unknown-linux-gnu.tar.gz",
    "aarch64-unknown-linux-gnu": "uv-aarch64-unknown-linux-gnu.tar.gz",
    "x86_64-apple-darwin": "uv-x86_64-apple-darwin.tar.gz",
    "aarch64-apple-darwin": "uv-aarch64-apple-darwin.tar.gz",
    "x86_64-pc-windows-msvc": "uv-x86_64-pc-windows-msvc.zip",
    "aarch64-pc-windows-msvc": "uv-aarch64-pc-windows-msvc.zip",
}


def host_target() -> str:
    """Best guess at the current host's Rust target triple."""
    machine = platform.machine().lower()
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine)
    if arch is None:
        sys.exit(f"Unsupported CPU architecture: {platform.machine()}")

    if sys.platform.startswith("linux"):
        return f"{arch}-unknown-linux-gnu"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    if sys.platform in ("win32", "cygwin"):
        return f"{arch}-pc-windows-msvc"
    sys.exit(f"Unsupported platform: {sys.platform}")


def extract(blob: bytes, asset: str) -> bytes:
    """Pull the `uv` executable out of the downloaded archive."""
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if Path(name).name == "uv.exe":
                    return zf.read(name)
        raise RuntimeError(f"No uv.exe inside {asset}")

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for member in tf.getmembers():
            if member.isfile() and Path(member.name).name == "uv":
                fh = tf.extractfile(member)
                if fh is not None:
                    return fh.read()
    raise RuntimeError(f"No uv binary inside {asset}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", default=None, help="Rust target triple (default: host)")
    ap.add_argument("--version", default=DEFAULT_UV_VERSION, help="uv version to fetch")
    args = ap.parse_args()

    target = args.target or host_target()
    asset = ASSETS.get(target)
    if asset is None:
        sys.exit(
            f"No uv asset mapped for target {target}.\n"
            f"Known targets: {', '.join(sorted(ASSETS))}"
        )

    suffix = ".exe" if "windows" in target else ""
    dest = BIN_DIR / f"uv-{target}{suffix}"
    if dest.exists():
        print(f"Already present: {dest}")
        return 0

    url = f"https://github.com/astral-sh/uv/releases/download/{args.version}/{asset}"
    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            blob = resp.read()
    except Exception as exc:  # noqa: BLE001 - any failure here is fatal and worth showing raw
        sys.exit(f"Download failed: {exc}")

    binary = extract(blob, asset)

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(binary)
    if not suffix:
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Wrote {dest} ({len(binary) / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
