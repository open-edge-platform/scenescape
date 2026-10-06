#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""P2 priority-2 spike: semantic marking landmarks (camera ↔ ortho).

Detects road-marking corners (Lab tophat + Shi-Tomasi) in the ortho map and
each camera frame, describes them with ORB, matches, and solves PnP RANSAC.
No OSM. Only hard prior after solve: z > 0.

This mirrors how humans pick crosswalk / curb corners, without requiring a
learned cross-view matcher.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from spike_common import (
  SI_CAMERA_VIDEO,
  camera_translation,
  image_resolution_from_intrinsics,
  load_smart_intersection,
  map_pixels_to_metres,
  project_world_to_image,
  rotation_angle_deg,
  solve_pose,
)


def marking_corners(bgr, max_corners=100, quality=0.02, min_distance=12, ground_bias=False):
  lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[:, :, 0]
  if ground_bias:
    lab = lab.copy()
    lab[: int(0.28 * lab.shape[0]), :] = 0
  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
  tophat = cv2.morphologyEx(lab, cv2.MORPH_TOPHAT, kernel)
  thr = cv2.threshold(tophat, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
  corners = cv2.goodFeaturesToTrack(
    tophat, maxCorners=max_corners, qualityLevel=quality,
    minDistance=min_distance, mask=thr)
  if corners is None:
    return np.zeros((0, 2), np.float64)
  return corners.reshape(-1, 2).astype(np.float64)


def orb_describe(img, pts, size=16):
  if len(pts) == 0:
    return [], None
  orb = cv2.ORB_create(nfeatures=max(200, len(pts) * 2), scaleFactor=1.2, nlevels=4)
  kps = [cv2.KeyPoint(float(x), float(y), size) for x, y in pts]
  kps, desc = orb.compute(img, kps)
  return kps, desc


def match_and_solve(map_bgr, frame, map_pts, cam_pts, scale, map_h, K, dist):
  mk, md = orb_describe(map_bgr, map_pts)
  ck, cd = orb_describe(frame, cam_pts)
  if md is None or cd is None or len(mk) < 6 or len(ck) < 6:
    return None, 0
  bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
  knn = bf.knnMatch(cd, md, k=2)
  good = []
  for pair in knn:
    if len(pair) < 2:
      continue
    a, b = pair
    if a.distance < 0.8 * b.distance:
      good.append(a)
  good = sorted(good, key=lambda m: m.distance)[:80]
  if len(good) < 8:
    return None, len(good)
  cam_xy = np.array([ck[m.queryIdx].pt for m in good], np.float32)
  map_xy = np.array([mk[m.trainIdx].pt for m in good], np.float32)
  world = map_pixels_to_metres(map_xy, scale, map_h)
  world = np.hstack([world, np.zeros((len(world), 1), np.float32)])
  ok, rvec, tvec, inliers = cv2.solvePnPRansac(
    world, cam_xy, K, dist, flags=cv2.SOLVEPNP_EPNP,
    reprojectionError=10.0, iterationsCount=2000, confidence=0.99)
  if not ok or inliers is None or len(inliers) < 6:
    return None, len(good)
  inl = inliers.ravel()
  ok2, rvec, tvec = cv2.solvePnP(
    world[inl], cam_xy[inl], K, dist, rvec, tvec,
    useExtrinsicGuess=True, flags=cv2.SOLVEPNP_ITERATIVE)
  if not ok2:
    return None, len(good)
  rmat, _ = cv2.Rodrigues(rvec)
  cam_from_world = np.vstack([np.hstack([rmat, tvec]), [0, 0, 0, 1]])
  return {
    "pose": np.linalg.inv(cam_from_world),
    "n_matches": int(len(good)),
    "n_inliers": int(len(inl)),
  }, len(good)


def evaluate_camera(cam, frame, map_bgr, map_corners, scale, map_h, out_dir):
  K, dist = cam["intrinsics"], cam["distortion"]
  gt_pose, rvec, tvec = solve_pose(cam["map_points"], cam["camera_points"], K, dist)
  gt_t = camera_translation(gt_pose)
  width, height = image_resolution_from_intrinsics(K)
  if frame.shape[1] != width or frame.shape[0] != height:
    frame = cv2.resize(frame, (width, height))
  cam_corners = marking_corners(frame, max_corners=100, ground_bias=True)

  # Observability: how many map corners fall near a camera corner under GT pose?
  world = map_pixels_to_metres(map_corners, scale, map_h)
  world3 = np.hstack([world, np.zeros((len(world), 1))])
  proj = project_world_to_image(world3, rvec, tvec, K, dist)
  inside = (proj[:, 0] >= 0) & (proj[:, 0] < width) & (proj[:, 1] >= 0) & (proj[:, 1] < height)
  nn_med = None
  n_close = 0
  if inside.any() and len(cam_corners):
    d = np.linalg.norm(proj[inside][:, None, :] - cam_corners[None, :, :], axis=2)
    nn = d.min(axis=1)
    nn_med = float(np.median(nn))
    n_close = int((nn < 15).sum())

  solved, n_good = match_and_solve(
    map_bgr, frame, map_corners, cam_corners, scale, map_h, K, dist)

  result = {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "gt_translation_m": gt_t.tolist(),
    "n_map_corners": int(len(map_corners)),
    "n_cam_corners": int(len(cam_corners)),
    "n_orb_good": n_good,
    "gt_nn_med_px": nn_med,
    "gt_nn_lt15px": n_close,
    "p2_pass": False,
    "p2_signal": False,
  }
  if solved is None:
    result["error"] = "no solve"
    return result

  est = solved["pose"]
  est_t = camera_translation(est)
  d_t = float(np.linalg.norm(est_t - gt_t))
  d_r = float(rotation_angle_deg(est, gt_pose))
  result.update({
    "est_translation_m": est_t.tolist(),
    "n_matches": solved["n_matches"],
    "n_inliers": solved["n_inliers"],
    "translation_err_m": d_t,
    "xy_err_m": float(np.linalg.norm(est_t[:2] - gt_t[:2])),
    "z_err_m": float(abs(est_t[2] - gt_t[2])),
    "rotation_err_deg": d_r,
    "above_ground": bool(est_t[2] > 0),
    "p2_pass": bool(est_t[2] > 0 and d_t <= 1.0 and d_r <= 8.0),
    "p2_signal": bool(est_t[2] > 0 and d_t <= 5.0 and d_r <= 20.0),
  })

  vis = frame.copy()
  for x, y in cam_corners.astype(int):
    cv2.circle(vis, (x, y), 3, (0, 255, 255), -1)
  cv2.imwrite(str(out_dir / f"{cam['sensor_id']}_p2_semantic_cam.png"), vis)
  return result


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  args = ap.parse_args()

  scene, cams = load_smart_intersection(args.fixture_dir)
  args.out_dir.mkdir(parents=True, exist_ok=True)
  map_bgr = cv2.imread(str(args.fixture_dir / scene["map"]))
  if map_bgr is None:
    raise SystemExit(f"failed to read map {args.fixture_dir / scene['map']}")
  scale = float(scene["scale"])
  map_h = map_bgr.shape[0]
  map_corners = marking_corners(map_bgr, max_corners=150)

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
        "p2_pass": False, "p2_signal": False})
      print(f"{cam['sensor_id']:8s}  MISSING_FRAME")
      continue
    frame = cv2.imread(str(frame_path))
    r = evaluate_camera(cam, frame, map_bgr, map_corners, scale, map_h, args.out_dir)
    results.append(r)
    print(
      f"{r['sensor_id']:8s}  cam_c={r.get('n_cam_corners')}  "
      f"orb={r.get('n_orb_good')}  inl={r.get('n_inliers')}  "
      f"gt_nn_med={r.get('gt_nn_med_px')}  "
      f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
      f"dR={r.get('rotation_err_deg', float('nan')):6.1f}deg  "
      f"pass={r.get('p2_pass')} signal={r.get('p2_signal')}"
    )

  n_pass = sum(1 for c in results if c.get("p2_pass"))
  n_signal = sum(1 for c in results if c.get("p2_signal"))
  summary = {
    "scene": scene["name"],
    "source": "semantic marking corners + ORB (P2 priority 2)",
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "cameras": results,
    "p2_pass_count": n_pass,
    "p2_signal_count": n_signal,
    "p2_pass": n_pass >= 2,
    "p2_signal": n_signal >= 2,
  }
  out_json = args.out_dir / "p2_semantic_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(
    f"\np2_pass={summary['p2_pass']} ({n_pass}/{len(results)})  "
    f"p2_signal={summary['p2_signal']} ({n_signal}/{len(results)})  "
    f"wrote {out_json}"
  )
  return 0 if summary["p2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
