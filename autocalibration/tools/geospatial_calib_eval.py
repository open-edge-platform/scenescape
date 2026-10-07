#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Accuracy harness for geospatial map calibration.

Runs the service engine (autocalibration/src/geospatial_map_calibration.py) on a
SceneScape scene export whose cameras were manually calibrated with 3d-2d point
correspondences; those manual poses are the ground truth. Use --set to try
GeoCalibConfig changes and --out to keep a JSON report for comparing runs.

Example (Smart Intersection export, run from the repository root):
  python3 autocalibration/tools/geospatial_calib_eval.py \\
    --scene-export /tmp/si-fixture \\
    --frame camera1=frames/1122south.jpg --frame camera2=frames/1122west.jpg \\
    --prior point --set heights_m=5,6.5,8 --out /tmp/geo-eval.json
"""

import argparse
import dataclasses
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from geospatial_map_calibration import (  # noqa: E402
  GeoCalibConfig, GeoMapPrior, GeospatialMapCalibration, angle_diff_deg, look_yaw_pitch)

from scene_common.transform import CameraIntrinsics, CameraPose  # noqa: E402

PASS_BAR = {"translation_m": 1.0, "rotation_deg": 8.0}
SIGNAL_BAR = {"translation_m": 5.0, "rotation_deg": 20.0}


def parse_overrides(pairs):
  """Parse --set key=value into GeoCalibConfig field overrides."""
  defaults = GeoCalibConfig()
  fields = {f.name for f in dataclasses.fields(GeoCalibConfig)}
  overrides = {}
  for pair in pairs:
    key, sep, value = pair.partition("=")
    if not sep or key not in fields:
      raise SystemExit(f"invalid --set {pair!r}; fields: {', '.join(sorted(fields))}")
    current = getattr(defaults, key)
    if isinstance(current, tuple):
      overrides[key] = tuple(float(v) for v in value.split(","))
    else:
      overrides[key] = type(current)(value)
  return dataclasses.replace(defaults, **overrides)


def load_scene_export(export_dir):
  """Scene map, scale, and manually calibrated cameras from a SceneScape DB export (data.json)."""
  data = json.loads((export_dir / "data.json").read_text())
  scene = next(x["fields"] for x in data if x["model"] == "manager.scene")
  sensors = {x["pk"]: x["fields"] for x in data if x["model"] == "manager.sensor"}
  cameras = {}
  for item in data:
    if item["model"] != "manager.cam":
      continue
    fields = item["fields"]
    if fields.get("transform_type") != "3d-2d point correspondence":
      continue
    transforms = fields["transforms"]
    if isinstance(transforms, str):
      transforms = json.loads(transforms)
    intrinsics = CameraIntrinsics(
      [fields["intrinsics_fx"], fields["intrinsics_fy"], fields["intrinsics_cx"], fields["intrinsics_cy"]],
      [fields[f"distortion_{k}"] for k in ("k1", "k2", "p1", "p2", "k3")])
    gt = CameraPose(CameraPose.arrayToDictionary(transforms, fields["transform_type"]), intrinsics)
    sensor_id = sensors.get(item["pk"], {}).get("sensor_id", f"cam-{item['pk']}")
    cameras[sensor_id] = {"K": intrinsics.intrinsics, "gt_pose": gt.pose_mat}
  return export_dir / scene["map"], float(scene["scale"]), cameras


def make_prior(mode, gt_pose, point_noise_m, heading_noise_deg):
  """Simulated operator prior derived from ground truth plus a fixed offset."""
  if mode == "none":
    return None
  prior = GeoMapPrior()
  if mode in ("point", "both"):
    prior.map_point = (gt_pose[0, 3] + point_noise_m, gt_pose[1, 3] - point_noise_m)
  if mode in ("heading", "both"):
    prior.heading_deg = (look_yaw_pitch(gt_pose)[0] + heading_noise_deg) % 360.0
  return prior


def rotation_error_deg(pose_a, pose_b):
  rel = pose_a[:3, :3].T @ pose_b[:3, :3]
  return math.degrees(math.acos(float(np.clip((np.trace(rel) - 1.0) / 2.0, -1.0, 1.0))))


def evaluate_camera(engine, sensor_id, camera, frame_path, args):
  frame = cv2.imread(str(frame_path))
  if frame is None:
    raise SystemExit(f"cannot read frame {frame_path}")
  K, gt_pose = camera["K"], camera["gt_pose"]
  width, height = int(round(K[0, 2] * 2)), int(round(K[1, 2] * 2))
  if frame.shape[1] != width or frame.shape[0] != height:
    frame = cv2.resize(frame, (width, height))
  gt_yaw, gt_pitch = look_yaw_pitch(gt_pose)
  prior = make_prior(args.prior, gt_pose, args.point_noise_m, args.heading_noise_deg)

  start = time.time()
  result = engine.calibrate(frame, K, prior)
  row = {
    "sensor_id": sensor_id,
    "seconds": round(time.time() - start, 2),
    "gt": {"translation": gt_pose[:3, 3].tolist(), "yaw_deg": gt_yaw, "pitch_deg": gt_pitch},
    "needs_prior": result["needs_prior"],
    "reason": result["reason"],
    "pitch_estimate_deg": result["pitch_estimate_deg"],
    "pitch_from_vanishing_point": result["pitch_from_vanishing_point"],
    "candidates": result["candidates"],
  }
  if result["pose"] is None:
    return row
  pose = result["pose"]
  d_t = float(np.linalg.norm(pose[:3, 3] - gt_pose[:3, 3]))
  d_r = rotation_error_deg(pose, gt_pose)
  row.update({
    "estimate": {"translation": result["translation"], "yaw_deg": result["yaw_deg"],
                 "pitch_deg": result["pitch_deg"], "height_m": result["height_m"],
                 "score": result["score"]},
    "translation_err_m": d_t,
    "xy_err_m": float(np.linalg.norm(pose[:2, 3] - gt_pose[:2, 3])),
    "z_err_m": float(abs(pose[2, 3] - gt_pose[2, 3])),
    "rotation_err_deg": d_r,
    "yaw_err_deg": angle_diff_deg(result["yaw_deg"], gt_yaw),
    "pitch_err_deg": abs(result["pitch_deg"] - gt_pitch),
    "pass": d_t <= PASS_BAR["translation_m"] and d_r <= PASS_BAR["rotation_deg"],
    "signal": d_t <= SIGNAL_BAR["translation_m"] and d_r <= SIGNAL_BAR["rotation_deg"],
  })
  return row


def main():
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--scene-export", type=Path, required=True,
                  help="Directory with data.json and the scene map image")
  ap.add_argument("--frame", action="append", default=[], metavar="SENSOR_ID=PATH", required=True,
                  help="Camera frame for a sensor (repeatable)")
  ap.add_argument("--prior", choices=("none", "point", "heading", "both"), default="none")
  ap.add_argument("--point-noise-m", type=float, default=5.0, help="Offset of simulated map point per axis")
  ap.add_argument("--heading-noise-deg", type=float, default=10.0, help="Offset of simulated heading")
  ap.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                  help="GeoCalibConfig override, e.g. heights_m=5,6.5,8 (repeatable)")
  ap.add_argument("--out", type=Path, help="Write a JSON report")
  args = ap.parse_args()

  config = parse_overrides(args.set)
  map_path, scale, cameras = load_scene_export(args.scene_export)
  engine = GeospatialMapCalibration.from_file(str(map_path), scale, config)

  rows = []
  for pair in args.frame:
    sensor_id, _, path = pair.partition("=")
    if sensor_id not in cameras:
      raise SystemExit(f"unknown sensor {sensor_id!r}; calibrated: {', '.join(sorted(cameras))}")
    row = evaluate_camera(engine, sensor_id, cameras[sensor_id], Path(path), args)
    rows.append(row)
    if "estimate" not in row:
      print(f"{sensor_id}: no pose ({row['reason']})")
      continue
    print(f"{sensor_id}: dT={row['translation_err_m']:.2f}m dXY={row['xy_err_m']:.2f}m "
          f"dZ={row['z_err_m']:.2f}m dR={row['rotation_err_deg']:.1f}deg "
          f"yaw_err={row['yaw_err_deg']:.1f} pitch_err={row['pitch_err_deg']:.1f} "
          f"score={row['estimate']['score']:.3f} needs_prior={row['needs_prior']} "
          f"{row['seconds']}s ({row['reason']})")

  summary = {
    "cameras": len(rows),
    "pass": sum(bool(r.get("pass")) for r in rows),
    "signal": sum(bool(r.get("signal")) for r in rows),
    "needs_prior": sum(bool(r["needs_prior"]) for r in rows),
    "median_xy_err_m": float(np.median([r["xy_err_m"] for r in rows if "xy_err_m" in r] or [np.nan])),
    "median_yaw_err_deg": float(np.median([r["yaw_err_deg"] for r in rows if "yaw_err_deg" in r] or [np.nan])),
  }
  print(json.dumps(summary))
  if args.out:
    report = {"prior": args.prior, "config": dataclasses.asdict(config), "summary": summary, "cameras": rows}
    args.out.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
