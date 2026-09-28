#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Rebuild RadarIntersection-scene-import.zip from JSON + map PNG.

Source of truth for sensors is ``RadarIntersection.json``. The ZIP is what
``radar-scene-init`` imports on a fresh machine (map + initial scene);
``radar_scene_init.py`` then re-syncs every camera/radar from the JSON so
poses stay portable across hosts without a live DB dump.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_JSON = _HERE / "RadarIntersection.json"
# Mapbox snapshot (preferred); fall back to legacy spaced filename.
_DEFAULT_MAP = _HERE / "RadarIntersection.png"
_LEGACY_MAP = _HERE / "Radar Intersection.png"
_DEFAULT_ZIP = _HERE / "RadarIntersection-scene-import.zip"
# Scene-import ZIP entry name (Manager media key uses the basename).
_ZIP_MAP_NAME = "Radar Intersection.png"


def pack(scene_json: Path, map_png: Path, out_zip: Path) -> None:
  if not scene_json.is_file():
    raise SystemExit(f"missing scene JSON: {scene_json}")
  if not map_png.is_file():
    raise SystemExit(f"missing map image: {map_png}")
  out_zip.parent.mkdir(parents=True, exist_ok=True)
  with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.write(scene_json, arcname="RadarIntersection.json")
    zf.write(map_png, arcname=_ZIP_MAP_NAME)
  print(f"wrote {out_zip} ({out_zip.stat().st_size} bytes) map={map_png.name}")


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--json", type=Path, default=_DEFAULT_JSON)
  ap.add_argument(
    "--map", type=Path, default=None,
    help="Map PNG (default: RadarIntersection.png, else legacy spaced name)")
  ap.add_argument("-o", "--output", type=Path, default=_DEFAULT_ZIP)
  args = ap.parse_args()
  map_png = args.map
  if map_png is None:
    map_png = _DEFAULT_MAP if _DEFAULT_MAP.is_file() else _LEGACY_MAP
  pack(args.json, map_png, args.output)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
