#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""V2 + OSM topology assist: does road/building layout break heading ambiguity?

Optional path for intersections where OSM has usable coverage. Not a product
default — campus/plaza scenes without OSM detail still need another cue.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

from osm_topology import load_scene_osm
from spike_common import (
  SI_CAMERA_VIDEO,
  camera_translation,
  image_resolution_from_intrinsics,
  load_smart_intersection,
  pose_from_look,
  rotation_angle_deg,
  solve_pose,
)
from v2_automatch import (
  look_yaw_pitch,
  overlay_map,
  paint_bev,
  match_xy,
  sample_structure_pixels,
  structure_image,
)


def search_on_target(uv, wts, target_grid, K, dist, ymax_m, res,
                     yaws, pitches, heights):
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
        hit = match_xy(bev, cam_uv, target_grid, ymax_m, res)
        if hit is None:
          continue
        score, cx, cy = hit
        if best is None or score > best["score"]:
          best = {
            "score": score, "yaw": float(yaw), "pitch": float(pitch),
            "height": float(height), "cx": cx, "cy": cy,
          }
  return best


def refine(pick, uv, wts, target_grid, K, dist, ymax_m, res):
  if pick is None:
    return None
  yaws = np.arange(pick["yaw"] - 8.0, pick["yaw"] + 8.1, 2.0) % 360.0
  pitches = np.arange(max(4.0, pick["pitch"] - 3.0), min(18.0, pick["pitch"] + 3.1), 1.0)
  heights = np.arange(max(3.5, pick["height"] - 1.0), min(12.0, pick["height"] + 1.1), 0.5)
  better = search_on_target(
    uv, wts, target_grid, K, dist, ymax_m, res, yaws, pitches, heights)
  if better is not None and better["score"] >= pick["score"]:
    return better
  return pick


def score_result(cam, pick, gt_pose, gt_t):
  if pick is None:
    return {
      "sensor_id": cam["sensor_id"], "error": "no alignment",
      "v2_pass": False, "v2_signal": False,
    }
  est_pose = pose_from_look(
    pick["cx"], pick["cy"], pick["height"], pick["yaw"], pick["pitch"], 0.0)
  est_t = camera_translation(est_pose)
  d_t = float(np.linalg.norm(est_t - gt_t))
  d_r = float(rotation_angle_deg(est_pose, gt_pose))
  return {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "score": pick["score"],
    "est_translation_m": est_t.tolist(),
    "est_yaw_deg": pick["yaw"],
    "est_pitch_deg": pick["pitch"],
    "est_height_m": pick["height"],
    "gt_translation_m": gt_t.tolist(),
    "translation_err_m": d_t,
    "xy_err_m": float(np.linalg.norm(est_t[:2] - gt_t[:2])),
    "z_err_m": float(abs(est_t[2] - gt_t[2])),
    "rotation_err_deg": d_r,
    "above_ground": bool(est_t[2] > 0),
    "v2_pass": bool(est_t[2] > 0 and d_t <= 1.0 and d_r <= 8.0),
    "v2_signal": bool(est_t[2] > 0 and d_t <= 5.0 and d_r <= 20.0),
  }


