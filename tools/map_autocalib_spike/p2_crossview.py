#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""P2 priority-1 spike: LoFTR cross-view matcher (camera ↔ ortho map).

Uses pretrained outdoor LoFTR to propose 3D–2D correspondences (map ground
points ↔ camera pixels), then solvePnPRansac. Only hard prior is z > 0 after
solve. Structure-enhanced grayscale optional (--enhance).

Requires: torch, kornia, opencv, numpy. Weights:
  fixtures/weights/loftr_outdoor.ckpt
  (download: http://cmp.felk.cvut.cz/~mishkdmy/models/loftr_outdoor.ckpt)

Example:
  map-any-venv/bin/python p2_crossview.py \\
    --fixture-dir /tmp/smart-intersection-v0 \\
    --frames-dir fixtures/videos --out-dir out
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from kornia.feature import LoFTR

from spike_common import (
  SI_CAMERA_VIDEO,
  camera_translation,
  image_resolution_from_intrinsics,
  load_smart_intersection,
  map_pixels_to_metres,
  rotation_angle_deg,
  solve_pose,
)


def structure_enhance(bgr):
  lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
  L = lab[:, :, 0]
  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
  tophat = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, kernel)
  edges = cv2.Canny(cv2.GaussianBlur(L, (5, 5), 0), 50, 130)
  mix = cv2.addWeighted(L, 0.45, tophat, 0.40, 0)
  mix = cv2.addWeighted(mix, 1.0, edges, 0.25, 0)
  return cv2.cvtColor(mix, cv2.COLOR_GRAY2BGR)


def to_gray_tensor(bgr, max_side):
  gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
  h, w = gray.shape
  scale = min(1.0, float(max_side) / max(h, w))
  nw = max(8, int(round(w * scale / 8.0)) * 8)
  nh = max(8, int(round(h * scale / 8.0)) * 8)
  if (nw, nh) != (w, h):
    gray = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)
  sx, sy = nw / float(w), nh / float(h)
  t = torch.from_numpy(gray.astype(np.float32) / 255.0)[None, None]
  return t, sx, sy


def load_matcher(weights: Path, device: str):
  matcher = LoFTR(pretrained=None)
  blob = torch.load(str(weights), map_location="cpu", weights_only=False)
  state = blob["state_dict"] if isinstance(blob, dict) and "state_dict" in blob else blob
  matcher.load_state_dict(state)
  return matcher.eval().to(device)


@torch.inference_mode()
def loftr_match(matcher, img0_bgr, img1_bgr, max_side, conf_min, device):
  t0, sx0, sy0 = to_gray_tensor(img0_bgr, max_side)
  t1, sx1, sy1 = to_gray_tensor(img1_bgr, max_side)
  out = matcher({"image0": t0.to(device), "image1": t1.to(device)})
  mk0 = out["keypoints0"].detach().cpu().numpy()
  mk1 = out["keypoints1"].detach().cpu().numpy()
  conf = out["confidence"].detach().cpu().numpy()
  keep = conf >= conf_min
  mk0, mk1, conf = mk0[keep], mk1[keep], conf[keep]
  mk0[:, 0] /= sx0
  mk0[:, 1] /= sy0
  mk1[:, 0] /= sx1
  mk1[:, 1] /= sy1
  return mk0, mk1, conf


def solve_from_matches(map_xy_px, cam_xy, scale, map_h, K, dist, reproj=12.0):
  if len(map_xy_px) < 6:
    return None
  world_xy = map_pixels_to_metres(map_xy_px, scale, map_h)
  world = np.hstack([world_xy, np.zeros((len(world_xy), 1), np.float64)])
  ok, rvec, tvec, inliers = cv2.solvePnPRansac(
    world.astype(np.float32),
    cam_xy.astype(np.float32),
    K,
    dist,
    flags=cv2.SOLVEPNP_EPNP,
    reprojectionError=reproj,
    iterationsCount=800,
    confidence=0.99,
  )
  if not ok or inliers is None or len(inliers) < 6:
    return None
  inl = inliers.ravel()
  ok2, rvec, tvec = cv2.solvePnP(
    world[inl].astype(np.float32),
    cam_xy[inl].astype(np.float32),
    K,
    dist,
    rvec,
    tvec,
    useExtrinsicGuess=True,
    flags=cv2.SOLVEPNP_ITERATIVE,
  )
  if not ok2:
    return None
  rmat, _ = cv2.Rodrigues(rvec)
  cam_from_world = np.vstack([np.hstack([rmat, tvec]), [0, 0, 0, 1]])
  return {
    "pose": np.linalg.inv(cam_from_world),
    "n_matches": int(len(map_xy_px)),
    "n_inliers": int(len(inl)),
  }


