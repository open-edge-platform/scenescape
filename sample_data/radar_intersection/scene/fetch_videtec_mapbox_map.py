#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fetch a Mapbox satellite map for the VIDETEC-2 intersection and write
calibration metadata used by ``RadarIntersection.json``.

Requires ``MAPBOX_API_KEY`` (or ``MAPBOX_ACCESS_TOKEN``) in the environment.
Does **not** persist the key to disk.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# VIDETEC-2 published local origin (Zenodo 17799385).
ORIGIN_LAT = 48.2494788974
ORIGIN_LON = 11.6310746174
DEFAULT_XMIN, DEFAULT_XMAX = -50.0, 90.0
DEFAULT_YMIN, DEFAULT_YMAX = -70.0, 70.0


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--out-dir", type=Path,
    default=Path("sample_data/radar_intersection"))
  ap.add_argument("--width", type=int, default=1280)
  ap.add_argument("--xmin", type=float, default=DEFAULT_XMIN)
  ap.add_argument("--xmax", type=float, default=DEFAULT_XMAX)
  ap.add_argument("--ymin", type=float, default=DEFAULT_YMIN)
  ap.add_argument("--ymax", type=float, default=DEFAULT_YMAX)
  ap.add_argument(
    "--style", default="mapbox/satellite-streets-v12")
  args = ap.parse_args()

  key = (
    os.environ.get("MAPBOX_API_KEY")
    or os.environ.get("MAPBOX_ACCESS_TOKEN")
    or ""
  ).strip()
  if not key:
    print("Set MAPBOX_API_KEY or MAPBOX_ACCESS_TOKEN", file=sys.stderr)
    return 1

  lat0, lon0 = ORIGIN_LAT, ORIGIN_LON
  m_per_deg_lat = 111320.0
  m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))

  def enu_to_ll(x: float, y: float) -> tuple[float, float]:
    return lon0 + x / m_per_deg_lon, lat0 + y / m_per_deg_lat

  corners = [
    enu_to_ll(args.xmin, args.ymin),
    enu_to_ll(args.xmax, args.ymin),
    enu_to_ll(args.xmin, args.ymax),
    enu_to_ll(args.xmax, args.ymax),
  ]
  lons = [c[0] for c in corners]
  lats = [c[1] for c in corners]
  min_lon, max_lon = min(lons), max(lons)
  min_lat, max_lat = min(lats), max(lats)
  w_m = args.xmax - args.xmin
  h_m = args.ymax - args.ymin
  width = args.width
  height = int(round(width * h_m / w_m))
  if height % 2:
    height += 1
  scale = width / w_m

  path = (
    f"/styles/v1/{args.style}/static/"
    f"[{min_lon},{min_lat},{max_lon},{max_lat}]/{width}x{height}"
  )
  url = (
    f"https://api.mapbox.com{path}"
    f"?access_token={urllib.parse.quote(key)}"
    "&attribution=false&logo=false"
  )
  print(f"[videtec-map] fetching {path}", flush=True)
  req = urllib.request.Request(url, headers={"User-Agent": "scenescape-videtec-map/1.0"})
  with urllib.request.urlopen(req, timeout=60) as resp:
    data = resp.read()
  args.out_dir.mkdir(parents=True, exist_ok=True)
  png_path = args.out_dir / "RadarIntersection.png"
  # Mapbox may return JPEG; convert to PNG when Pillow is available.
  try:
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(data))
    im.save(png_path, format="PNG")
  except Exception:
    png_path.write_bytes(data)
    print("[videtec-map] warning: wrote raw bytes (install Pillow for PNG)", flush=True)

  meta = {
    "source": "mapbox static",
    "style": args.style,
    "origin_lat": lat0,
    "origin_lon": lon0,
    "local_xmin_m": args.xmin,
    "local_xmax_m": args.xmax,
    "local_ymin_m": args.ymin,
    "local_ymax_m": args.ymax,
    "width_px": width,
    "height_px": height,
    "scale_pixels_per_meter": scale,
    "map_corners_lla_ccw_from_sw": [
      [lat0 + args.ymin / m_per_deg_lat, lon0 + args.xmin / m_per_deg_lon, 484.0],
      [lat0 + args.ymin / m_per_deg_lat, lon0 + args.xmax / m_per_deg_lon, 484.0],
      [lat0 + args.ymax / m_per_deg_lat, lon0 + args.xmax / m_per_deg_lon, 484.0],
      [lat0 + args.ymax / m_per_deg_lat, lon0 + args.xmin / m_per_deg_lon, 484.0],
    ],
  }
  cal_path = args.out_dir / "videtec_map_calibration.json"
  cal_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
  print(f"[videtec-map] wrote {png_path} scale={scale:.4f} px/m", flush=True)
  print(f"[videtec-map] wrote {cal_path}", flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
