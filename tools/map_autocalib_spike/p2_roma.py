#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""P2 priority-1 spike: RoMa-class dense matcher (camera ↔ ortho map).

Uses Parskatt RoMa (romatch) outdoor / tiny-outdoor to propose dense
correspondences, samples high-certainty matches, then solvePnPRansac.
Only hard prior is z > 0 after solve.

Requires a Python env with torch + romatch (see .venv-roma). Weights under
fixtures/weights/ (gitignored):
  tiny_roma_v1_outdoor.pth
  roma_outdoor.pth
  dinov2_vitl14_pretrain.pth  (full outdoor only)

Example:
  .venv-roma/bin/python p2_roma.py \\
    --fixture-dir /tmp/smart-intersection-v0 \\
    --frames-dir fixtures/videos --out-dir out --model tiny
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import torch

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


def load_roma(model_name: str, weights_dir: Path, device: str):
  from romatch import roma_outdoor, tiny_roma_v1_outdoor

  if model_name == "tiny":
    path = weights_dir / "tiny_roma_v1_outdoor.pth"
    if not path.is_file():
      raise SystemExit(f"missing weights: {path}")
    weights = torch.load(str(path), map_location="cpu", weights_only=True)
    return tiny_roma_v1_outdoor(device=device, weights=weights)

  if model_name == "outdoor":
    path = weights_dir / "roma_outdoor.pth"
    dino = weights_dir / "dinov2_vitl14_pretrain.pth"
    if not path.is_file():
      raise SystemExit(f"missing weights: {path}")
    if not dino.is_file():
      raise SystemExit(f"missing DINOv2 weights: {dino}")
    weights = torch.load(str(path), map_location="cpu", weights_only=True)
    dino_w = torch.load(str(dino), map_location="cpu", weights_only=True)
    # use_custom_corr needs optional fused-local-corr; fall back to native torch.
    return roma_outdoor(
      device=device, weights=weights, dinov2_weights=dino_w,
      use_custom_corr=False, amp_dtype=torch.float32)

  raise SystemExit(f"unknown model: {model_name}")


def write_temp_jpg(bgr, path: Path):
  path.parent.mkdir(parents=True, exist_ok=True)
  if not cv2.imwrite(str(path), bgr):
    raise RuntimeError(f"failed to write {path}")


@torch.inference_mode()
def roma_correspondences(model, cam_bgr, map_bgr, num_sample, cert_min, tmp_dir: Path):
  """Return (cam_xy Nx2, map_xy Nx2, certainty N) in original image pixels."""
  h0, w0 = cam_bgr.shape[:2]
  h1, w1 = map_bgr.shape[:2]
  p0 = tmp_dir / "cam.jpg"
  p1 = tmp_dir / "map.jpg"
  write_temp_jpg(cam_bgr, p0)
  write_temp_jpg(map_bgr, p1)

  warp, certainty = model.match(str(p0), str(p1))
  matches, cert = model.sample(warp, certainty, num=num_sample)
  if matches is None or len(matches) == 0:
    return (
      np.zeros((0, 2), np.float64),
      np.zeros((0, 2), np.float64),
      np.zeros((0,), np.float64),
    )

  kpts0, kpts1 = model.to_pixel_coordinates(matches, h0, w0, h1, w1)
  if torch.is_tensor(kpts0):
    kpts0 = kpts0.detach().cpu().numpy()
    kpts1 = kpts1.detach().cpu().numpy()
  if torch.is_tensor(cert):
    cert = cert.detach().cpu().numpy()
  cert = np.asarray(cert, dtype=np.float64).reshape(-1)
  kpts0 = np.asarray(kpts0, dtype=np.float64).reshape(-1, 2)
  kpts1 = np.asarray(kpts1, dtype=np.float64).reshape(-1, 2)

  keep = cert >= cert_min
  # also drop points outside image bounds
  keep &= (
    (kpts0[:, 0] >= 0) & (kpts0[:, 0] < w0) &
    (kpts0[:, 1] >= 0) & (kpts0[:, 1] < h0) &
    (kpts1[:, 0] >= 0) & (kpts1[:, 0] < w1) &
    (kpts1[:, 1] >= 0) & (kpts1[:, 1] < h1)
  )
  return kpts0[keep], kpts1[keep], cert[keep]


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
    iterationsCount=1000,
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


