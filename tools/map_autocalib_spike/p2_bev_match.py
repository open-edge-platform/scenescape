#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""P2 BEV-conditioned matcher: pose hypotheses → BEV warp → dense match.

For each (yaw, pitch, height) hypothesis, warp the camera into a forward
bird's-eye patch, then either:
  - ncc:  structure BEV ↔ structure map via template match (V2-style), or
  - roma: tiny-RoMa dense match BEV ↔ map; RANSAC translation for XY.

Modes:
  oracle  — GT yaw/pitch/height; only XY from the matcher (diagnostic)
  search  — full yaw (/pitch/height) grid; automatic path

Example:
  .venv-roma/bin/python p2_bev_match.py \\
    --fixture-dir /tmp/smart-intersection-v0 --frames-dir fixtures/videos \\
    --out-dir out --matcher ncc --mode search
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import torch

from spike_common import (
  SI_CAMERA_VIDEO,
  camera_translation,
  image_from_ground_homography,
  image_resolution_from_intrinsics,
  load_smart_intersection,
  map_pixels_to_metres,
  pose_from_look,
  ray_to_ground,
  rotation_angle_deg,
  solve_pose,
)


def look_yaw_pitch(pose):
  look = pose[:3, 2]
  pitch = math.degrees(math.asin(float(np.clip(-look[2], -1.0, 1.0))))
  yaw = math.degrees(math.atan2(float(look[1]), float(look[0]))) % 360.0
  return yaw, pitch


def structure_image(bgr, ground_bias=False):
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


