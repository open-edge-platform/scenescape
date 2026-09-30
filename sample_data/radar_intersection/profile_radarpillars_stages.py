#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stage-1 latency profile for RadarPillars host preproc + OV BEV.

Times voxelize / PillarVFE / PillarAttention / scatter / OV BEV / postproc on
the Python parity path (same math as ``g3dinference`` radarpillars runtime).
Use to decide what to OV-ify next; wait for confirmation before Stage 2.

Example::

  python3 sample_data/radar_intersection/profile_radarpillars_stages.py \\
    --frames-dir sample_data/radar_intersection/VIDETEC-2/converted/frames \\
    --config sample_data/radar_intersection/model_installer/FP16_ft2/radarpillars_ov_config.json \\
    --start-index 3270 --stop-index 3369 --accumulate-past 0 \\
    --accumulate-past-cmp 10 -o VIDETEC-2/profile_stages_ft2.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from radarpillars_infer import (  # noqa: E402
  RadarPillarsOV,
  _pillar_attention,
  _pillar_vfe,
  _postprocess_heads,
  _scatter,
  _voxelize,
)
from videtec_accumulate import accumulate_points_causal, load_vod_points  # noqa: E402


STAGES = ("voxelize", "vfe", "attention", "scatter", "ov_bev", "postproc", "total")


def _timed_infer(model: RadarPillarsOV, points: np.ndarray) -> dict[str, float]:
  """One forward; returns stage times in milliseconds + pillar/point counts."""
  cfg = model.cfg
  t0 = time.perf_counter()

  t = time.perf_counter()
  voxels, coors, num_points = _voxelize(
    points, cfg["point_cloud_range"], cfg["voxel_size"],
    cfg["max_points_per_voxel"], cfg["max_voxels"])
  t_vox = (time.perf_counter() - t) * 1e3

  t = time.perf_counter()
  pillars = _pillar_vfe(
    voxels, num_points, model.preproc,
    cfg["point_cloud_range"], cfg["voxel_size"])
  if pillars.shape[0] and pillars.shape[1] != cfg["bev_channels"]:
    out = np.zeros((pillars.shape[0], cfg["bev_channels"]), np.float32)
    n = min(pillars.shape[1], cfg["bev_channels"])
    out[:, :n] = pillars[:, :n]
    pillars = out
  t_vfe = (time.perf_counter() - t) * 1e3

  if pillars.shape[0] == 0:
    total = (time.perf_counter() - t0) * 1e3
    return {
      "voxelize": t_vox, "vfe": t_vfe, "attention": 0.0, "scatter": 0.0,
      "ov_bev": 0.0, "postproc": 0.0, "total": total,
      "n_points": int(points.shape[0]), "n_pillars": 0, "n_dets": 0,
    }

  t = time.perf_counter()
  pillars = _pillar_attention(pillars, model.preproc)
  t_attn = (time.perf_counter() - t) * 1e3

  t = time.perf_counter()
  nx, ny, _ = cfg["grid_size"]
  spatial = _scatter(pillars, coors, nx, ny, cfg["bev_channels"])
  t_scat = (time.perf_counter() - t) * 1e3

  t = time.perf_counter()
  result = model.compiled([spatial])
  outs = []
  if hasattr(result, "values"):
    for tens in result.values():
      outs.append(np.array(tens))
  else:
    outs = [np.array(tens) for tens in result]
  t_ov = (time.perf_counter() - t) * 1e3

  t = time.perf_counter()
  cls_preds = box_preds = dir_preds = None
  for a in outs:
    if a.ndim != 4:
      continue
    c = a.shape[1]
    if c == 18:
      cls_preds = a
    elif c == 42:
      box_preds = a
    elif c == 12:
      dir_preds = a
  if cls_preds is None or box_preds is None or dir_preds is None:
    cls_preds, box_preds, dir_preds = outs[0], outs[1], outs[2]
  objects = _postprocess_heads(cls_preds, box_preds, dir_preds, model.anchors, cfg)
  t_post = (time.perf_counter() - t) * 1e3
  total = (time.perf_counter() - t0) * 1e3
  return {
    "voxelize": t_vox, "vfe": t_vfe, "attention": t_attn, "scatter": t_scat,
    "ov_bev": t_ov, "postproc": t_post, "total": total,
    "n_points": int(points.shape[0]), "n_pillars": int(pillars.shape[0]),
    "n_dets": int(len(objects)),
  }


