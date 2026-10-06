#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""P2 yaw prior: vanishing/horizon cues + local BEV–NCC + confidence gate.

Pipeline
  1. Estimate pitch from a ground-plane vanishing point (line RANSAC).
  2. Build absolute yaw candidates by pairing camera line directions with
     Manhattan orientations from the ortho structure (0/90° families + flips).
  3. Local BEV+NCC refine in ±yaw_window around each candidate (and a small
     pitch/height band).
  4. Confidence gate: if the top two distinct yaw modes are ~90° apart and
     close in NCC score → needs_click (prompt for human heading/click).

Example:
  python3 p2_yaw_prior.py \\
    --fixture-dir /tmp/smart-intersection-v0 --frames-dir fixtures/videos \\
    --out-dir out
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
  rotation_angle_deg,
  solve_pose,
)
from p2_bev_match import (
  look_yaw_pitch,
  map_structure_grid,
  ncc_place_structure,
  structure_paint_bev,
  summarize,
)


def _detect_lines(gray):
  """Line segments as (x1,y1,x2,y2). Prefer LSD; fall back to Hough."""
  if hasattr(cv2, "createLineSegmentDetector"):
    try:
      lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
      segs, *_ = lsd.detect(gray)
      if segs is not None and len(segs):
        return segs.reshape(-1, 4).astype(np.float64)
    except cv2.error:
      pass
  edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
  lines = cv2.HoughLinesP(
    edges, 1, np.pi / 180, threshold=60, minLineLength=40, maxLineGap=10)
  if lines is None:
    return np.zeros((0, 4), np.float64)
  return lines.reshape(-1, 4).astype(np.float64)


def _line_params(segs):
  """Return midpoints, unit directions, lengths."""
  p1 = segs[:, :2]
  p2 = segs[:, 2:]
  d = p2 - p1
  lengths = np.linalg.norm(d, axis=1)
  ok = lengths > 1e-3
  p1, p2, d, lengths = p1[ok], p2[ok], d[ok], lengths[ok]
  dirs = d / lengths[:, None]
  # force dir angle into (-90, 90] for uniqueness of undirected lines
  flip = dirs[:, 0] < 0
  dirs[flip] *= -1
  mids = 0.5 * (p1 + p2)
  return mids, dirs, lengths


def estimate_vanishing_point(frame, max_segs=250):
  """RANSAC VP from line intersections in the lower image (ground-dominated)."""
  h, w = frame.shape[:2]
  gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  # Bias to lower FOV where ground markings live
  roi = gray[int(0.25 * h):, :]
  y_off = int(0.25 * h)
  segs = _detect_lines(roi)
  if len(segs) < 4:
    return None
  segs = segs.copy()
  segs[:, [1, 3]] += y_off
  mids, dirs, lengths = _line_params(segs)
  # Drop near-horizontal image lines (often horizon / curb parallel to image x)
  ang = np.degrees(np.arctan2(np.abs(dirs[:, 1]), np.abs(dirs[:, 0]) + 1e-9))
  keep = (ang > 15.0) & (ang < 75.0) & (lengths > 30.0)
  mids, dirs, lengths = mids[keep], dirs[keep], lengths[keep]
  if len(mids) < 4:
    return None
  # Keep longest
  order = np.argsort(-lengths)[:max_segs]
  mids, dirs, lengths = mids[order], dirs[order], lengths[order]
  n = len(mids)
  best_vp, best_score = None, -1.0
  rng = np.random.default_rng(0)
  for _ in range(400):
    i, j = rng.choice(n, size=2, replace=False)
    # intersection of two lines through mid along dir
    a, u = mids[i], dirs[i]
    b, v = mids[j], dirs[j]
    mat = np.array([u, -v], dtype=np.float64).T
    if abs(np.linalg.det(mat)) < 1e-6:
      continue
    t = np.linalg.solve(mat, b - a)
    vp = a + t[0] * u
    # score: how many lines point toward vp (weighted by length)
    to_vp = vp[None, :] - mids
    to_n = np.linalg.norm(to_vp, axis=1)
    ok = to_n > 20.0
    if ok.sum() < 3:
      continue
    to_u = to_vp[ok] / to_n[ok, None]
    # undirected alignment
    align = np.abs((to_u * dirs[ok]).sum(axis=1))
    score = float((align * lengths[ok]).sum())
    if score > best_score:
      best_score = score
      best_vp = vp
  if best_vp is None:
    return None
  return {
    "vp": best_vp,
    "score": best_score,
    "image_size": (w, h),
  }


