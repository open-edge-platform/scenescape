#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Distill vehicle/cyclist boxes from the base VoD RadarPillars OV model.

Writes JSONL::
  {"frame_index": N, "objects": [{category, confidence, translation, size}, ...]}

Used by ``build_videtec_dataset.py --distill-jsonl`` to add non-person labels
for FT6. Exclude the demo eval window (3270–4100) at dataset-build time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_RI_ROOT = Path(__file__).resolve().parents[1]
if str(_RI_ROOT / "radarpillars") not in sys.path:
  sys.path.insert(0, str(_RI_ROOT / "radarpillars"))
if str(_RI_ROOT / "prepare") not in sys.path:
  sys.path.insert(0, str(_RI_ROOT / "prepare"))

from radarpillars_infer import RadarPillarsOV  # noqa: E402
from videtec_accumulate import load_vod_points  # noqa: E402

VEHICLE_LWH = (3.9, 1.6, 1.56)
CYCLIST_LWH = (1.76, 0.6, 1.73)


def _n_points_near(pcd: np.ndarray, xyz: np.ndarray, radius: float) -> int:
  if pcd.size == 0:
    return 0
  d = np.hypot(pcd[:, 0] - xyz[0], pcd[:, 1] - xyz[1])
  return int((d <= radius).sum())


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument(
    "--config", type=Path,
    default=_RI_ROOT / "model_installer/FP16/radarpillars_ov_config.json",
    help="Base VoD OV config (not FT2)")
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--score-threshold", type=float, default=0.15,
                  help="Keep distilled boxes at or above this confidence")
  ap.add_argument("--start-index", type=int, default=0)
  ap.add_argument("--stop-index", type=int, default=None)
  ap.add_argument("--stride", type=int, default=2)
  ap.add_argument("--categories", default="vehicle,cyclist")
  ap.add_argument("--min-points-near", type=int, default=2,
                  help="Require this many radar points within --near-radius-m")
  ap.add_argument("--near-radius-m", type=float, default=3.0)
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  keep_cats = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
  index = {int(e["frame_index"]): e
           for e in json.loads((args.frames_dir / "index.json").read_text())}
  model = RadarPillarsOV(args.config, device=args.device)
  model.cfg["score_threshold"] = float(args.score_threshold)
  start = args.start_index
  stop = args.stop_index if args.stop_index is not None else max(index)
  args.output.parent.mkdir(parents=True, exist_ok=True)
  n_frames = 0
  n_kept = 0
  with args.output.open("w") as fh:
    for fi in range(start, stop + 1, max(1, args.stride)):
      path = args.frames_dir / f"{fi:06d}.npy"
      if not path.is_file():
        continue
      points = load_vod_points(path)
      objects = []
      for obj in model.infer(points):
        cat = str(obj.get("category", "")).lower()
        if cat not in keep_cats:
          continue
        conf = float(obj.get("confidence", 0))
        if conf < args.score_threshold:
          continue
        xyz = np.asarray(obj["translation"][:3], dtype=np.float64)
        if _n_points_near(points, xyz, args.near_radius_m) < args.min_points_near:
          continue
        lwh = VEHICLE_LWH if cat == "vehicle" else CYCLIST_LWH
        objects.append({
          "category": cat,
          "confidence": conf,
          "translation": [float(x) for x in xyz],
          "size": list(lwh),
        })
        n_kept += 1
      fh.write(json.dumps({"frame_index": fi, "objects": objects}) + "\n")
      n_frames += 1
      if n_frames % 100 == 0:
        print(f"... {n_frames} frames, {n_kept} distilled boxes", flush=True)
  print(f"wrote {n_frames} frames, {n_kept} boxes → {args.output}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