def dense_bev(frame, pose, K, yaw_deg, res=0.4, ahead=70.0, half_lat=40.0, near=5.0):
  """Forward-biased RGB BEV in camera-local world frame (pose XY should be 0,0).

  Returns (bev_bgr, meta) or None. meta maps BEV pixels → world metres when the
  real camera XY is later added (bev is painted as if camera is at origin).
  """
  H = image_from_ground_homography(pose, K)
  yaw = math.radians(yaw_deg)
  fwd = np.array([math.cos(yaw), math.sin(yaw)], dtype=np.float64)
  right = np.array([-math.sin(yaw), math.cos(yaw)], dtype=np.float64)

  us = np.arange(near, ahead, res)          # along look on ground
  vs = np.arange(-half_lat, half_lat, res)  # lateral
  uu, vv = np.meshgrid(us, vs)  # rows = lateral, cols = forward
  # world XY with camera at origin
  xy = uu[..., None] * fwd + vv[..., None] * right
  ones = np.ones(xy.shape[:2] + (1,), dtype=np.float64)
  pts = np.concatenate([xy, ones], axis=-1).reshape(-1, 3).T
  proj = H @ pts
  depth = proj[2].reshape(uu.shape)
  u = (proj[0] / proj[2]).reshape(uu.shape).astype(np.float32)
  v = (proj[1] / proj[2]).reshape(uu.shape).astype(np.float32)
  valid = depth > 0.1
  bev = cv2.remap(frame, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
  bev[~valid] = 0
  coverage = float(valid.mean())
  if coverage < 0.05:
    return None
  # Axis-aligned world bounds of this BEV (for pixel→metre)
  # row 0 = v=-half_lat, col 0 = u=near
  meta = {
    "res": res,
    "near": near,
    "ahead": ahead,
    "half_lat": half_lat,
    "yaw_deg": yaw_deg,
    "fwd": fwd,
    "right": right,
    "coverage": coverage,
    "rows": bev.shape[0],
    "cols": bev.shape[1],
  }
  return bev, meta


def bev_pixels_to_local_xy(px, meta):
  """BEV pixel (col,row) → ground metres relative to camera at origin."""
  # col → forward distance, row → lateral (row 0 = -half_lat)
  fwd_m = meta["near"] + px[:, 0] * meta["res"]
  lat_m = -meta["half_lat"] + px[:, 1] * meta["res"]
  xy = fwd_m[:, None] * meta["fwd"] + lat_m[:, None] * meta["right"]
  return xy


def map_structure_grid(map_bgr, scale, res):
  struct = structure_image(map_bgr)
  h_px, w_px = struct.shape
  cols = int(np.ceil((w_px / scale) / res))
  rows = int(np.ceil((h_px / scale) / res))
  grid = cv2.resize(struct, (cols, rows), interpolation=cv2.INTER_AREA)
  return grid, h_px / scale


def structure_paint_bev(frame, pose, K, dist, res, max_range=90.0, pad=4.0):
  """V2-style structure BEV with known camera pixel (cam at pose XY, often origin)."""
  cam_struct = structure_image(frame, ground_bias=True)
  ys, xs = np.where(cam_struct > 0.12)
  if len(xs) == 0:
    return None
  idx = np.arange(0, len(xs), 3)
  xs, ys = xs[idx], ys[idx]
  wts = cam_struct[ys, xs]
  uv = np.stack([xs, ys], axis=1).astype(np.float32)
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


def ncc_place_structure(bev, cam_uv, map_grid, ymax_m, res):
  if bev.shape[0] >= map_grid.shape[0] or bev.shape[1] >= map_grid.shape[1]:
    return None
  resp = cv2.matchTemplate(map_grid, bev, cv2.TM_CCOEFF_NORMED)
  _, score, _, loc = cv2.minMaxLoc(resp)
  cx = (loc[0] + cam_uv[0]) * res
  cy = ymax_m - (loc[1] + cam_uv[1]) * res
  return {"score": float(score), "xy": np.array([cx, cy], dtype=np.float64)}


def load_tiny_roma(weights_dir: Path, device: str):
  from romatch import tiny_roma_v1_outdoor
  path = weights_dir / "tiny_roma_v1_outdoor.pth"
  if not path.is_file():
    raise SystemExit(f"missing {path}")
  weights = torch.load(str(path), map_location="cpu", weights_only=True)
  return tiny_roma_v1_outdoor(device=device, weights=weights).eval()


def _struct_bgr(bgr):
  s = (structure_image(bgr) * 255).astype(np.uint8)
  return cv2.cvtColor(s, cv2.COLOR_GRAY2BGR)


def _map_crop(map_bgr, scale, map_h, cx, cy, half_m, bev_res):
  corners = np.array([
    [cx - half_m, cy - half_m],
    [cx + half_m, cy + half_m],
  ], dtype=np.float64)
  from spike_common import map_metres_to_pixels
  pix = map_metres_to_pixels(corners, scale, map_h)
  x0 = int(max(0, math.floor(pix[:, 0].min())))
  x1 = int(min(map_bgr.shape[1], math.ceil(pix[:, 0].max())))
  y0 = int(max(0, math.floor(pix[:, 1].min())))
  y1 = int(min(map_bgr.shape[0], math.ceil(pix[:, 1].max())))
  if x1 - x0 < 32 or y1 - y0 < 32:
    return None
  crop = map_bgr[y0:y1, x0:x1]
  tw = max(32, int(round((x1 - x0) / scale / bev_res)))
  th = max(32, int(round((y1 - y0) / scale / bev_res)))
  return cv2.resize(crop, (tw, th), interpolation=cv2.INTER_AREA), (x0, y0), (x1 - x0, y1 - y0)


@torch.inference_mode()
def roma_place(model, bev_bgr, map_bgr, meta, scale, map_h, num_sample, cert_min,
               tmp_dir, crop_centers, half_m=50.0):
  """RoMa match structure-BEV ↔ map crops; RANSAC translation → camera XY."""
  h0, w0 = bev_bgr.shape[:2]
  bev_s = _struct_bgr(bev_bgr)
  p0 = tmp_dir / "bev.jpg"
  cv2.imwrite(str(p0), bev_s)
  best = None
  for cx, cy in crop_centers:
    cropped = _map_crop(map_bgr, scale, map_h, cx, cy, half_m, meta["res"])
    if cropped is None:
      continue
    crop_r, (x0, y0), (cw, ch) = cropped
    tw, th = crop_r.shape[1], crop_r.shape[0]
    p1 = tmp_dir / "map.jpg"
    cv2.imwrite(str(p1), _struct_bgr(crop_r))
    warp, certainty = model.match(str(p0), str(p1))
    matches, cert = model.sample(warp, certainty, num=num_sample)
    if matches is None or len(matches) == 0:
      continue
    k0, k1 = model.to_pixel_coordinates(matches, h0, w0, th, tw)
    if torch.is_tensor(k0):
      k0 = k0.detach().cpu().numpy()
      k1 = k1.detach().cpu().numpy()
      cert = cert.detach().cpu().numpy()
    cert = np.asarray(cert, dtype=np.float64).reshape(-1)
    k0 = np.asarray(k0, dtype=np.float64).reshape(-1, 2)
    k1 = np.asarray(k1, dtype=np.float64).reshape(-1, 2)
    keep = (
      (cert >= cert_min) &
      (k0[:, 0] >= 0) & (k0[:, 0] < w0) & (k0[:, 1] >= 0) & (k0[:, 1] < h0) &
      (k1[:, 0] >= 0) & (k1[:, 0] < tw) & (k1[:, 1] >= 0) & (k1[:, 1] < th)
    )
    k0, k1, cert = k0[keep], k1[keep], cert[keep]
    if len(k0) < 8:
      continue
    map_px = np.stack([
      x0 + k1[:, 0] * (cw / tw),
      y0 + k1[:, 1] * (ch / th),
    ], axis=1)
    local = bev_pixels_to_local_xy(k0, meta)
    world = map_pixels_to_metres(map_px, scale, map_h)
    delta = world - local
    best_n, best_t = 0, None
    rng = np.random.default_rng(0)
    for _ in range(600):
      i = int(rng.integers(0, len(delta)))
      t = delta[i]
      inl = np.linalg.norm(delta - t, axis=1) < 3.0
      n = int(inl.sum())
      if n > best_n:
        best_n = n
        best_t = np.median(delta[inl], axis=0)
    if best_t is None or best_n < 6:
      continue
    crop_dist = float(np.linalg.norm(best_t - np.array([cx, cy])))
    score = best_n - 0.05 * crop_dist
    cand = {
      "xy": best_t,
      "n_inliers": best_n,
      "n_matches": int(len(delta)),
      "score": float(score),
      "mean_cert": float(cert.mean()),
    }
    if best is None or cand["score"] > best["score"]:
      best = cand
  return best


def summarize(cam, pose, gt_pose, extra=None):
  gt_t = camera_translation(gt_pose)
  out = {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "gt_translation_m": gt_t.tolist(),
    "p2_pass": False,
    "p2_signal": False,
  }
  if extra:
    out.update(extra)
  if pose is None:
    out.setdefault("error", "no pose")
    return out
  est_t = camera_translation(pose)
  if not (est_t[2] > 0) or not np.isfinite(est_t).all() or float(np.linalg.norm(est_t)) > 1e4:
    out["error"] = "degenerate pose"
    out["est_translation_m"] = est_t.tolist()
    return out
  d_t = float(np.linalg.norm(est_t - gt_t))
  d_r = float(rotation_angle_deg(pose, gt_pose))
  out.update({
    "est_translation_m": est_t.tolist(),
    "translation_err_m": d_t,
    "xy_err_m": float(np.linalg.norm(est_t[:2] - gt_t[:2])),
    "z_err_m": float(abs(est_t[2] - gt_t[2])),
    "rotation_err_deg": d_r,
    "above_ground": True,
    "p2_pass": bool(d_t <= 1.0 and d_r <= 8.0),
    "p2_signal": bool(d_t <= 5.0 and d_r <= 20.0),
  })
  return out


def evaluate_hypotheses(cam, frame, map_bgr, map_grid, ymax_m, scale, map_h,
                        gt_pose, hyps, args, roma_model, tmp_dir, out_dir,
                        crop_centers):
  K = cam["intrinsics"]
  dist = cam["distortion"]
  best = None
  trials = 0
  for yaw, pitch, height in hyps:
    trials += 1
    pose0 = pose_from_look(0.0, 0.0, float(height), float(yaw), float(pitch))
    if args.matcher == "ncc":
      painted = structure_paint_bev(frame, pose0, K, dist, args.bev_res)
      if painted is None:
        continue
      bev, cam_uv = painted
      hit = ncc_place_structure(bev, cam_uv, map_grid, ymax_m, args.bev_res)
      if hit is None:
        continue
      cand = {
        "score": hit["score"],
        "xy": hit["xy"],
        "yaw": yaw,
        "pitch": pitch,
        "height": height,
        "coverage": None,
        "n_inliers": None,
      }
      bev_vis = (np.clip(bev, 0, 1) * 255).astype(np.uint8)
      bev_vis = cv2.cvtColor(bev_vis, cv2.COLOR_GRAY2BGR)
    else:
      painted = dense_bev(
        frame, pose0, K, yaw, res=args.bev_res, ahead=args.ahead,
        half_lat=args.half_lat, near=args.near)
      if painted is None:
        continue
      bev, meta = painted
      hit = roma_place(
        roma_model, bev, map_bgr, meta, scale, map_h,
        args.num_sample, args.cert_min, tmp_dir, crop_centers,
        half_m=args.crop_half_m)
      if hit is None:
        continue
      cand = {
        "score": hit["score"],
        "xy": hit["xy"],
        "yaw": yaw,
        "pitch": pitch,
        "height": height,
        "coverage": meta["coverage"],
        "n_inliers": hit["n_inliers"],
        "n_matches": hit["n_matches"],
        "mean_cert": hit["mean_cert"],
      }
      bev_vis = bev
    if best is None or cand["score"] > best["score"]:
      best = cand
      if args.save_bev:
        cv2.imwrite(str(out_dir / f"{cam['sensor_id']}_best_bev.png"), bev_vis)

  if best is None:
    return summarize(cam, None, gt_pose, {"trials": trials, "error": "no hyp"}), trials

  pose = pose_from_look(
    float(best["xy"][0]), float(best["xy"][1]), float(best["height"]),
    float(best["yaw"]), float(best["pitch"]))
  return summarize(cam, pose, gt_pose, {
    "trials": trials,
    "score": best["score"],
    "est_yaw_deg": best["yaw"],
    "est_pitch_deg": best["pitch"],
    "est_height_m": best["height"],
    "n_inliers": best.get("n_inliers"),
    "coverage": best.get("coverage"),
  }), trials


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument("--matcher", choices=("ncc", "roma"), default="ncc")
  ap.add_argument("--mode", choices=("oracle", "search"), default="search")
  ap.add_argument(
    "--weights-dir", type=Path,
    default=Path(__file__).resolve().parent / "fixtures/weights")
  ap.add_argument("--device", default="cpu")
  ap.add_argument("--bev-res", type=float, default=0.4)
  ap.add_argument("--ahead", type=float, default=70.0)
  ap.add_argument("--half-lat", type=float, default=40.0)
  ap.add_argument("--near", type=float, default=5.0)
  ap.add_argument("--yaw-step", type=float, default=10.0)
  ap.add_argument("--num-sample", type=int, default=4000)
  ap.add_argument("--cert-min", type=float, default=0.15)
  ap.add_argument("--crop-half-m", type=float, default=50.0)
  ap.add_argument("--xy-grid", type=int, default=4,
                  help="Coarse map XY crop grid for RoMa matcher.")
  ap.add_argument("--save-bev", action="store_true")
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
  map_grid, ymax_m = map_structure_grid(map_bgr, scale, args.bev_res)
  frames_dir = args.frames_dir or (Path(__file__).resolve().parent / "fixtures" / "videos")

  roma_model = None
  if args.matcher == "roma":
    print(f"loading tiny RoMa from {args.weights_dir} ...")
    roma_model = load_tiny_roma(args.weights_dir, args.device)

  results = []
  with tempfile.TemporaryDirectory(prefix="p2_bev_") as tmp:
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
      K = cam["intrinsics"]
      w, h = image_resolution_from_intrinsics(K)
      if frame.shape[1] != w or frame.shape[0] != h:
        frame = cv2.resize(frame, (w, h))
      gt_pose, _, _ = solve_pose(
        cam["map_points"], cam["camera_points"], K, cam["distortion"])
      gt_t = camera_translation(gt_pose)
      gt_yaw, gt_pitch = look_yaw_pitch(gt_pose)

      if args.mode == "oracle":
        hyps = [(gt_yaw, gt_pitch, float(gt_t[2]))]
      else:
        yaws = np.arange(0.0, 360.0, args.yaw_step)
        pitches = np.arange(6.0, 15.1, 4.0)
        heights = [5.0, 6.5, 8.0]
        hyps = [(float(y), float(p), float(h_))
                for y in yaws for p in pitches for h_ in heights]

      # RoMa crop centers: coarse grid, plus GT XY in oracle mode.
      w_m = map_bgr.shape[1] / scale
      h_m = map_h / scale
      xs = np.linspace(0.2 * w_m, 0.8 * w_m, args.xy_grid)
      ys = np.linspace(0.2 * h_m, 0.8 * h_m, args.xy_grid)
      crop_centers = [(float(x), float(y)) for y in ys for x in xs]
      if args.mode == "oracle":
        crop_centers = crop_centers + [(float(gt_t[0]), float(gt_t[1]))]

      r, trials = evaluate_hypotheses(
        cam, frame, map_bgr, map_grid, ymax_m, scale, map_h,
        gt_pose, hyps, args, roma_model, tmp_dir, args.out_dir, crop_centers)
      r["mode"] = args.mode
      r["matcher"] = args.matcher
      r["gt_yaw_deg"] = gt_yaw
      r["gt_pitch_deg"] = gt_pitch
      results.append(r)
      print(
        f"{r['sensor_id']:8s}  {args.matcher}/{args.mode}  "
        f"trials={trials}  score={r.get('score', float('nan'))}  "
        f"inl={r.get('n_inliers')}  "
        f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
        f"dR={r.get('rotation_err_deg', float('nan')):6.1f}deg  "
        f"yaw={r.get('est_yaw_deg', float('nan'))}  "
        f"pass={r.get('p2_pass')} signal={r.get('p2_signal')}"
      )

  n_pass = sum(1 for c in results if c.get("p2_pass"))
  n_signal = sum(1 for c in results if c.get("p2_signal"))
  summary = {
    "scene": scene["name"],
    "source": f"BEV-conditioned {args.matcher} ({args.mode})",
    "matcher": args.matcher,
    "mode": args.mode,
    "yaw_step": args.yaw_step if args.mode == "search" else None,
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "cameras": results,
    "p2_pass_count": n_pass,
    "p2_signal_count": n_signal,
    "p2_pass": n_pass >= 2,
    "p2_signal": n_signal >= 2,
  }
  out_json = args.out_dir / f"p2_bev_{args.matcher}_{args.mode}_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(
    f"\np2_pass={summary['p2_pass']} ({n_pass}/{len(results)})  "
    f"p2_signal={summary['p2_signal']} ({n_signal}/{len(results)})  "
    f"wrote {out_json}"
  )
  return 0 if summary["p2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