def pitch_from_vp(vp, K, fallback=10.0):
  """Rough downward pitch (deg) from VP vertical location vs principal point."""
  fy = float(K[1, 1])
  cy = float(K[1, 2])
  # VP below principal point → looking down; angle ≈ atan((vp_y - cy)/fy)
  pitch = math.degrees(math.atan2(float(vp[1] - cy), fy))
  # Clamp to plausible mast-camera band
  if not (3.0 <= pitch <= 25.0):
    return fallback, False
  return float(pitch), True


def map_manhattan_angles(map_grid, n_peaks=2):
  """Dominant edge orientations (deg in [0,180)) from ortho structure gradients."""
  gx = cv2.Sobel(map_grid, cv2.CV_32F, 1, 0, ksize=3)
  gy = cv2.Sobel(map_grid, cv2.CV_32F, 0, 1, ksize=3)
  mag = np.sqrt(gx * gx + gy * gy)
  ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0  # edge normal → rotate
  # orientation of edge is normal + 90
  edge = (ang + 90.0) % 180.0
  strong = mag > np.percentile(mag, 70)
  if strong.sum() < 100:
    return [0.0, 90.0]
  hist, bins = np.histogram(edge[strong], bins=36, range=(0, 180), weights=mag[strong])
  # wrap-smooth
  hist = hist.astype(np.float64)
  hist = (hist + np.roll(hist, 1) + np.roll(hist, -1)) / 3.0
  peaks = []
  for _ in range(n_peaks):
    i = int(np.argmax(hist))
    peaks.append(float(bins[i] + 2.5))  # bin center approx
    # suppress neighborhood
    for k in range(-2, 3):
      hist[(i + k) % len(hist)] = 0.0
  # Ensure a roughly orthogonal pair if only one family dominates
  if len(peaks) == 1:
    peaks.append((peaks[0] + 90.0) % 180.0)
  return peaks


def camera_line_angles(frame):
  """Dominant undirected line angles (deg in [0,180)) in lower FOV."""
  h = frame.shape[0]
  gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  roi = gray[int(0.3 * h):, :]
  segs = _detect_lines(roi)
  if len(segs) < 4:
    return []
  _, dirs, lengths = _line_params(segs)
  ang = (np.degrees(np.arctan2(dirs[:, 1], dirs[:, 0])) + 180.0) % 180.0
  keep = lengths > 25.0
  ang, lengths = ang[keep], lengths[keep]
  if len(ang) < 4:
    return []
  hist, bins = np.histogram(ang, bins=36, range=(0, 180), weights=lengths)
  hist = hist.astype(np.float64)
  i = int(np.argmax(hist))
  return [float(bins[i] + 2.5)]


def yaw_candidates_from_manhattan(frame, map_grid, n_max=8):
  """Absolute world yaw candidates from camera lines × map Manhattan angles.

  Image line angle is not world yaw; we only use the pairing to generate the
  discrete set {θ, θ+90, θ+180, θ+270} for each map Manhattan family, then
  let local NCC choose. If camera lines are weak, return the four cardinal
  headings of the map's dominant edge family.
  """
  map_angs = map_manhattan_angles(map_grid)
  cam_angs = camera_line_angles(frame)
  # Base world headings: map edge directions and their opposites
  bases = []
  for a in map_angs:
    bases.extend([a % 360.0, (a + 180.0) % 360.0])
  # Also include orthogonal family explicitly
  for a in list(bases):
    bases.append((a + 90.0) % 360.0)
  # Dedup
  uniq = []
  for a in bases:
    if not any(abs(((a - u + 180) % 360) - 180) < 5.0 for u in uniq):
      uniq.append(a % 360.0)
  # Prefer candidates near camera-line-implied headings when available:
  # map angle ≈ camera line angle under orthographic assumption is weak;
  # keep all Manhattan candidates (typically ≤ 4).
  uniq = uniq[:n_max]
  if not uniq:
    uniq = [0.0, 90.0, 180.0, 270.0]
  return uniq, map_angs, cam_angs


def angle_diff_deg(a, b):
  return abs(((a - b + 180.0) % 360.0) - 180.0)


