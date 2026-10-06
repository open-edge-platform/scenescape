#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""V2 auto-match: recover pose from camera + ortho imagery with only z > 0.

No mount XY/heading prior, no OSM. Camera structure pixels are ray-cast onto
the ground for each (yaw, pitch, height) hypothesis, rasterized to a BEV
patch, and 2D-registered onto the map structure image.

A diagnostic (not used for pass/fail) also reports XY error when the GT
heading/pitch/height are supplied, to separate correspondence finding from
the remaining 2D alignment.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

from spike_common import (
  SI_CAMERA_VIDEO,
  camera_translation,
  image_resolution_from_intrinsics,
  load_smart_intersection,
  pose_from_look,
  ray_to_ground,
  rotation_angle_deg,
  solve_pose,
)


def structure_image(bgr, ground_bias=False):
  """Soft structure map: bright markings + edges. Values in [0, 1]."""
  lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
  L = lab[:, :, 0]
  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
  tophat = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, kernel)
  marking = cv2.normalize(tophat, None, 0, 1, cv2.NORM_MINMAX, dtype=cv2.CV_32F)
  edges = cv2.Canny(cv2.GaussianBlur(L, (5, 5), 0), 50, 130).astype(np.float32) / 255.0
  struct = np.clip(0.7 * marking + 0.3 * edges, 0, 1)
  if ground_bias:
    struct[: int(0.28 * struct.shape[0]), :] *= 0.05
  return cv2.GaussianBlur(struct, (5, 5), 0)


def look_yaw_pitch(pose):
  look = pose[:3, 2]
  pitch = math.degrees(math.asin(float(np.clip(-look[2], -1.0, 1.0))))
  yaw = math.degrees(math.atan2(float(look[1]), float(look[0]))) % 360.0
  return yaw, pitch


def sample_structure_pixels(cam_struct, thresh=0.12, stride=3):
  ys, xs = np.where(cam_struct > thresh)
  if len(xs) == 0:
    return None
  idx = np.arange(0, len(xs), stride)
  xs, ys = xs[idx], ys[idx]
  wts = cam_struct[ys, xs]
  return np.stack([xs, ys], axis=1).astype(np.float32), wts


def paint_bev(uv, wts, pose, K, dist, res, max_range=90.0, pad=4.0):
  """Rasterize camera structure onto a local z=0 BEV. Camera may sit outside the crop."""
  ground = ray_to_ground(pose, K, dist, uv)
  ok = ~np.isnan(ground).any(axis=1)
  ground, wts = ground[ok], wts[ok]
  cam_xy = pose[:3, 3][:2]
  dist_xy = np.linalg.norm(ground[:, :2] - cam_xy, axis=1)
  ok = (dist_xy > 4.0) & (dist_xy < max_range)
  ground, wts = ground[ok], wts[ok]
  if len(ground) < 80:
    return None
  xmin, xmax = ground[:, 0].min() - pad, ground[:, 0].max() + pad
  ymin, ymax = ground[:, 1].min() - pad, ground[:, 1].max() + pad
  cols = int(np.ceil((xmax - xmin) / res))
  rows = int(np.ceil((ymax - ymin) / res))
  if cols < 8 or rows < 8 or cols > 800 or rows > 800:
    return None
  img = np.zeros((rows, cols), np.float32)
  u = ((ground[:, 0] - xmin) / res).astype(int)
  v = ((ymax - ground[:, 1]) / res).astype(int)
  inside = (u >= 0) & (u < cols) & (v >= 0) & (v < rows)
  np.add.at(img, (v[inside], u[inside]), wts[inside])
  img = cv2.GaussianBlur(np.clip(img, 0, None), (5, 5), 0)
  peak = float(img.max())
  if peak < 1e-6:
    return None
  img /= peak
  cam_uv = ((cam_xy[0] - xmin) / res, (ymax - cam_xy[1]) / res)
  return img, cam_uv


def match_xy(bev, cam_uv, map_grid, ymax_m, res):
  if bev.shape[0] >= map_grid.shape[0] or bev.shape[1] >= map_grid.shape[1]:
    return None
  resp = cv2.matchTemplate(map_grid, bev, cv2.TM_CCOEFF_NORMED)
  _, score, _, loc = cv2.minMaxLoc(resp)
  cx = (loc[0] + cam_uv[0]) * res
  cy = ymax_m - (loc[1] + cam_uv[1]) * res
  return float(score), float(cx), float(cy)


