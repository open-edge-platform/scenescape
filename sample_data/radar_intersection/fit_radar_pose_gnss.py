#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fit radar scene extrinsics (x, y, z, yaw) to GNSS VRU tracks.

Detections stay in radar-local metres (+X forward, +Y left, +Z up). Pose is
SceneScape euler XYZ with yaw-only rotation (roll=pitch=0), matching
``CameraPose.pose_mat @ p``. GNSS is mapped VIDETEC local ENU → scene via the
Mapbox offsets in ``videtec_map_calibration.json``.

Primary score: recall @ 3 m + median XY error on person-like boxes.
Z is chosen so matched detections land near a target scene height (default
1.0 m), i.e. the effective height for this detector's box Z convention.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from eval_radarpillars_gnss import (  # noqa: E402
  VIDETEC_UTM_EASTING_M,
  VIDETEC_UTM_NORTHING_M,
  VIDETEC_UTM_ZONE,
  _to_seconds,
  load_detections_jsonl,
  load_frame_index,
  load_gnss_csv,
)

PERSON_LIKE = {"person", "pedestrian", "cyclist", "bicycle"}


def _scene_offsets(calib: dict) -> tuple[float, float]:
  return -float(calib["local_xmin_m"]), -float(calib["local_ymin_m"])


def _yaw_mat(yaw_deg: float) -> np.ndarray:
  c = math.cos(math.radians(yaw_deg))
  s = math.sin(math.radians(yaw_deg))
  return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def _collect_frames(
  index: list[dict],
  dets: dict[int, dict],
  gnss: np.ndarray,
  *,
  ox: float,
  oy: float,
  max_dt_s: float,
  frame_lo: int | None,
  frame_hi: int | None,
) -> list[tuple[np.ndarray, np.ndarray]]:
  """Per usable frame: (dets_xyz Mx3, gnss_xy_scene 2,)."""
  index_by = {int(e["frame_index"]): e for e in index if "timestamp" in e}
  g_t = gnss["t"]
  out: list[tuple[np.ndarray, np.ndarray]] = []
  for frame_index, det in sorted(dets.items()):
    fi = int(frame_index)
    if frame_lo is not None and fi < frame_lo:
      continue
    if frame_hi is not None and fi > frame_hi:
      continue
    entry = index_by.get(fi)
    if entry is None:
      if "timestamp" not in det:
        continue
      t = float(det["timestamp"])
    else:
      t = float(entry["timestamp"])
    t = float(_to_seconds(np.array([t]))[0])
    j = int(np.argmin(np.abs(g_t - t)))
    if abs(float(g_t[j] - t)) > max_dt_s:
      continue
    pts = []
    for obj in det.get("objects") or []:
      cat = str(obj.get("category", obj.get("label", ""))).lower()
      if cat and cat not in PERSON_LIKE:
        continue
      tr = obj.get("translation") or obj.get("center")
      if not tr or len(tr) < 2:
        continue
      z = float(tr[2]) if len(tr) > 2 else 0.0
      pts.append((float(tr[0]), float(tr[1]), z))
    if not pts:
      continue
    gxy = np.array([float(gnss["x"][j]) + ox, float(gnss["y"][j]) + oy],
                   dtype=np.float64)
    out.append((np.asarray(pts, dtype=np.float64), gxy))
  if not out:
    raise SystemExit("no time-aligned person detections vs GNSS")
  return out


def _score_frames(
  frames: list[tuple[np.ndarray, np.ndarray]],
  tx: float,
  ty: float,
  yaw_deg: float,
  dist_m: float,
) -> tuple[float, float, float, list[float]]:
  R = _yaw_mat(yaw_deg)
  errs: list[float] = []
  matched_z_local: list[float] = []
  hits = 0
  for dets, gxy in frames:
    world = dets @ R.T
    d = np.hypot(world[:, 0] + tx - gxy[0], world[:, 1] + ty - gxy[1])
    k = int(np.argmin(d))
    best = float(d[k])
    if best <= dist_m:
      hits += 1
      errs.append(best)
      matched_z_local.append(float(dets[k, 2]))
  n = len(frames)
  recall = hits / n if n else 0.0
  med = float(np.median(errs)) if errs else 1e9
  score = recall * 100.0 - min(med, 50.0)
  return score, recall, med, matched_z_local