def local_yaw_hyps(yaw_centers, yaw_window, yaw_step, pitches, heights):
  hyps = []
  for yc in yaw_centers:
    for d in np.arange(-yaw_window, yaw_window + 0.01, yaw_step):
      yaw = (yc + d) % 360.0
      for pitch in pitches:
        for height in heights:
          hyps.append((float(yaw), float(pitch), float(height)))
  # Dedup near-identical
  out = []
  for h in hyps:
    if not any(
        angle_diff_deg(h[0], o[0]) < 0.5 and abs(h[1] - o[1]) < 0.5 and abs(h[2] - o[2]) < 0.25
        for o in out):
      out.append(h)
  return out


def predict_vp_for_road(K, yaw, pitch, height, road_angle_deg):
  """Image VP of horizontal world lines along road_angle, under look pose."""
  pose = pose_from_look(0.0, 0.0, float(height), float(yaw), float(pitch))
  r_cw = pose[:3, :3].T
  rad = math.radians(road_angle_deg)
  direction = np.array([math.cos(rad), math.sin(rad), 0.0], dtype=np.float64)
  d_cam = r_cw @ direction
  if d_cam[2] <= 1e-5:
    return None
  vp = K @ d_cam
  return vp[:2] / vp[2]


def vp_consistency(vp_det, K, yaw, pitch, height, map_angs, image_size, sigma_px=80.0):
  """Best match of detected VP to any map-road VP predicted under this pose."""
  if vp_det is None:
    return 0.5  # neutral when VP missing
  w, h = image_size
  best = 0.0
  for road in list(map_angs) + [a + 180.0 for a in map_angs]:
    pred = predict_vp_for_road(K, yaw, pitch, height, road)
    if pred is None:
      continue
    # Allow VP slightly outside the frame
    if pred[0] < -0.5 * w or pred[0] > 1.5 * w or pred[1] < -h or pred[1] > 2 * h:
      continue
    dist = float(np.linalg.norm(pred - vp_det))
    best = max(best, math.exp(-0.5 * (dist / sigma_px) ** 2))
  return best


def score_hypotheses(frame, K, dist, map_grid, ymax_m, res, hyps, vp_det, map_angs,
                     vp_weight=0.35):
  """Return candidates sorted by combined NCC × VP consistency."""
  h, w = frame.shape[:2]
  cands = []
  for yaw, pitch, height in hyps:
    pose0 = pose_from_look(0.0, 0.0, float(height), float(yaw), float(pitch))
    painted = structure_paint_bev(frame, pose0, K, dist, res)
    if painted is None:
      continue
    bev, cam_uv = painted
    hit = ncc_place_structure(bev, cam_uv, map_grid, ymax_m, res)
    if hit is None:
      continue
    vpc = vp_consistency(vp_det, K, yaw, pitch, height, map_angs, (w, h))
    ncc = float(hit["score"])
    # Combined: down-weight NCC when VP disagrees
    score = ncc * ((1.0 - vp_weight) + vp_weight * vpc)
    cands.append({
      "score": score,
      "ncc": ncc,
      "vp_consistency": vpc,
      "xy": hit["xy"],
      "yaw": yaw,
      "pitch": pitch,
      "height": height,
    })
  cands.sort(key=lambda c: c["score"], reverse=True)
  return cands


def confidence_gate(cands, ortho_gap=70.0, score_ratio=0.85):
  """True if we should ask for a click: top modes ~90° apart and close in score."""
  if not cands:
    return True, "no candidates", None, None
  best = cands[0]
  second = None
  for c in cands[1:]:
    if angle_diff_deg(c["yaw"], best["yaw"]) >= ortho_gap:
      second = c
      break
  if second is None:
    # Still gate if VP consistency is weak
    if best.get("vp_consistency", 1.0) < 0.25:
      return True, "weak VP consistency", best, None
    return False, "unique yaw mode", best, None
  ratio = second["score"] / max(best["score"], 1e-6)
  if ratio >= score_ratio:
    return True, f"ambiguous orthogonal yaws (score ratio {ratio:.2f})", best, second
  if best.get("vp_consistency", 1.0) < 0.25:
    return True, "weak VP consistency", best, second
  return False, f"best beats orthogonal rival (ratio {ratio:.2f})", best, second


