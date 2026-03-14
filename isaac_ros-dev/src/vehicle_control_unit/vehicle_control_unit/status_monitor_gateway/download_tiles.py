#!/usr/bin/env python3
"""
download_tiles.py — Pre-download OSM tiles for offline use.

Usage:
    python -m status_monitor_gateway.download_tiles \
        --lat 36.162 --lon -85.501 \
        --radius-m 800 \
        --min-zoom 14 --max-zoom 19 \
        --out tiles

The downloaded tiles are saved as:
    <out>/{z}/{x}/{y}.png

The FastAPI server in webapp.py serves them at:
    GET /tiles/{z}/{x}/{y}.png

OSM tile usage policy: https://operations.osmfoundation.org/policies/tiles/
Keep --max-zoom ≤ 19 and --radius-m reasonable (< 2 km) to stay within fair-use.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import urllib.request
from pathlib import Path


# OSM tile math ---------------------------------------------------------------

def deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile2deg(x: int, y: int, zoom: int) -> tuple[float, float]:
    """Return the NW corner (lat, lon) of tile (x, y, z)."""
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def meters_per_pixel(lat_deg: float, zoom: int) -> float:
    return 156_543.03 * math.cos(math.radians(lat_deg)) / (2 ** zoom)


def tile_range_for_radius(
    lat: float, lon: float, radius_m: float, zoom: int
) -> tuple[int, int, int, int]:
    """Return (x_min, x_max, y_min, y_max) tile indices covering a circle."""
    mpp = meters_per_pixel(lat, zoom)
    tile_size_m = mpp * 256
    pad = math.ceil(radius_m / tile_size_m) + 1

    cx, cy = deg2tile(lat, lon, zoom)
    return cx - pad, cx + pad, cy - pad, cy + pad


# Download logic --------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "IGVC-StatusMonitor/1.0 offline-tile-downloader "
        "(https://github.com/your-team/igvc; contact@example.com)"
    )
}
OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DELAY_S = 0.5        # be polite — OSM fair-use asks for ≥ 1 req/s max


def download_tile(z: int, x: int, y: int, out_dir: Path, retries: int = 3) -> bool:
    dest = out_dir / str(z) / str(x) / f"{y}.png"
    if dest.exists():
        return True  # already cached

    dest.parent.mkdir(parents=True, exist_ok=True)
    url = OSM_URL.format(z=z, x=x, y=y)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                dest.write_bytes(resp.read())
            return True
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(1.0)
            else:
                print(f"  FAIL {z}/{x}/{y}: {exc}", file=sys.stderr)
    return False


def download_area(
    lat: float,
    lon: float,
    radius_m: float,
    min_zoom: int,
    max_zoom: int,
    out_dir: Path,
) -> None:
    total_tiles = 0
    plan: list[tuple[int, int, int]] = []

    for z in range(min_zoom, max_zoom + 1):
        x0, x1, y0, y1 = tile_range_for_radius(lat, lon, radius_m, z)
        n = 2 ** z
        x0, x1 = max(0, x0), min(n - 1, x1)
        y0, y1 = max(0, y0), min(n - 1, y1)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                plan.append((z, x, y))

    total_tiles = len(plan)
    print(f"Tiles to download: {total_tiles}  (centre {lat:.5f}, {lon:.5f}  r={radius_m}m  z{min_zoom}–{max_zoom})")
    print(f"Output directory : {out_dir.resolve()}")

    ok = skip = fail = 0
    for i, (z, x, y) in enumerate(plan, 1):
        dest = out_dir / str(z) / str(x) / f"{y}.png"
        if dest.exists():
            skip += 1
            continue

        success = download_tile(z, x, y, out_dir)
        if success:
            ok += 1
        else:
            fail += 1

        if i % 20 == 0 or i == total_tiles:
            pct = 100 * i / total_tiles
            print(f"  [{i:4d}/{total_tiles}] {pct:.0f}%  ok={ok} skip={skip} fail={fail}")

        time.sleep(DELAY_S)

    print(f"\nDone. ok={ok}  skipped={skip}  failed={fail}")
    if fail:
        print("Some tiles failed. Re-run the script to retry only failed tiles.", file=sys.stderr)


# CLI -------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download OSM tiles for offline use.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--lat",       type=float, required=True,  help="Centre latitude")
    parser.add_argument("--lon",       type=float, required=True,  help="Centre longitude")
    parser.add_argument("--radius-m",  type=float, default=500.0,  help="Coverage radius in metres")
    parser.add_argument("--min-zoom",  type=int,   default=14,     help="Minimum zoom level")
    parser.add_argument("--max-zoom",  type=int,   default=19,     help="Maximum zoom level (≤19 recommended)")
    parser.add_argument("--out",       type=str,   default="tiles", help="Output directory")
    args = parser.parse_args()

    if args.max_zoom > 19:
        print("Warning: zoom > 19 is not available on OSM and will produce only failed downloads.")

    out_dir = Path(args.out)
    download_area(
        lat=args.lat,
        lon=args.lon,
        radius_m=args.radius_m,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
        out_dir=out_dir,
    )


if __name__ == "__main__":
    main()