def search_pose(uv, wts, map_grid, K, dist, ymax_m, res, yaws, pitches, heights):
  best = None
  for yaw in yaws:
    for pitch in pitches:
      for height in heights:
        if height <= 0:
          continue
        pose0 = pose_from_look(0.0, 0.0, float(height), float(yaw), float(pitch), 0.0)
        painted = paint_bev(uv, wts, pose0, K, dist, res)
        if painted is None:
          continue
        bev, cam_uv = painted
        hit = match_xy(bev, cam_uv, map_grid, ymax_m, res)
        if hit is None:
          continue
        score, cx, cy = hit
        if best is None or score > best["score"]:
          best = {
            "score": score,
            "yaw": float(yaw),
            "pitch": float(pitch),
            "height": float(height),
            "cx": cx,
            "cy": cy,
          }
  return best


def overlay_map(map_grid, ymax_m, res, gt_t, est_t, label, path):
  vis = cv2.cvtColor((np.clip(map_grid, 0, 1) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
  def to_uv(t):
    return (
      int(round(t[0] / res)),
      int(round((ymax_m - t[1]) / res)),
    )
  cv2.drawMarker(vis, to_uv(gt_t), (0, 255, 0), cv2.MARKER_TILTED_CROSS, 18, 2)
  cv2.drawMarker(vis, to_uv(est_t), (0, 0, 255), cv2.MARKER_TILTED_CROSS, 18, 2)
  cv2.putText(vis, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
  cv2.imwrite(str(path), vis)


def evaluate_camera(cam, frame, map_grid, ymax_m, res, out_dir):
  K = cam["intrinsics"]
  dist = cam["distortion"]
  gt_pose, _, _ = solve_pose(cam["map_points"], cam["camera_points"], K, dist)
  gt_t = camera_translation(gt_pose)
  gt_yaw, gt_pitch = look_yaw_pitch(gt_pose)

  width, height = image_resolution_from_intrinsics(K)
  if frame.shape[1] != width or frame.shape[0] != height:
    frame = cv2.resize(frame, (width, height))
  cam_struct = structure_image(frame, ground_bias=True)
  sampled = sample_structure_pixels(cam_struct)
  if sampled is None:
    return {"sensor_id": cam["sensor_id"], "error": "no camera structure", "v2_pass": False}
  uv, wts = sampled

  yaws = np.arange(0.0, 360.0, 10.0)
  pitches = np.arange(6.0, 15.1, 2.0)
  heights = np.array([5.0, 6.0, 7.0, 8.0])
  pick = search_pose(uv, wts, map_grid, K, dist, ymax_m, res, yaws, pitches, heights)
  if pick is not None:
    pick2 = search_pose(
      uv, wts, map_grid, K, dist, ymax_m, res,
      np.arange(pick["yaw"] - 8.0, pick["yaw"] + 8.1, 2.0) % 360.0,
      np.arange(max(4.0, pick["pitch"] - 3.0), min(18.0, pick["pitch"] + 3.1), 1.0),
      np.arange(max(3.5, pick["height"] - 1.0), min(12.0, pick["height"] + 1.1), 0.5),
    )
    if pick2 is not None and pick2["score"] >= pick["score"]:
      pick = pick2

  result = {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "gt_translation_m": gt_t.tolist(),
    "gt_yaw_deg": gt_yaw,
    "gt_pitch_deg": gt_pitch,
    "v2_pass": False,
    "v2_signal": False,
  }
  if pick is None:
    result["error"] = "no alignment"
    return result

  est_pose = pose_from_look(
    pick["cx"], pick["cy"], pick["height"], pick["yaw"], pick["pitch"], 0.0)
  est_t = camera_translation(est_pose)
  d_t = float(np.linalg.norm(est_t - gt_t))
  d_r = float(rotation_angle_deg(est_pose, gt_pose))
  result.update({
    "score": pick["score"],
    "est_translation_m": est_t.tolist(),
    "est_yaw_deg": pick["yaw"],
    "est_pitch_deg": pick["pitch"],
    "est_height_m": pick["height"],
    "translation_err_m": d_t,
    "xy_err_m": float(np.linalg.norm(est_t[:2] - gt_t[:2])),
    "z_err_m": float(abs(est_t[2] - gt_t[2])),
    "rotation_err_deg": d_r,
    "above_ground": bool(est_t[2] > 0),
    "v2_pass": bool(est_t[2] > 0 and d_t <= 1.0 and d_r <= 8.0),
    "v2_signal": bool(est_t[2] > 0 and d_t <= 5.0 and d_r <= 20.0),
  })

  # Diagnostic: GT orientation + height, XY from the same matcher (not a prior in V2).
  pose_gt_orient = pose_from_look(0.0, 0.0, float(gt_t[2]), gt_yaw, gt_pitch, 0.0)
  painted = paint_bev(uv, wts, pose_gt_orient, K, dist, res)
  if painted is not None:
    hit = match_xy(painted[0], painted[1], map_grid, ymax_m, res)
    if hit is not None:
      _, cx, cy = hit
      result["oracle_orient_xy_err_m"] = float(math.hypot(cx - gt_t[0], cy - gt_t[1]))

  overlay_map(
    map_grid, ymax_m, res, gt_t, est_t,
    f"{cam['sensor_id']} dT={d_t:.1f}m dR={d_r:.1f}deg ncc={pick['score']:.2f}",
    out_dir / f"{cam['sensor_id']}_v2_map.png")
  return result


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument("--res", type=float, default=0.4)
  args = ap.parse_args()

  scene, cams = load_smart_intersection(args.fixture_dir)
  args.out_dir.mkdir(parents=True, exist_ok=True)
  map_bgr = cv2.imread(str(args.fixture_dir / scene["map"]))
  if map_bgr is None:
    raise SystemExit(f"failed to read map {args.fixture_dir / scene['map']}")
  scale = float(scene["scale"])
  map_struct = structure_image(map_bgr)
  h_px, w_px = map_struct.shape
  cols = int(np.ceil((w_px / scale) / args.res))
  rows = int(np.ceil((h_px / scale) / args.res))
  map_grid = cv2.resize(map_struct, (cols, rows), interpolation=cv2.INTER_AREA)
  ymax_m = h_px / scale

  frames_dir = args.frames_dir
  if frames_dir is None:
    frames_dir = Path(__file__).resolve().parent / "fixtures" / "videos"

  results = []
  for cam in cams:
    stem = SI_CAMERA_VIDEO.get(cam["sensor_id"])
    frame_path = frames_dir / f"{stem}.jpg" if stem else None
    if not frame_path or not frame_path.is_file():
      results.append({
        "sensor_id": cam["sensor_id"], "error": "missing frame",
        "v2_pass": False, "v2_signal": False})
      print(f"{cam['sensor_id']:8s}  MISSING_FRAME")
      continue
    frame = cv2.imread(str(frame_path))
    r = evaluate_camera(cam, frame, map_grid, ymax_m, args.res, args.out_dir)
    results.append(r)
    print(
      f"{r['sensor_id']:8s}  ncc={r.get('score', 0):.3f}  "
      f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
      f"dR={r.get('rotation_err_deg', float('nan')):6.1f}deg  "
      f"oracleXY={r.get('oracle_orient_xy_err_m', float('nan')):5.1f}m  "
      f"pass={r.get('v2_pass')}  signal={r.get('v2_signal')}"
    )

  n_pass = sum(1 for c in results if c.get("v2_pass"))
  n_signal = sum(1 for c in results if c.get("v2_signal"))
  summary = {
    "scene": scene["name"],
    "source": "ortho imagery auto-match (no OSM, z>0 only)",
    "res_m_per_px": args.res,
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "cameras": results,
    "v2_pass_count": n_pass,
    "v2_signal_count": n_signal,
    "v2_pass": n_pass >= 2,
    "v2_signal": n_signal >= 2,
  }
  out_json = args.out_dir / "v2_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(
    f"\nv2_pass={summary['v2_pass']} ({n_pass}/{len(results)})  "
    f"v2_signal={summary['v2_signal']} ({n_signal}/{len(results)})  "
    f"wrote {out_json}"
  )
  return 0 if summary["v2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