def maybe_downscale_map(map_bgr, max_side):
  """Optional map downscale for speed; returns (image, sx, sy) pixel scales."""
  h, w = map_bgr.shape[:2]
  if max(h, w) <= max_side:
    return map_bgr, 1.0, 1.0
  s = max_side / max(h, w)
  nw, nh = int(round(w * s)), int(round(h * s))
  return cv2.resize(map_bgr, (nw, nh), interpolation=cv2.INTER_AREA), w / nw, h / nh


def evaluate_camera(model, cam, frame, map_bgr, scale, map_h, args, tmp_dir, out_dir):
  K, dist = cam["intrinsics"], cam["distortion"]
  gt_pose, _, _ = solve_pose(cam["map_points"], cam["camera_points"], K, dist)
  gt_t = camera_translation(gt_pose)
  width, height = image_resolution_from_intrinsics(K)
  if frame.shape[1] != width or frame.shape[0] != height:
    frame = cv2.resize(frame, (width, height))

  cam_img = structure_enhance(frame) if args.enhance else frame
  map_img, sx, sy = maybe_downscale_map(map_bgr, args.map_max_side)
  map_img = structure_enhance(map_img) if args.enhance else map_img

  mk_cam, mk_map_s, conf = roma_correspondences(
    model, cam_img, map_img, args.num_sample, args.cert_min, tmp_dir)
  # map coords back to full-resolution map pixels
  mk_map = mk_map_s.copy()
  mk_map[:, 0] *= sx
  mk_map[:, 1] *= sy

  solved = solve_from_matches(mk_map, mk_cam, scale, map_h, K, dist, reproj=args.reproj)

  result = {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "gt_translation_m": gt_t.tolist(),
    "n_raw": int(len(conf)),
    "mean_cert": float(conf.mean()) if len(conf) else 0.0,
    "p2_pass": False,
    "p2_signal": False,
  }
  if len(conf):
    overlay_matches(
      frame, map_bgr, mk_cam, mk_map,
      out_dir / f"{cam['sensor_id']}_p2_roma_matches.png")
  if solved is None:
    result["error"] = "no solve"
    return result

  est = solved["pose"]
  est_t = camera_translation(est)
  # Reject degenerate / below-ground solves (hard prior z > 0).
  if not (est_t[2] > 0) or not np.isfinite(est_t).all() or float(np.linalg.norm(est_t)) > 1e4:
    result["error"] = "degenerate pose"
    result["n_matches"] = solved["n_matches"]
    result["n_inliers"] = solved["n_inliers"]
    result["est_translation_m"] = est_t.tolist()
    return result
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
    "--weights-dir", type=Path,
    default=Path(__file__).resolve().parent / "fixtures/weights")
  ap.add_argument("--model", choices=("tiny", "outdoor"), default="tiny")
  ap.add_argument("--num-sample", type=int, default=5000)
  ap.add_argument("--cert-min", type=float, default=0.05)
  ap.add_argument("--reproj", type=float, default=12.0)
  ap.add_argument("--map-max-side", type=int, default=1280,
                  help="Downscale map longest side before matching (speed).")
  ap.add_argument("--enhance", action="store_true", default=True)
  ap.add_argument("--no-enhance", action="store_false", dest="enhance")
  ap.add_argument("--device", default="cpu")
  ap.add_argument("--cameras", nargs="*", default=None)
  args = ap.parse_args()

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

  print(f"loading RoMa model={args.model} from {args.weights_dir} on {args.device} ...")
  model = load_roma(args.model, args.weights_dir, args.device)
  model.eval()

  results = []
  with tempfile.TemporaryDirectory(prefix="p2_roma_") as tmp:
    tmp_dir = Path(tmp)
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
        model, cam, frame, map_bgr, scale, map_h, args, tmp_dir, args.out_dir)
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
    "source": f"RoMa {args.model} cross-view (P2 priority 1)",
    "model": args.model,
    "weights_dir": str(args.weights_dir),
    "num_sample": args.num_sample,
    "cert_min": args.cert_min,
    "enhance": args.enhance,
    "map_max_side": args.map_max_side,
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "cameras": results,
    "p2_pass_count": n_pass,
    "p2_signal_count": n_signal,
    "p2_pass": n_pass >= 2,
    "p2_signal": n_signal >= 2,
  }
  out_json = args.out_dir / f"p2_roma_{args.model}_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(
    f"\np2_pass={summary['p2_pass']} ({n_pass}/{len(results)})  "
    f"p2_signal={summary['p2_signal']} ({n_signal}/{len(results)})  "
    f"wrote {out_json}"
  )
  return 0 if summary["p2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
