#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""V0 oracle: map↔camera geometry solvability on Smart Intersection fixtures.

Uses the sample's hand-labeled 3d-2d correspondences as an oracle (perfect
landmark IDs). No mount prior. Solves pose from a subset and scores held-out
ground error in metres. External fixture only — does not vendor SI assets.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np


POINT_CORRESPONDENCE = "3d-2d point correspondence"


def parse_transforms(array, transform_type):
  """Mirror scene_common.transform.CameraPose.arrayToDictionary for 3d-2d."""
  if transform_type != POINT_CORRESPONDENCE:
    raise ValueError(f"unsupported transform_type: {transform_type}")
  if isinstance(array, str):
    array = json.loads(array)
  array = list(array)
  if len(array) % 5 == 0:
    split = (len(array) // 5) * 2
    cam = np.asarray(array[:split], dtype=np.float64).reshape(-1, 2)
    maps = np.asarray(array[split:], dtype=np.float64).reshape(-1, 3)
  elif len(array) % 4 == 0:
    split = len(array) // 2
    cam = np.asarray(array[:split], dtype=np.float64).reshape(-1, 2)
    maps = np.asarray(array[split:], dtype=np.float64).reshape(-1, 2)
    maps = np.hstack([maps, np.zeros((maps.shape[0], 1))])
  else:
    raise ValueError(f"invalid transforms length {len(array)}")
  return cam, maps


def load_smart_intersection(fixture_dir: Path):
  data = json.loads((fixture_dir / "data.json").read_text())
  scene = next(x for x in data if x["model"] == "manager.scene")
  sensors = {x["pk"]: x["fields"] for x in data if x["model"] == "manager.sensor"}
  cams = []
  for x in data:
    if x["model"] != "manager.cam":
      continue
    fields = x["fields"]
    transforms = fields["transforms"]
    if isinstance(transforms, str):
      transforms = json.loads(transforms)
    cam_pts, map_pts = parse_transforms(transforms, fields["transform_type"])
    sensor = sensors.get(x["pk"], {})
    cams.append({
      "pk": x["pk"],
      "sensor_id": sensor.get("sensor_id", f"cam-{x['pk']}"),
      "name": sensor.get("name", ""),
      "camera_points": cam_pts,
      "map_points": map_pts,
      "intrinsics": np.array([
        [fields["intrinsics_fx"], 0.0, fields["intrinsics_cx"]],
        [0.0, fields["intrinsics_fy"], fields["intrinsics_cy"]],
        [0.0, 0.0, 1.0],
      ], dtype=np.float64),
      "distortion": np.array([
        fields["distortion_k1"], fields["distortion_k2"],
        fields["distortion_p1"], fields["distortion_p2"],
        fields["distortion_k3"],
      ], dtype=np.float64),
    })
  return scene["fields"], cams


def solve_pose(map_pts, cam_pts, K, dist):
  """World-from-camera pose matrix via solvePnP (same as PointCorrespondenceTransform)."""
  ok, rvec, tvec = cv2.solvePnP(
    map_pts.astype(np.float32),
    cam_pts.astype(np.float32),
    K,
    dist,
    flags=cv2.SOLVEPNP_ITERATIVE,
  )
  if not ok:
    raise RuntimeError("solvePnP failed")
  rmat, _ = cv2.Rodrigues(rvec)
  cam_from_world = np.vstack([np.hstack([rmat, tvec]), [0, 0, 0, 1]])
  world_from_cam = np.linalg.inv(cam_from_world)
  return world_from_cam, rvec, tvec


def camera_translation(pose_mat):
  return pose_mat[:3, 3].copy()


def project_world_to_image(map_pts, rvec, tvec, K, dist):
  img, _ = cv2.projectPoints(
    map_pts.astype(np.float32), rvec, tvec, K, dist)
  return img.reshape(-1, 2)


def ray_to_ground(pose_mat, K, dist, cam_pts):
  """Intersect camera rays with z=0. Returns Nx3 world points (nan if parallel)."""
  # Undistort to normalized camera rays, then transform by pose.
  und = cv2.undistortPoints(cam_pts.astype(np.float32).reshape(-1, 1, 2), K, dist)
  und = und.reshape(-1, 2)
  cam_origin = pose_mat @ np.array([0.0, 0.0, 0.0, 1.0])
  out = []
  for u, v in und:
    cam_dir = pose_mat @ np.array([u, v, 1.0, 0.0])
    # origin + t * dir, set z=0
    oz, dz = cam_origin[2], cam_dir[2]
    if abs(dz) < 1e-9:
      out.append([np.nan, np.nan, np.nan])
      continue
    t = -oz / dz
    if t <= 0:
      out.append([np.nan, np.nan, np.nan])
      continue
    pt = cam_origin[:3] + t * cam_dir[:3]
    out.append(pt.tolist())
  return np.asarray(out, dtype=np.float64)


def rotation_angle_deg(Ra, Rb):
  R = Ra[:3, :3].T @ Rb[:3, :3]
  cos_theta = np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0)
  return math.degrees(math.acos(cos_theta))


