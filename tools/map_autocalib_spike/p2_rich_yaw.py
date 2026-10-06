#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""P2 richer yaw cues: RGB forward-BEV match + marking orientation.

Structure-only BEV+NCC and fold/flip do not rank the correct Manhattan
heading on Smart Intersection. This spike replaces the appearance cue with:

  1. RGB (Lab) forward-BEV ↔ ortho crop correlation under each yaw hyp
  2. Marking-orientation histogram agreement (stripe / edge angles in BEV)

Modes
  oracle_xy — GT camera XY (and pitch/height); only yaw ranked (diagnostic)
  search    — coarse XY grid + yaw candidates (automatic path)

Example:
  .venv-roma/bin/python p2_rich_yaw.py \\
    --fixture-dir /tmp/smart-intersection-v0 --frames-dir fixtures/videos \\
    --out-dir out --mode oracle_xy
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
  map_metres_to_pixels,
  pose_from_look,
  solve_pose,
)
from p2_bev_match import (
  dense_bev, look_yaw_pitch, map_structure_grid, structure_image, summarize)
from p2_yaw_prior import (
  angle_diff_deg,
  estimate_vanishing_point,
  pitch_from_vp,
  yaw_candidates_from_manhattan,
)


def _lab_float(bgr):
  lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
  lab[:, :, 0] /= 255.0
  lab[:, :, 1:] = (lab[:, :, 1:] - 128.0) / 128.0
  return lab


