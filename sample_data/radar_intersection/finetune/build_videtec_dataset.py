#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Build a VoD/KITTI-style RadarPillars fine-tune set from VIDETEC-2 + GNSS.

Writes under ``--out`` (OpenPCDet / RadarPillar layout sketch)::

  training/velodyne/%06d.bin     float32 (N,7)
  training/label_2/%06d.txt      KITTI-like 3D box (GNSS VRU pseudo-label)
  training/calib/%06d.txt        identity stub (radar-local already)
  ImageSets/{train,val}.txt

Pseudo-label: one ``Pedestrian`` or ``Cyclist`` box at the GNSS position in
**radar-local** metres (UTM origin + /sensor pose). Size defaults match VoD
anchors roughly (person 0.8×0.6×1.73, cyclist 1.76×0.6×1.73).

Point filter: drop detections with |elevation| > ``--max-abs-elev-deg`` to
suppress VIDETEC elevation outliers that explode Z outside VoD range.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from eval_radarpillars_gnss import (  # noqa: E402
  VIDETEC_UTM_EASTING_M,
  VIDETEC_UTM_NORTHING_M,
  _to_seconds,
  load_gnss_csv,
  world_to_radar_xy,
)
from videtec_to_pcd import videtec_to_pcd  # noqa: E402

# VoD-ish default sizes (l, w, h) metres — OpenPCDet KITTI order in label is h w l
PERSON_LWH = (0.8, 0.6, 1.73)
CYCLIST_LWH = (1.76, 0.6, 1.73)


def _kitti_label_line(cls: str, x: float, y: float, z: float, lwh: tuple[float, float, float],
                      yaw: float = 0.0) -> str:
  """KITTI label in camera frame normally; we store radar-local as x forward, y left, z up.

  OpenPCDet VoD radar path still expects KITTI text; RadarPillar dataset code
  maps these into lidar/radar frame. We write: type … h w l x y z rotation_y
  with (x,y,z) = radar-local centre and h,w,l = size.
  """
  l, w, h = lwh
  # truncated..score placeholders
  return (
    f"{cls} 0.0 0 0.0 0.0 0.0 0.0 0.0 "
    f"{h:.4f} {w:.4f} {l:.4f} {x:.4f} {y:.4f} {z:.4f} {yaw:.4f}\n"
  )