def evaluate_camera(cam, frame, map_grid, ymax_m, args, out_dir):
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
    vp_xy = vp_info["vp"].tolist()
  else:
    pitch_est, pitch_ok = 10.0, False
    vp_xy = None

  yaw_cands, map_angs, cam_angs = yaw_candidates_from_manhattan(frame, map_grid)
  seed_yaw = None
  if args.seed_yaw is not None:
    seed_yaw = float(args.seed_yaw)
  elif args.seed_gt_yaw:
    # Stand-in for a human heading / click-derived yaw prior.
    seed_yaw = float(gt_yaw)
  if seed_yaw is not None:
    yaw_cands = [seed_yaw]
  pitches = [pitch_est]
  if seed_yaw is None:
    for d in (-2.0, 2.0, 4.0):
      p = pitch_est + d
      if 4.0 <= p <= 18.0:
        pitches.append(p)
  else:
    # Tight pitch band when heading is seeded — avoid NCC latching onto a
    # wrong pitch/height that outscores the true orientation.
    for d in (-2.0, 2.0):
      p = pitch_est + d
      if 4.0 <= p <= 18.0:
        pitches.append(p)
  heights = [5.0, 6.5, 8.0]
  window = args.yaw_window if seed_yaw is None else args.seed_yaw_window
  step = args.yaw_step if seed_yaw is None else min(args.yaw_step, 5.0)
  hyps = local_yaw_hyps(yaw_cands, window, step, pitches, heights)
  vp_det = None if vp_info is None else np.asarray(vp_info["vp"], dtype=np.float64)
  # With an external yaw seed, trust NCC placement; VP term is for disambiguation only.
  vw = 0.0 if seed_yaw is not None else args.vp_weight
  cands = score_hypotheses(
    frame, K, dist, map_grid, ymax_m, args.bev_res, hyps, vp_det, map_angs,
    vp_weight=vw)
  if seed_yaw is not None:
    # With an external yaw seed, skip the orthogonal-ambiguity click gate.
    needs_click, reason = False, "yaw seeded (click/heading prior)"
    best = cands[0] if cands else None
    second = None
  else:
    needs_click, reason, best, second = confidence_gate(
      cands, ortho_gap=args.ortho_gap, score_ratio=args.score_ratio)

  extra = {
    "vp": vp_xy,
    "pitch_est_deg": pitch_est,
    "pitch_from_vp": pitch_ok,
    "yaw_candidates_deg": yaw_cands,
    "map_manhattan_deg": map_angs,
    "cam_line_deg": cam_angs,
    "seed_yaw_deg": seed_yaw,
    "n_hyps": len(hyps),
    "n_cands": len(cands),
    "needs_click": needs_click,
    "confidence_reason": reason,
    "yaw_err_to_gt_deg": None if best is None else angle_diff_deg(best["yaw"], gt_yaw),
  }
  if second is not None:
    extra["second_yaw_deg"] = second["yaw"]
    extra["second_score"] = second["score"]
    extra["score_ratio"] = second["score"] / max(best["score"], 1e-6)

  if best is None:
    r = summarize(cam, None, gt_pose, extra)
    return r

  extra["ncc"] = best.get("ncc")
  extra["vp_consistency"] = best.get("vp_consistency")
  pose = pose_from_look(
    float(best["xy"][0]), float(best["xy"][1]), float(best["height"]),
    float(best["yaw"]), float(best["pitch"]))
  r = summarize(cam, pose, gt_pose, {
    **extra,
    "score": best["score"],
    "est_yaw_deg": best["yaw"],
    "est_pitch_deg": best["pitch"],
    "est_height_m": best["height"],
  })
  # High-confidence automatic success vs gated
  r["auto_accept"] = bool((not needs_click) and r.get("p2_signal"))
  # Overlay VP
  if vp_xy is not None:
    vis = frame.copy()
    cv2.circle(vis, (int(vp_xy[0]), int(vp_xy[1])), 8, (0, 0, 255), 2)
    cv2.putText(
      vis,
      f"yaw={best['yaw']:.0f} need_click={needs_click}",
      (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imwrite(str(out_dir / f"{cam['sensor_id']}_yaw_prior.png"), vis)
  return r


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument("--bev-res", type=float, default=0.4)
  ap.add_argument("--yaw-window", type=float, default=25.0)
  ap.add_argument("--yaw-step", type=float, default=5.0)
  ap.add_argument("--ortho-gap", type=float, default=70.0)
  ap.add_argument("--score-ratio", type=float, default=0.85,
                  help="needs_click if orthogonal rival score / best >= this.")
  ap.add_argument("--vp-weight", type=float, default=0.45,
                  help="Weight of VP consistency in the combined score.")
  ap.add_argument("--seed-gt-yaw", action="store_true",
                  help="Simulate click/heading prior using GT yaw (diagnostic).")
  ap.add_argument("--seed-yaw", type=float, default=None,
                  help="External yaw prior in degrees (world look heading).")
  ap.add_argument("--seed-yaw-window", type=float, default=20.0,
                  help="Local refine window when a yaw seed is provided.")
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
  map_grid, ymax_m = map_structure_grid(map_bgr, scale, args.bev_res)
  frames_dir = args.frames_dir or (Path(__file__).resolve().parent / "fixtures" / "videos")

  results = []
  for cam in cams:
    stem = SI_CAMERA_VIDEO.get(cam["sensor_id"])
    frame_path = frames_dir / f"{stem}.jpg" if stem else None
    if not frame_path or not frame_path.is_file():
      results.append({
        "sensor_id": cam["sensor_id"], "error": "missing frame",
        "p2_pass": False, "p2_signal": False, "needs_click": True})
      print(f"{cam['sensor_id']:8s}  MISSING_FRAME")
      continue
    frame = cv2.imread(str(frame_path))
    gt_pose, _, _ = solve_pose(
      cam["map_points"], cam["camera_points"],
      cam["intrinsics"], cam["distortion"])
    gt_yaw, _ = look_yaw_pitch(gt_pose)
    r = evaluate_camera(cam, frame, map_grid, ymax_m, args, args.out_dir)
    r["gt_yaw_deg"] = gt_yaw
    results.append(r)
    print(
      f"{r['sensor_id']:8s}  yaw={r.get('est_yaw_deg', float('nan')):6.1f}  "
      f"gt={gt_yaw:6.1f}  yaw_err={r.get('yaw_err_to_gt_deg', float('nan')):5.1f}  "
      f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
      f"dR={r.get('rotation_err_deg', float('nan')):6.1f}deg  "
      f"score={r.get('score', float('nan'))}  "
      f"need_click={r.get('needs_click')}  "
      f"auto={r.get('auto_accept')}  "
      f"signal={r.get('p2_signal')}  "
      f"({r.get('confidence_reason')})"
    )

  n_signal = sum(1 for c in results if c.get("p2_signal"))
  n_pass = sum(1 for c in results if c.get("p2_pass"))
  n_auto = sum(1 for c in results if c.get("auto_accept"))
  n_click = sum(1 for c in results if c.get("needs_click"))
  # Suite signal: either automatic signal on >=2 cams, or (signal OR gated click) covering >=3
  n_covered = sum(
    1 for c in results
    if c.get("p2_signal") or c.get("needs_click"))
  summary = {
    "scene": scene["name"],
    "source": "yaw prior (VP/Manhattan) + local BEV-NCC + confidence gate",
    "yaw_window": args.yaw_window,
    "yaw_step": args.yaw_step,
    "ortho_gap": args.ortho_gap,
    "score_ratio": args.score_ratio,
    "pass_bar": "dT<=1m and dR<=8deg on >=2 cameras",
    "signal_bar": "dT<=5m and dR<=20deg on >=2 cameras",
    "cameras": results,
    "p2_pass_count": n_pass,
    "p2_signal_count": n_signal,
    "auto_accept_count": n_auto,
    "needs_click_count": n_click,
    "covered_count": n_covered,
    "p2_pass": n_pass >= 2,
    "p2_signal": n_signal >= 2,
    "gate_ok": n_click + n_auto >= 3 or n_signal >= 2,
  }
  out_json = args.out_dir / "p2_yaw_prior_results.json"
  # numpy-safe json
  def _conv(o):
    if isinstance(o, np.generic):
      return o.item()
    if isinstance(o, np.ndarray):
      return o.tolist()
    raise TypeError(type(o))
  out_json.write_text(json.dumps(summary, indent=2, default=_conv))
  print(
    f"\np2_signal={summary['p2_signal']} ({n_signal}/{len(results)})  "
    f"auto_accept={n_auto}  needs_click={n_click}  "
    f"gate_ok={summary['gate_ok']}  wrote {out_json}"
  )
  return 0 if (summary["p2_signal"] or summary["gate_ok"]) else 1


if __name__ == "__main__":
  sys.exit(main())