def map_forward_crop(map_bgr, scale, map_h, cx, cy, yaw_deg, meta):
  """Sample ortho into the same forward-BEV frame as dense_bev (camera at cx,cy)."""
  res = meta["res"]
  near, ahead = meta["near"], meta["ahead"]
  half_lat = meta["half_lat"]
  yaw = math.radians(yaw_deg)
  fwd = np.array([math.cos(yaw), math.sin(yaw)], dtype=np.float64)
  right = np.array([-math.sin(yaw), math.cos(yaw)], dtype=np.float64)
  us = np.arange(near, ahead, res)
  vs = np.arange(-half_lat, half_lat, res)
  uu, vv = np.meshgrid(us, vs)
  xy = np.array([cx, cy], dtype=np.float64) + uu[..., None] * fwd + vv[..., None] * right
  flat = xy.reshape(-1, 2)
  pix = map_metres_to_pixels(flat, scale, map_h).astype(np.float32)
  map_w = map_bgr.shape[1]
  u = pix[:, 0].reshape(uu.shape)
  v = pix[:, 1].reshape(uu.shape)
  valid = (u >= 0) & (u < map_w - 1) & (v >= 0) & (v < map_h - 1)
  crop = cv2.remap(
    map_bgr, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
  crop[~valid] = 0
  return crop, float(valid.mean())


def masked_channel_ncc(a, b, mask, eps=1e-6):
  """Mean NCC across channels on a shared mask."""
  if mask.sum() < 80:
    return 0.0
  scores = []
  for c in range(a.shape[2]):
    aa = a[:, :, c][mask].astype(np.float64)
    bb = b[:, :, c][mask].astype(np.float64)
    aa -= aa.mean()
    bb -= bb.mean()
    den = np.linalg.norm(aa) * np.linalg.norm(bb)
    scores.append(float(np.dot(aa, bb) / (den + eps)))
  return float(np.mean(scores))


def marking_angle_hist(bgr, bins=18):
  """Orientation histogram of marking/edge structure in [0, 180)."""
  struct = structure_image(bgr)
  gray = (np.clip(struct, 0, 1) * 255).astype(np.uint8)
  gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
  gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
  mag = cv2.magnitude(gx, gy)
  ang = (cv2.phase(gx, gy, angleInDegrees=True) % 180.0)
  thr = max(20.0, float(np.percentile(mag, 70)))
  m = mag >= thr
  if int(m.sum()) < 50:
    return np.zeros(bins, np.float64)
  hist, _ = np.histogram(ang[m], bins=bins, range=(0.0, 180.0), weights=mag[m])
  hist = hist.astype(np.float64)
  s = hist.sum()
  if s < 1e-6:
    return np.zeros(bins, np.float64)
  return hist / s


def hist_circular_corr(h0, h1):
  """Max circular correlation of two [0,180) orientation histograms."""
  if h0.sum() < 1e-9 or h1.sum() < 1e-9:
    return 0.0
  a = h0 - h0.mean()
  b = h1 - h1.mean()
  best = -1.0
  n = len(a)
  for k in range(n):
    bb = np.roll(b, k)
    den = np.linalg.norm(a) * np.linalg.norm(bb)
    if den < 1e-9:
      continue
    best = max(best, float(np.dot(a, bb) / den))
  return max(0.0, best)


def score_rgb_marking(bev_bgr, map_crop, rgb_weight=0.65):
  """Combined RGB Lab NCC + marking-orientation agreement."""
  mask = (cv2.cvtColor(bev_bgr, cv2.COLOR_BGR2GRAY) > 8) & (
    cv2.cvtColor(map_crop, cv2.COLOR_BGR2GRAY) > 8)
  rgb = masked_channel_ncc(_lab_float(bev_bgr), _lab_float(map_crop), mask)
  mark = hist_circular_corr(marking_angle_hist(bev_bgr), marking_angle_hist(map_crop))
  score = rgb_weight * rgb + (1.0 - rgb_weight) * mark
  return {
    "score": float(score),
    "rgb_ncc": float(rgb),
    "mark_corr": float(mark),
    "mask_frac": float(mask.mean()),
  }


def xy_candidates(gt_xy, mode, span_m, step_m):
  if mode == "oracle_xy":
    return [np.asarray(gt_xy, dtype=np.float64)]
  xs = np.arange(gt_xy[0] - span_m, gt_xy[0] + span_m + 1e-6, step_m)
  ys = np.arange(gt_xy[1] - span_m, gt_xy[1] + span_m + 1e-6, step_m)
  # Always include GT for diagnostic ranking even in search (not used as prior
  # for scoring — just denser near GT). Search is centered on GT for spike
  # cost; product search would use a scene bbox.
  out = [np.array([x, y], dtype=np.float64) for x in xs for y in ys]
  return out


def yaw_list(frame, map_grid, gt_yaw, mode, yaw_window, yaw_step):
  cands, map_angs, cam_angs = yaw_candidates_from_manhattan(frame, map_grid)
  if mode == "oracle_xy":
    # Rank all Manhattan families plus a tight band around GT for recall check.
    bases = list(cands)
    for d in np.arange(-yaw_window, yaw_window + 1e-6, yaw_step):
      bases.append((gt_yaw + d) % 360.0)
    uniq = []
    for a in bases:
      if not any(angle_diff_deg(a, u) < 2.5 for u in uniq):
        uniq.append(float(a % 360.0))
    return uniq, map_angs, cam_angs
  return [float(a) for a in cands], map_angs, cam_angs


def evaluate_camera(cam, frame, map_bgr, map_grid, scale, map_h, args, out_dir):
  K, dist = cam["intrinsics"], cam["distortion"]
  gt_pose, _, _ = solve_pose(cam["map_points"], cam["camera_points"], K, dist)
  gt_t = camera_translation(gt_pose)
  gt_yaw, gt_pitch = look_yaw_pitch(gt_pose)
  width, height = image_resolution_from_intrinsics(K)
  if frame.shape[1] != width or frame.shape[0] != height:
    frame = cv2.resize(frame, (width, height))

  vp_info = estimate_vanishing_point(frame)
  if vp_info is not None:
    pitch_est, pitch_ok = pitch_from_vp(vp_info["vp"], K)
  else:
    pitch_est, pitch_ok = float(gt_pitch), False

  if args.mode == "oracle_xy":
    pitches = [float(gt_pitch)]
    heights = [float(gt_t[2])]
  else:
    pitches = [pitch_est]
    for d in (-2.0, 2.0):
      p = pitch_est + d
      if 4.0 <= p <= 20.0:
        pitches.append(p)
    heights = [5.0, 6.5, 8.0]

  yaws, map_angs, cam_angs = yaw_list(
    frame, map_grid, gt_yaw, args.mode, args.yaw_window, args.yaw_step)
  xys = xy_candidates(gt_t[:2], args.mode, args.xy_span, args.xy_step)

  best = None
  ranked = []
  for yaw in yaws:
    for pitch in pitches:
      for height in heights:
        pose0 = pose_from_look(0.0, 0.0, float(height), float(yaw), float(pitch))
        painted = dense_bev(
          frame, pose0, K, yaw, res=args.bev_res, ahead=args.ahead,
          half_lat=args.half_lat, near=args.near)
        if painted is None:
          continue
        bev, meta = painted
        local_best = None
        for xy in xys:
          crop, cov = map_forward_crop(
            map_bgr, scale, map_h, float(xy[0]), float(xy[1]), yaw, meta)
          if cov < 0.2:
            continue
          sc = score_rgb_marking(bev, crop, rgb_weight=args.rgb_weight)
          if sc["mask_frac"] < 0.1:
            continue
          cand = {
            **sc,
            "xy": xy,
            "yaw": float(yaw),
            "pitch": float(pitch),
            "height": float(height),
            "map_cov": cov,
            "yaw_err_to_gt_deg": angle_diff_deg(yaw, gt_yaw),
          }
          if local_best is None or cand["score"] > local_best["score"]:
            local_best = cand
        if local_best is not None:
          ranked.append(local_best)
          if best is None or local_best["score"] > best["score"]:
            best = local_best

  ranked.sort(key=lambda c: c["score"], reverse=True)
  # Collapse to best per ~10° yaw bin for readable top-k
  top = []
  for c in ranked:
    if not any(angle_diff_deg(c["yaw"], t["yaw"]) < 10.0 for t in top):
      top.append(c)
    if len(top) >= 6:
      break

  gt_rank = None
  for i, c in enumerate(ranked):
    if angle_diff_deg(c["yaw"], gt_yaw) <= max(args.yaw_step, 5.0):
      gt_rank = i + 1
      break

  extra = {
    "mode": args.mode,
    "pitch_est_deg": pitch_est,
    "pitch_from_vp": pitch_ok,
    "yaw_candidates_deg": yaws,
    "map_manhattan_deg": map_angs,
    "cam_line_deg": cam_angs,
    "n_ranked": len(ranked),
    "gt_yaw_rank": gt_rank,
    "top_yaws": [
      {
        "yaw": t["yaw"], "score": t["score"], "rgb_ncc": t["rgb_ncc"],
        "mark_corr": t["mark_corr"], "yaw_err_to_gt_deg": t["yaw_err_to_gt_deg"],
        "xy": t["xy"].tolist(),
      }
      for t in top
    ],
  }
  if best is None:
    return summarize(cam, None, gt_pose, {**extra, "error": "no candidates"})

  # Confidence: orthogonal rival with close RGB score → needs_click
  needs_click = False
  conf_reason = "unique rich-yaw mode"
  if len(top) >= 2 and angle_diff_deg(top[0]["yaw"], top[1]["yaw"]) >= 70.0:
    ratio = top[1]["score"] / max(top[0]["score"], 1e-6)
    if ratio >= args.score_ratio:
      needs_click = True
      conf_reason = f"ambiguous orthogonal rich scores (ratio {ratio:.2f})"
    else:
      conf_reason = f"best beats orthogonal rival (ratio {ratio:.2f})"
  extra["needs_click"] = needs_click
  extra["confidence_reason"] = conf_reason

  pose = pose_from_look(
    float(best["xy"][0]), float(best["xy"][1]), float(best["height"]),
    float(best["yaw"]), float(best["pitch"]))
  r = summarize(cam, pose, gt_pose, {
    **extra,
    "score": best["score"],
    "rgb_ncc": best["rgb_ncc"],
    "mark_corr": best["mark_corr"],
    "est_yaw_deg": best["yaw"],
    "est_pitch_deg": best["pitch"],
    "est_height_m": best["height"],
    "yaw_err_to_gt_deg": best["yaw_err_to_gt_deg"],
  })
  # Overlay
  vis = frame.copy()
  cv2.putText(
    vis,
    f"yaw={best['yaw']:.0f} gt={gt_yaw:.0f} err={best['yaw_err_to_gt_deg']:.0f} "
    f"rank={gt_rank} rgb={best['rgb_ncc']:.2f} mk={best['mark_corr']:.2f}",
    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
  cv2.imwrite(str(out_dir / f"{cam['sensor_id']}_rich_yaw.png"), vis)
  return r


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument("--mode", choices=("oracle_xy", "search"), default="oracle_xy")
  ap.add_argument("--bev-res", type=float, default=0.5)
  ap.add_argument("--ahead", type=float, default=55.0)
  ap.add_argument("--half-lat", type=float, default=28.0)
  ap.add_argument("--near", type=float, default=6.0)
  ap.add_argument("--yaw-window", type=float, default=15.0)
  ap.add_argument("--yaw-step", type=float, default=5.0)
  ap.add_argument("--xy-span", type=float, default=12.0)
  ap.add_argument("--xy-step", type=float, default=4.0)
  ap.add_argument("--rgb-weight", type=float, default=1.0,
                  help="Weight of Lab RGB NCC vs marking hist (1=RGB only).")
  ap.add_argument("--score-ratio", type=float, default=0.9,
                  help="needs_click if orthogonal rival score / best >= this.")
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
  map_grid, _ = map_structure_grid(map_bgr, scale, args.bev_res)
  frames_dir = args.frames_dir or (Path(__file__).resolve().parent / "fixtures" / "videos")

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
    gt_pose, _, _ = solve_pose(
      cam["map_points"], cam["camera_points"],
      cam["intrinsics"], cam["distortion"])
    gt_yaw, _ = look_yaw_pitch(gt_pose)
    r = evaluate_camera(
      cam, frame, map_bgr, map_grid, scale, map_h, args, args.out_dir)
    r["gt_yaw_deg"] = gt_yaw
    results.append(r)
    print(
      f"{r['sensor_id']:8s}  yaw={r.get('est_yaw_deg', float('nan')):6.1f}  "
      f"gt={gt_yaw:6.1f}  yaw_err={r.get('yaw_err_to_gt_deg', float('nan')):5.1f}  "
      f"rank={r.get('gt_yaw_rank')}  "
      f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
      f"rgb={r.get('rgb_ncc', float('nan'))}  "
      f"need_click={r.get('needs_click')}  signal={r.get('p2_signal')}  "
      f"({r.get('confidence_reason')})"
    )

  n_signal = sum(1 for c in results if c.get("p2_signal"))
  n_pass = sum(1 for c in results if c.get("p2_pass"))
  n_yaw_ok = sum(
    1 for c in results
    if c.get("yaw_err_to_gt_deg") is not None and c["yaw_err_to_gt_deg"] <= 20.0)
  n_rank1 = sum(1 for c in results if c.get("gt_yaw_rank") == 1)
  summary = {
    "scene": scene["name"],
    "source": "RGB forward-BEV + marking orientation (rich yaw)",
    "mode": args.mode,
    "rgb_weight": args.rgb_weight,
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "yaw_ok_bar": "yaw_err<=20deg",
    "cameras": results,
    "p2_pass_count": n_pass,
    "p2_signal_count": n_signal,
    "yaw_ok_count": n_yaw_ok,
    "gt_rank1_count": n_rank1,
    "p2_pass": n_pass >= 2,
    "p2_signal": n_signal >= 2,
    "yaw_signal": n_yaw_ok >= 2 or n_rank1 >= 2,
  }

  def _conv(o):
    if isinstance(o, np.generic):
      return o.item()
    if isinstance(o, np.ndarray):
      return o.tolist()
    raise TypeError(type(o))

  out_json = args.out_dir / f"p2_rich_yaw_{args.mode}_results.json"
  out_json.write_text(json.dumps(summary, indent=2, default=_conv))
  print(
    f"\np2_signal={summary['p2_signal']} ({n_signal}/{len(results)})  "
    f"yaw_ok={n_yaw_ok}  gt_rank1={n_rank1}  yaw_signal={summary['yaw_signal']}  "
    f"wrote {out_json}"
  )
  return 0 if summary["yaw_signal"] or summary["p2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