def evaluate_camera(cam):
  """Leave-one-out held-out ground error (primary V0 metric)."""
  cam_pts = cam["camera_points"]
  map_pts = cam["map_points"]
  K = cam["intrinsics"]
  dist = cam["distortion"]
  n = len(cam_pts)
  if n < 5:
    raise ValueError(f"{cam['sensor_id']}: need >= 5 points, got {n}")

  gt_pose, gt_rvec, gt_tvec = solve_pose(map_pts, cam_pts, K, dist)
  gt_t = camera_translation(gt_pose)

  reproj = project_world_to_image(map_pts, gt_rvec, gt_tvec, K, dist)
  reproj_err = np.linalg.norm(reproj - cam_pts, axis=1)

  splits = []
  for i in range(n):
    fit = np.array([j for j in range(n) if j != i])
    pose, rvec, tvec = solve_pose(map_pts[fit], cam_pts[fit], K, dist)
    t = camera_translation(pose)
    pred_map = ray_to_ground(pose, K, dist, cam_pts[i:i + 1])[0]
    if np.isnan(pred_map).any():
      ground_err = float("nan")
    else:
      ground_err = float(np.linalg.norm(pred_map[:2] - map_pts[i, :2]))
    img = project_world_to_image(map_pts[i:i + 1], rvec, tvec, K, dist)[0]
    splits.append({
      "held": [i],
      "translation_err_m": float(np.linalg.norm(t - gt_t)),
      "rotation_err_deg": float(rotation_angle_deg(pose, gt_pose)),
      "heldout_ground_err_m": ground_err,
      "heldout_reproj_px": float(np.linalg.norm(img - cam_pts[i])),
      "z_cam": float(t[2]),
      "above_ground": bool(t[2] > 0),
    })

  ground_errs = np.array([s["heldout_ground_err_m"] for s in splits], dtype=np.float64)
  return {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "n_points": n,
    "gt_translation_m": gt_t.tolist(),
    "gt_z_m": float(gt_t[2]),
    "above_ground": bool(gt_t[2] > 0),
    "reproj_mean_px": float(np.mean(reproj_err)),
    "reproj_max_px": float(np.max(reproj_err)),
    "loo_ground_mean_m": float(np.nanmean(ground_errs)),
    "loo_ground_median_m": float(np.nanmedian(ground_errs)),
    "loo_ground_max_m": float(np.nanmax(ground_errs)),
    "pose_trans_err_mean_m": float(np.mean([s["translation_err_m"] for s in splits])),
    "pose_rot_err_mean_deg": float(np.mean([s["rotation_err_deg"] for s in splits])),
    "splits": splits,
  }


def map_metres_to_pixels(map_pts_xy, scale, map_h):
  # SceneScape: x = px / S, y = (H - py) / S  =>  px = x*S, py = H - y*S
  px = map_pts_xy[:, 0] * scale
  py = map_h - map_pts_xy[:, 1] * scale
  return np.stack([px, py], axis=1)


def save_map_overlay(map_path, scale, cam, out_path):
  img = cv2.imread(str(map_path))
  if img is None:
    return
  h = img.shape[0]
  pix = map_metres_to_pixels(cam["map_points"][:, :2], scale, h)
  for (x, y), (u, v) in zip(pix, cam["camera_points"]):
    cv2.circle(img, (int(round(x)), int(round(y))), 6, (0, 255, 0), 2)
  t = camera_translation(solve_pose(
    cam["map_points"], cam["camera_points"], cam["intrinsics"], cam["distortion"])[0])
  cam_pix = map_metres_to_pixels(t[:2][None, :], scale, h)[0]
  cv2.drawMarker(img, (int(cam_pix[0]), int(cam_pix[1])), (0, 0, 255),
                 markerType=cv2.MARKER_TILTED_CROSS, markerSize=20, thickness=2)
  cv2.putText(img, cam["sensor_id"], (int(cam_pix[0]) + 8, int(cam_pix[1]) - 8),
              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
  cv2.imwrite(str(out_path), img)


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--fixture-dir",
    type=Path,
    required=True,
    help="Extracted smart-intersection-ri.tar.bz2 directory (data.json + map)",
  )
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument(
    "--pass-bar-m",
    type=float,
    default=1.0,
    help="Max LOO mean ground error (m) for v0_pass per camera",
  )
  args = ap.parse_args()

  scene, cams = load_smart_intersection(args.fixture_dir)
  args.out_dir.mkdir(parents=True, exist_ok=True)
  map_path = args.fixture_dir / scene["map"]
  scale = float(scene["scale"])

  results = []
  for cam in cams:
    r = evaluate_camera(cam)
    results.append(r)
    save_map_overlay(map_path, scale, cam, args.out_dir / f"{r['sensor_id']}_map.png")
    print(
      f"{r['sensor_id']:8s}  n={r['n_points']}  "
      f"z={r['gt_z_m']:6.2f}m  above={r['above_ground']}  "
      f"reproj={r['reproj_mean_px']:5.2f}px  "
      f"loo_mean={r['loo_ground_mean_m']:6.3f}m  "
      f"loo_med={r['loo_ground_median_m']:6.3f}m  "
      f"loo_max={r['loo_ground_max_m']:6.3f}m  "
      f"dT={r['pose_trans_err_mean_m']:5.3f}m  "
      f"dR={r['pose_rot_err_mean_deg']:5.2f}deg"
    )

  summary = {
    "scene": scene["name"],
    "scale_px_per_m": scale,
    "map_corners_lla": scene.get("map_corners_lla"),
    "metric": "leave-one-out ground error (m)",
    "pass_bar_m": args.pass_bar_m,
    "cameras": results,
  }
  # Pass: above ground, LOO mean <= bar, pose stable under LOO (mean dT < 2 m).
  summary["v0_pass"] = all(
    c["above_ground"]
    and c["loo_ground_mean_m"] <= summary["pass_bar_m"]
    and c["pose_trans_err_mean_m"] < 2.0
    for c in results
  )
  summary["v0_pass_median"] = all(
    c["above_ground"] and c["loo_ground_median_m"] <= summary["pass_bar_m"]
    for c in results
  )
  out_json = args.out_dir / "v0_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(f"\nv0_pass={summary['v0_pass']}  wrote {out_json}")
  return 0 if summary["v0_pass"] else 1


if __name__ == "__main__":
  sys.exit(main())