def run_mode(name, cams, frames_dir, target_grid, ymax_m, res, yaws, out_dir):
  pitches = np.arange(6.0, 15.1, 2.0)
  heights = np.array([5.0, 6.0, 7.0, 8.0])
  results = []
  for cam in cams:
    stem = SI_CAMERA_VIDEO.get(cam["sensor_id"])
    frame_path = frames_dir / f"{stem}.jpg"
    gt_pose, _, _ = solve_pose(
      cam["map_points"], cam["camera_points"],
      cam["intrinsics"], cam["distortion"])
    gt_t = camera_translation(gt_pose)
    if not frame_path.is_file():
      results.append({
        "sensor_id": cam["sensor_id"], "error": "missing frame",
        "v2_pass": False, "v2_signal": False})
      continue
    frame = cv2.imread(str(frame_path))
    w, h = image_resolution_from_intrinsics(cam["intrinsics"])
    if frame.shape[1] != w or frame.shape[0] != h:
      frame = cv2.resize(frame, (w, h))
    cam_struct = structure_image(frame, ground_bias=True)
    sampled = sample_structure_pixels(cam_struct)
    if sampled is None:
      results.append({
        "sensor_id": cam["sensor_id"], "error": "no structure",
        "v2_pass": False, "v2_signal": False})
      continue
    uv, wts = sampled
    pick = search_on_target(
      uv, wts, target_grid, cam["intrinsics"], cam["distortion"],
      ymax_m, res, yaws, pitches, heights)
    pick = refine(
      pick, uv, wts, target_grid, cam["intrinsics"], cam["distortion"],
      ymax_m, res)
    r = score_result(cam, pick, gt_pose, gt_t)
    results.append(r)
    if pick is not None:
      overlay_map(
        target_grid, ymax_m, res, gt_t,
        np.array(r["est_translation_m"]),
        f"{name} {cam['sensor_id']} dT={r['translation_err_m']:.1f}m "
        f"dR={r['rotation_err_deg']:.1f}",
        out_dir / f"{cam['sensor_id']}_v2_{name}_map.png")
    print(
      f"  {cam['sensor_id']:8s}  ncc={r.get('score', 0):.3f}  "
      f"dT={r.get('translation_err_m', float('nan')):6.2f}m  "
      f"dR={r.get('rotation_err_deg', float('nan')):6.1f}deg  "
      f"pass={r.get('v2_pass')}  signal={r.get('v2_signal')}"
    )
  n_pass = sum(1 for c in results if c.get("v2_pass"))
  n_signal = sum(1 for c in results if c.get("v2_signal"))
  return {
    "mode": name,
    "cameras": results,
    "v2_pass_count": n_pass,
    "v2_signal_count": n_signal,
    "v2_pass": n_pass >= 2,
    "v2_signal": n_signal >= 2,
  }


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--osm", type=Path, required=True,
                  help="OSM XML from api.openstreetmap.org map?bbox=...")
  ap.add_argument("--frames-dir", type=Path, default=None)
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument("--res", type=float, default=0.4)
  args = ap.parse_args()

  scene, cams = load_smart_intersection(args.fixture_dir)
  args.out_dir.mkdir(parents=True, exist_ok=True)
  map_bgr = cv2.imread(str(args.fixture_dir / scene["map"]))
  if map_bgr is None:
    raise SystemExit("failed to read map")
  scale = float(scene["scale"])
  h_px, w_px = map_bgr.shape[:2]
  ymax_m = h_px / scale

  osm = load_scene_osm(
    args.osm, scene["map_corners_lla"], w_px, h_px, scale, res=args.res)
  img_struct = structure_image(map_bgr)
  img_grid = cv2.resize(
    img_struct, (osm["grid"].shape[1], osm["grid"].shape[0]),
    interpolation=cv2.INTER_AREA)
  # Fuse: OSM topology dominates asymmetry; imagery adds paint texture.
  fused = np.clip(0.55 * osm["grid"] + 0.45 * img_grid, 0, 1)

  cv2.imwrite(str(args.out_dir / "v2_osm_roads.png"),
              (osm["grid"] * 255).astype(np.uint8))
  cv2.imwrite(str(args.out_dir / "v2_osm_fused.png"),
              (fused * 255).astype(np.uint8))

  frames_dir = args.frames_dir or (
    Path(__file__).resolve().parent / "fixtures" / "videos")

  print("OSM road headings (deg undirected -> length m):",
        [(round(a, 1), round(l, 1)) for a, l in osm["road_headings"][:6]])
  print("Yaw candidates from roads:", [round(y, 1) for y in osm["yaw_candidates"]])
  print(f"OSM ways: {len(osm['ways'])}  grid={osm['grid'].shape}")

  full_yaws = list(np.arange(0.0, 360.0, 10.0))
  road_yaws = osm["yaw_candidates"]

  modes = []
  print("\n[1] imagery-only, full yaw (baseline V2)")
  modes.append(run_mode(
    "imagery_full", cams, frames_dir, img_grid, ymax_m, args.res,
    full_yaws, args.out_dir))
  print("\n[2] OSM raster, road-aligned yaw")
  modes.append(run_mode(
    "osm_roads", cams, frames_dir, osm["grid"], ymax_m, args.res,
    road_yaws, args.out_dir))
  print("\n[3] fused imagery+OSM, road-aligned yaw")
  modes.append(run_mode(
    "fused_roads", cams, frames_dir, fused, ymax_m, args.res,
    road_yaws, args.out_dir))
  print("\n[4] fused imagery+OSM, full yaw")
  modes.append(run_mode(
    "fused_full", cams, frames_dir, fused, ymax_m, args.res,
    full_yaws, args.out_dir))

  summary = {
    "scene": scene["name"],
    "osm_file": str(args.osm),
    "road_headings_deg": [
      {"heading": a, "length_m": l} for a, l in osm["road_headings"]],
    "yaw_candidates": osm["yaw_candidates"],
    "modes": modes,
    "best_signal_mode": max(modes, key=lambda m: (m["v2_signal_count"], m["v2_pass_count"]))["mode"],
  }
  out_json = args.out_dir / "v2_osm_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print("\n=== summary ===")
  for m in modes:
    print(
      f"{m['mode']:16s}  pass={m['v2_pass_count']}/4  "
      f"signal={m['v2_signal_count']}/4  "
      f"gate_pass={m['v2_pass']}  gate_signal={m['v2_signal']}")
  print(f"wrote {out_json}")
  best = max(modes, key=lambda m: (m["v2_signal_count"], m["v2_pass_count"]))
  return 0 if best["v2_signal"] else 1


if __name__ == "__main__":
  sys.exit(main())