def _best_on_yaw_grid(
  frames: list[tuple[np.ndarray, np.ndarray]],
  yaw: float,
  xs: np.ndarray,
  ys: np.ndarray,
  dist_m: float,
) -> tuple[float, float, float, float, float]:
  """Return (score, recall, med, best_x, best_y) for one yaw over an XY grid."""
  R = _yaw_mat(yaw)
  TX, TY = np.meshgrid(xs, ys, indexing="ij")  # (Gx, Gy)
  hit = np.zeros(TX.shape, dtype=np.int32)
  # Keep top errors list per cell is heavy; track sum of capped errors + count.
  err_sum = np.zeros(TX.shape, dtype=np.float64)
  err_cnt = np.zeros(TX.shape, dtype=np.int32)
  # For median we only need it at the winner — compute exact score via recall
  # proxy first (hit count), then refine top-K cells.
  min_d = np.full(TX.shape, np.inf, dtype=np.float64)
  for dets, gxy in frames:
    world = dets @ R.T  # (M,3)
    # d[m,i,j] = hypot(TX[i,j] + wx[m] - gx, ...)
    dx = TX[None, :, :] + world[:, 0, None, None] - gxy[0]
    dy = TY[None, :, :] + world[:, 1, None, None] - gxy[1]
    d = np.sqrt(dx * dx + dy * dy).min(axis=0)  # (Gx, Gy)
    matched = d <= dist_m
    hit += matched.astype(np.int32)
    err_sum += np.where(matched, d, 0.0)
    err_cnt += matched.astype(np.int32)
    min_d = np.minimum(min_d, d)

  n = len(frames)
  recall = hit.astype(np.float64) / max(n, 1)
  mean_err = np.where(err_cnt > 0, err_sum / np.maximum(err_cnt, 1), 50.0)
  score = recall * 100.0 - np.minimum(mean_err, 50.0)
  # Prefer high recall; break ties with lower mean err
  flat = np.argmax(score * 1e6 + recall * 1e3 - mean_err)
  ix, iy = np.unravel_index(int(flat), score.shape)
  bx, by = float(xs[ix]), float(ys[iy])
  # Exact median at winner
  _, rec, med, _ = _score_frames(frames, bx, by, yaw, dist_m)
  return float(score[ix, iy]), float(rec), float(med), bx, by