def overlay_matches(frame, map_bgr, mk_cam, mk_map, path, max_draw=80):
  # Downscale map for a readable side-by-side.
  mh = frame.shape[0]
  scale = mh / map_bgr.shape[0]
  map_s = cv2.resize(map_bgr, (int(map_bgr.shape[1] * scale), mh))
  canvas = np.concatenate([frame, map_s], axis=1)
  n = min(len(mk_cam), max_draw)
  for i in range(n):
    p0 = (int(mk_cam[i, 0]), int(mk_cam[i, 1]))
    p1 = (int(mk_map[i, 0] * scale) + frame.shape[1], int(mk_map[i, 1] * scale))
    cv2.circle(canvas, p0, 3, (0, 255, 0), -1)
    cv2.circle(canvas, p1, 3, (0, 255, 0), -1)
    cv2.line(canvas, p0, p1, (0, 255, 0), 1)
  if canvas.shape[1] > 1600:
    s = 1600 / canvas.shape[1]
    canvas = cv2.resize(canvas, None, fx=s, fy=s)
  cv2.imwrite(str(path), canvas)


def evaluate_camera(matcher, cam, frame, map_bgr, scale, map_h, args, device, out_dir):
  K, dist = cam["intrinsics"], cam["distortion"]
  gt_pose, _, _ = solve_pose(cam["map_points"], cam["camera_points"], K, dist)
  gt_t = camera_translation(gt_pose)
  width, height = image_resolution_from_intrinsics(K)
  if frame.shape[1] != width or frame.shape[0] != height:
    frame = cv2.resize(frame, (width, height))

  cam_img = structure_enhance(frame) if args.enhance else frame
  map_img = structure_enhance(map_bgr) if args.enhance else map_bgr
  mk_cam, mk_map, conf = loftr_match(
    matcher, cam_img, map_img, args.max_side, args.conf_min, device)
  solved = solve_from_matches(mk_map, mk_cam, scale, map_h, K, dist, reproj=args.reproj)

  result = {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "gt_translation_m": gt_t.tolist(),
    "n_raw": int(len(conf)),
    "mean_conf": float(conf.mean()) if len(conf) else 0.0,
    "p2_pass": False,
    "p2_signal": False,
  }
  if len(conf):
    overlay_matches(
      frame, map_bgr, mk_cam, mk_map,
      out_dir / f"{cam['sensor_id']}_p2_loftr_matches.png")
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
  return result


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument(
    "--weights", type=Path,
    default=Path(__file__).resolve().parent / "fixtures/weights/loftr_outdoor.ckpt")
  ap.add_argument("--max-side", type=int, default=640)
  ap.add_argument("--conf-min", type=float, default=0.2)
  ap.add_argument("--reproj", type=float, default=12.0)
  ap.add_argument("--enhance", action="store_true", default=True)
  ap.add_argument("--no-enhance", action="store_false", dest="enhance")
  ap.add_argument("--device", default="cpu")
  ap.add_argument("--cameras", nargs="*", default=None)
  args = ap.parse_args()

  if not args.weights.is_file():
    raise SystemExit(f"missing LoFTR weights: {args.weights}")

  scene, cams = load_smart_intersection(args.fixture_dir)
  if args.cameras:
    cams = [c for c in cams if c["sensor_id"] in set(args.cameras)]
  args.out_dir.mkdir(parents=True, exist_ok=True)
  map_bgr = cv2.imread(str(args.fixture_dir / scene["map"]))
  if map_bgr is None:
    raise SystemExit(f"failed to read map {args.fixture_dir / scene['map']}")
  scale = float(scene["scale"])
  map_h = map_bgr.shape[0]
  frames_dir = args.frames_dir or (Path(__file__).resolve().parent / "fixtures" / "videos")

  print(f"loading LoFTR from {args.weights} on {args.device} ...")
  matcher = load_matcher(args.weights, args.device)

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
    r = evaluate_camera(
      matcher, cam, frame, map_bgr, scale, map_h, args, args.device, args.out_dir)
    results.append(r)
    print(
      f"{r['sensor_id']:8s}  raw={r.get('n_raw', 0):4d}  "
      f"inl={r.get('n_inliers')}  "
      f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
      f"dR={r.get('rotation_err_deg', float('nan')):6.1f}deg  "
      f"pass={r.get('p2_pass')} signal={r.get('p2_signal')}"
    )

  n_pass = sum(1 for c in results if c.get("p2_pass"))
  n_signal = sum(1 for c in results if c.get("p2_signal"))
  summary = {
    "scene": scene["name"],
    "source": "LoFTR outdoor cross-view (P2 priority 1)",
    "weights": str(args.weights),
    "max_side": args.max_side,
    "conf_min": args.conf_min,
    "enhance": args.enhance,
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "cameras": results,
    "p2_pass_count": n_pass,
    "p2_signal_count": n_signal,
    "p2_pass": n_pass >= 2,
    "p2_signal": n_signal >= 2,
  }
  out_json = args.out_dir / "p2_crossview_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(
    f"\np2_pass={summary['p2_pass']} ({n_pass}/{len(results)})  "
    f"p2_signal={summary['p2_signal']} ({n_signal}/{len(results)})  "
    f"wrote {out_json}"
  )
  return 0 if summary["p2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