def _summarize(rows: list[dict]) -> dict:
  out: dict = {"n_frames": len(rows)}
  for key in STAGES + ("n_points", "n_pillars", "n_dets"):
    vals = [float(r[key]) for r in rows]
    out[key] = {
      "mean": statistics.fmean(vals),
      "median": statistics.median(vals),
      "p95": sorted(vals)[max(0, int(round(0.95 * (len(vals) - 1))))],
      "max": max(vals),
    }
  total_med = out["total"]["median"] or 1e-9
  out["share_of_median_total_pct"] = {
    s: 100.0 * out[s]["median"] / total_med for s in STAGES if s != "total"
  }
  return out


def _run_mode(
  model: RadarPillarsOV,
  frames_dir: Path,
  start: int,
  stop: int,
  past: int,
  warmup: int,
) -> dict:
  rows = []
  for fi in range(start, stop + 1):
    path = frames_dir / f"{fi:06d}.npy"
    if not path.is_file():
      path = frames_dir / f"{fi:06d}.bin"
    if not path.is_file():
      continue
    if past > 0:
      points = accumulate_points_causal(frames_dir, fi, past,
                                        extension=path.suffix)
    else:
      points = load_vod_points(path)
    row = _timed_infer(model, points)
    row["frame_index"] = fi
    rows.append(row)
  if len(rows) <= warmup:
    raise SystemExit(f"Need more than {warmup} frames; got {len(rows)}")
  measured = rows[warmup:]
  return {
    "accumulate_past": past,
    "warmup_frames": warmup,
    "summary": _summarize(measured),
    "per_frame": measured,
  }


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument("--config", type=Path, required=True)
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--start-index", type=int, default=3270)
  ap.add_argument("--stop-index", type=int, default=3369)
  ap.add_argument("--accumulate-past", type=int, default=0,
                  help="Primary densify mode (0 = single-frame).")
  ap.add_argument("--accumulate-past-cmp", type=int, default=None,
                  help="Optional second mode to compare (e.g. 10).")
  ap.add_argument("--warmup", type=int, default=5)
  ap.add_argument("--score-threshold", type=float, default=0.1)
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  model = RadarPillarsOV(args.config, device=args.device)
  model.cfg["score_threshold"] = float(args.score_threshold)

  modes = [args.accumulate_past]
  if args.accumulate_past_cmp is not None and args.accumulate_past_cmp != args.accumulate_past:
    modes.append(args.accumulate_past_cmp)

  report = {
    "config": str(args.config),
    "device": args.device,
    "frames_dir": str(args.frames_dir),
    "window": [args.start_index, args.stop_index],
    "score_threshold": float(args.score_threshold),
    "note": (
      "Python parity path (radarpillars_infer.py). Live g3dinference uses the "
      "same stages in C++; absolute ms may differ, stage ranking should match."
    ),
    "modes": [],
  }
  for past in modes:
    print(f"Profiling accumulate_past={past} …", flush=True)
    mode = _run_mode(
      model, args.frames_dir, args.start_index, args.stop_index, past, args.warmup)
    report["modes"].append(mode)
    s = mode["summary"]
    print(
      f"  past={past}: median total={s['total']['median']:.1f} ms  "
      f"pillars={s['n_pillars']['median']:.0f}  "
      f"attn={s['attention']['median']:.1f} ms "
      f"({s['share_of_median_total_pct']['attention']:.0f}%)  "
      f"vfe={s['vfe']['median']:.1f}  "
      f"ov_bev={s['ov_bev']['median']:.1f}",
      flush=True,
    )

  args.output.parent.mkdir(parents=True, exist_ok=True)
  # Drop per-frame detail from default write if huge? Keep it for analysis.
  args.output.write_text(json.dumps(report, indent=2) + "\n")
  print(f"Wrote {args.output}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