def _identity_calib() -> str:
  # Valid KITTI-like stub: radar-local boxes are written as camera-frame with
  # identity Tr_velo_to_cam, so OpenPCDet's camera→lidar path is a no-op on XY
  # (plus the usual bottom→center Z / yaw adjust). P2 must have fy≠0 or ty=NaN.
  p2 = "721.5377 0.0 609.5593 0.0 0.0 721.5377 172.854 0.0 0.0 0.0 1.0 0.0"
  return (
    f"P0: {p2}\nP1: {p2}\nP2: {p2}\nP3: {p2}\n"
    "R0_rect: 1 0 0 0 1 0 0 0 1\n"
    "Tr_velo_to_cam: 1 0 0 0 0 1 0 0 0 0 1 0\n"
    "Tr_imu_to_velo: 1 0 0 0 0 1 0 0 0 0 1 0\n"
  )


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument("--gnss", type=Path, required=True)
  ap.add_argument("--sensor", type=Path, required=True)
  ap.add_argument("-o", "--out", type=Path, required=True)
  ap.add_argument("--vru-class", choices=("Pedestrian", "Cyclist"), default="Pedestrian",
                  help="KITTI class name for the instrumented VRU (Oct-9 run is pedestrian)")
  ap.add_argument("--max-abs-elev-deg", type=float, default=20.0)
  ap.add_argument("--max-dt", type=float, default=0.15)
  ap.add_argument("--pc-range", type=float, nargs=6,
                  default=[-20.0, -40.0, -5.0, 60.0, 40.0, 3.0],
                  help="Keep frames whose GNSS radar-local XY lies in this box "
                       "(gantry-expanded vs VoD forward-only)")
  ap.add_argument("--min-points", type=int, default=3)
  ap.add_argument("--near-gt-radius-m", type=float, default=3.0,
                  help="Association radius (m) around GNSS for point support / snap")
  ap.add_argument("--min-points-near-gt", type=int, default=1,
                  help="Require at least this many points within --near-gt-radius-m")
  ap.add_argument("--snap-gt-to-points", action="store_true", default=True,
                  help="Move box XY to mean of points within radius (default on)")
  ap.add_argument("--no-snap-gt-to-points", action="store_false", dest="snap_gt_to_points")
  ap.add_argument("--box-lwh", type=float, nargs=3, default=None,
                  metavar=("L", "W", "H"),
                  help="Override box size (default: larger sparse-radar person 1.2 0.8 1.73)")
  ap.add_argument("--val-fraction", type=float, default=0.2)
  ap.add_argument("--stride", type=int, default=1)
  ap.add_argument("--z-ground", type=float, default=None,
                  help="Override box bottom Z (default: -mounting_height_m; KITTI bottom)")
  ap.add_argument("--z-from-points", action="store_true", default=True,
                  help="Set box Z from median near-GT point Z - half_h (default on)")
  ap.add_argument("--no-z-from-points", action="store_false", dest="z_from_points")
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  index = json.loads((args.frames_dir / "index.json").read_text())
  sensor = json.loads(args.sensor.read_text())
  gnss = load_gnss_csv(
    args.gnss,
    origin_utm_easting=VIDETEC_UTM_EASTING_M,
    origin_utm_northing=VIDETEC_UTM_NORTHING_M,
  )
  g_t = gnss["t"]
  if args.box_lwh is not None:
    lwh = tuple(float(x) for x in args.box_lwh)
  elif args.vru_class == "Pedestrian":
    # Slightly larger than VoD person anchor — sparse gantry returns need a bigger
    # association volume (FT2: 72% of kept frames had 0 pts within 2 m of GNSS).
    lwh = (1.2, 0.8, 1.73)
  else:
    lwh = CYCLIST_LWH
  half_h = lwh[2] / 2.0
  mount = float(sensor.get("mounting_height_m", 4.5))
  z_bottom_default = args.z_ground if args.z_ground is not None else (-mount)

  velo = args.out / "training" / "velodyne"
  lab = args.out / "training" / "label_2"
  cal = args.out / "training" / "calib"
  sets = args.out / "ImageSets"
  for d in (velo, lab, cal, sets):
    d.mkdir(parents=True, exist_ok=True)

  x0, y0, _z0, x1, y1, _z1 = args.pc_range
  kept = []
  skipped = {"dt": 0, "range": 0, "points": 0, "near_gt": 0, "missing": 0}

  for entry in index:
    fi = int(entry["frame_index"])
    if fi % max(1, args.stride) != 0:
      continue
    if "timestamp" not in entry:
      continue
    t = float(_to_seconds(np.array([entry["timestamp"]]))[0])
    j = int(np.argmin(np.abs(g_t - t)))
    if abs(float(g_t[j] - t)) > args.max_dt:
      skipped["dt"] += 1
      continue
    gx, gy = world_to_radar_xy(
      np.array([gnss["x"][j]]), np.array([gnss["y"][j]]), sensor)
    gx, gy = float(gx[0]), float(gy[0])
    if not (x0 <= gx <= x1 and y0 <= gy <= y1):
      skipped["range"] += 1
      continue
    npy = args.frames_dir / f"{fi:06d}.npy"
    if not npy.is_file():
      skipped["missing"] += 1
      continue
    frame = np.load(npy)
    if frame.size and args.max_abs_elev_deg is not None:
      mask = np.abs(frame[:, 3]) <= args.max_abs_elev_deg
      frame = frame[mask]
    pcd = videtec_to_pcd(frame)
    if pcd.shape[0] < args.min_points:
      skipped["points"] += 1
      continue

    dxy = np.hypot(pcd[:, 0] - gx, pcd[:, 1] - gy)
    near = dxy <= float(args.near_gt_radius_m)
    n_near = int(near.sum())
    if n_near < int(args.min_points_near_gt):
      skipped["near_gt"] += 1
      continue

    bx, by = gx, gy
    if args.snap_gt_to_points and n_near > 0:
      bx = float(pcd[near, 0].mean())
      by = float(pcd[near, 1].mean())

    if args.z_from_points and n_near > 0:
      # KITTI label Z is bottom of object; OpenPCDet then adds h/2 → center.
      z_center = float(np.median(pcd[near, 2]))
      z_label = z_center - half_h
    else:
      z_label = float(z_bottom_default)

    sid = len(kept)
    pcd.astype(np.float32).tofile(velo / f"{sid:06d}.bin")
    (lab / f"{sid:06d}.txt").write_text(
      _kitti_label_line(args.vru_class, bx, by, z_label, lwh))
    (cal / f"{sid:06d}.txt").write_text(_identity_calib())
    kept.append({
      "seq_id": sid, "frame_index": fi, "gx": gx, "gy": gy,
      "bx": bx, "by": by, "n": int(pcd.shape[0]), "n_near": n_near,
      "snap_shift_m": float(math.hypot(bx - gx, by - gy)),
    })

  n = len(kept)
  if n == 0:
    raise SystemExit(f"no samples kept; skipped={skipped}")
  rng = np.random.default_rng(0)
  order = np.arange(n)
  rng.shuffle(order)
  n_val = max(1, int(round(n * args.val_fraction)))
  val_ids = set(int(i) for i in order[:n_val])
  train_lines, val_lines = [], []
  for k in kept:
    line = f"{k['seq_id']:06d}\n"
    (val_lines if k["seq_id"] in val_ids else train_lines).append(line)
  (sets / "train.txt").write_text("".join(train_lines))
  (sets / "val.txt").write_text("".join(val_lines))
  shifts = np.array([k["snap_shift_m"] for k in kept], dtype=np.float64)
  near_counts = np.array([k["n_near"] for k in kept], dtype=np.float64)
  meta = {
    "n_samples": n,
    "n_train": len(train_lines),
    "n_val": len(val_lines),
    "vru_class": args.vru_class,
    "pc_range": list(args.pc_range),
    "max_abs_elev_deg": args.max_abs_elev_deg,
    "box_lwh": list(lwh),
    "near_gt_radius_m": args.near_gt_radius_m,
    "min_points_near_gt": args.min_points_near_gt,
    "snap_gt_to_points": args.snap_gt_to_points,
    "z_from_points": args.z_from_points,
    "snap_shift_m": {
      "mean": float(shifts.mean()),
      "median": float(np.median(shifts)),
      "p95": float(np.percentile(shifts, 95)),
    },
    "n_near": {
      "mean": float(near_counts.mean()),
      "median": float(np.median(near_counts)),
    },
    "skipped": skipped,
    "source": "VIDETEC-2 + GNSS pseudo-labels (associated)",
  }
  (args.out / "dataset_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
  (args.out / "kept_index.json").write_text(json.dumps(kept) + "\n")
  print(json.dumps(meta, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