def fit_pose(
  frames: list[tuple[np.ndarray, np.ndarray]],
  *,
  x0: float,
  y0: float,
  z0: float,
  yaw0: float,
  z_target: float,
  dist_m: float,
) -> dict:
  best = (-1e18, 0.0, 1e9, x0, y0, yaw0)

  print("[fit] coarse yaw/XY grid...", flush=True)
  yaw_coarse = np.linspace(yaw0 - 40.0, yaw0 + 40.0, 33)
  xs = x0 + np.linspace(-25.0, 25.0, 51)
  ys = y0 + np.linspace(-25.0, 25.0, 51)
  for yaw in yaw_coarse:
    sc, rec, med, bx, by = _best_on_yaw_grid(frames, float(yaw), xs, ys, dist_m)
    key = (sc, rec, -med)
    if key > (best[0], best[1], -best[2]):
      best = (sc, rec, med, bx, by, float(yaw))

  _, _, _, bx, by, byaw = best
  print(f"[fit] coarse best xy=({bx:.2f},{by:.2f}) yaw={byaw:.2f} "
        f"recall={best[1]:.3f} med={best[2]:.2f}", flush=True)

  print("[fit] fine yaw/XY grid...", flush=True)
  yaw_fine = np.linspace(byaw - 5.0, byaw + 5.0, 21)
  xs = bx + np.linspace(-3.0, 3.0, 25)
  ys = by + np.linspace(-3.0, 3.0, 25)
  for yaw in yaw_fine:
    sc, rec, med, x, y = _best_on_yaw_grid(frames, float(yaw), xs, ys, dist_m)
    key = (sc, rec, -med)
    if key > (best[0], best[1], -best[2]):
      best = (sc, rec, med, x, y, float(yaw))

  sc, rec, med, bx, by, byaw = best
  print(f"[fit] fine best xy=({bx:.2f},{by:.2f}) yaw={byaw:.2f} "
        f"recall={rec:.3f} med={med:.2f}", flush=True)

  _, _, _, matched_z_local = _score_frames(frames, bx, by, byaw, dist_m)
  if matched_z_local:
    bz = float(z_target - float(np.median(matched_z_local)))
  else:
    bz = float(z0)

  return {
    "translation": [float(bx), float(by), float(bz)],
    "rotation": [0.0, 0.0, float(byaw)],
    "recall_at_m": float(dist_m),
    "recall": float(rec),
    "median_xy_err_m": float(med) if med < 1e8 else None,
    "median_matched_z_local": (
      float(np.median(matched_z_local)) if matched_z_local else None),
    "median_matched_z_world": (
      float(np.median(np.asarray(matched_z_local) + bz))
      if matched_z_local else None),
    "n_gnss_frames_scored": int(len(frames)),
    "n_matched": int(round(rec * len(frames))),
    "bootstrap": {"x": x0, "y": y0, "z": z0, "yaw": yaw0},
    "z_target_m": float(z_target),
  }


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--detections",
    type=Path,
    default=_HERE / "VIDETEC-2/detections_w2100_4100_ft2ep11_acc5.jsonl",
  )
  ap.add_argument(
    "--index",
    type=Path,
    default=_HERE / "VIDETEC-2/converted/frames/index.json",
  )
  ap.add_argument(
    "--gnss",
    type=Path,
    default=_HERE / "VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55"
    "/rosbag2_2025_10_09-14_43_55_0_gps.csv",
  )
  ap.add_argument(
    "--calib",
    type=Path,
    default=_HERE / "videtec_map_calibration.json",
  )
  ap.add_argument(
    "--sensor", type=Path,
    default=_HERE / "VIDETEC-2/converted/frames/sensor.json")
  ap.add_argument("--frame-start", type=int, default=3270)
  ap.add_argument("--frame-stop", type=int, default=4100)
  ap.add_argument("--max-dt", type=float, default=0.2)
  ap.add_argument("--dist", type=float, default=3.0)
  ap.add_argument("--z-target", type=float, default=1.0)
  ap.add_argument("--bootstrap-x", type=float, default=None)
  ap.add_argument("--bootstrap-y", type=float, default=None)
  ap.add_argument("--bootstrap-z", type=float, default=None)
  ap.add_argument("--bootstrap-yaw", type=float, default=None)
  ap.add_argument(
    "-o", "--output", type=Path,
    default=_HERE / "radar_pose_gnss_fit.json")
  args = ap.parse_args()

  calib = json.loads(args.calib.read_text())
  ox, oy = _scene_offsets(calib)
  sensor = json.loads(args.sensor.read_text())

  gnss = load_gnss_csv(
    args.gnss,
    origin_utm_easting=VIDETEC_UTM_EASTING_M,
    origin_utm_northing=VIDETEC_UTM_NORTHING_M,
    utm_zone=VIDETEC_UTM_ZONE,
  )
  index = load_frame_index(args.index)
  dets = load_detections_jsonl(args.detections)
  frames = _collect_frames(
    index, dets, gnss,
    ox=ox, oy=oy, max_dt_s=args.max_dt,
    frame_lo=args.frame_start, frame_hi=args.frame_stop,
  )
  print(
    f"[fit] frames={len(frames)} scene_offset=({ox},{oy}) "
    f"window={args.frame_start}-{args.frame_stop}",
    flush=True,
  )

  pos = sensor.get("position_xyz_m") or [0.0, 0.0, 4.5]
  yaw0 = float(
    args.bootstrap_yaw if args.bootstrap_yaw is not None
    else sensor.get("orientation_yaw_deg", 0.0))
  x0 = float(args.bootstrap_x if args.bootstrap_x is not None else float(pos[0]) + ox)
  y0 = float(args.bootstrap_y if args.bootstrap_y is not None else float(pos[1]) + oy)
  z0 = float(args.bootstrap_z if args.bootstrap_z is not None else float(pos[2]))

  result = fit_pose(
    frames, x0=x0, y0=y0, z0=z0, yaw0=yaw0,
    z_target=args.z_target, dist_m=args.dist,
  )
  result["method"] = (
    "gnss_xy_yaw_grid + z = z_target - median(matched z_local); "
    "yaw-only euler; FT2 densify dets"
  )
  result["inputs"] = {
    "detections": str(args.detections),
    "gnss": str(args.gnss),
    "frame_start": args.frame_start,
    "frame_stop": args.frame_stop,
  }
  args.output.write_text(json.dumps(result, indent=2) + "\n")
  print(json.dumps(result, indent=2), flush=True)
  print(f"[fit] wrote {args.output}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
