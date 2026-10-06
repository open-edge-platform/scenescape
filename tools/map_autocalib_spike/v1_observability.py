#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""V1 observability: imagery-derived landmarks under GT pose (no OSM).

Extracts static structure from the ortho map tile (bright markings, edges,
paved-vs-vegetation boundaries), projects into each camera with the V0 GT
pose, and scores depth / lateral coverage. Camera-frame edges are extracted
only for overlay comparison — not for matching (that is V2).
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
  map_metres_to_pixels,
  map_pixels_to_metres,
  project_world_to_image,
  solve_pose,
)


def extract_map_landmarks(map_bgr, max_points=2500, stride=2):
  """Imagery-only landmarks from an ortho tile. Returns pixel xy + labels.

  Classes (no OSM):
    marking  — bright linear / blotch structure (top-hat on Lab L)
    edge     — Canny edges on luminance
    boundary — paved vs vegetation / soil (ExG + Lab a*)
  """
  h, w = map_bgr.shape[:2]
  lab = cv2.cvtColor(map_bgr, cv2.COLOR_BGR2LAB)
  L, a, b = cv2.split(lab)
  rgb = cv2.cvtColor(map_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
  R, G, B = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
  # Excess green (vegetation proxy); paved / asphalt tends low.
  exg = 2.0 * G - R - B
  vegetated = exg > np.percentile(exg, 70)

  # Bright markings: white paint on dark pavement.
  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
  tophat = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, kernel)
  marking = tophat > max(40, int(np.percentile(tophat, 97)))
  marking = cv2.morphologyEx(
    marking.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

  # Edges on L, suppressed in heavy vegetation (keep building / curb edges).
  blur = cv2.GaussianBlur(L, (5, 5), 0)
  edges = cv2.Canny(blur, 60, 140)
  edges[vegetated] = 0

  # Boundary: gradient of vegetation mask (paved↔veg / soil).
  veg_u8 = vegetated.astype(np.uint8) * 255
  boundary = cv2.Canny(veg_u8, 50, 150)

  # Prefer ground-ish pixels: not the strongest vegetation.
  ground = ~vegetated | (marking > 0)

  masks = {
    "marking": (marking > 0) & ground,
    "edge": (edges > 0) & ground,
    "boundary": (boundary > 0),
  }

  points = []
  labels = []
  for label, mask in masks.items():
    ys, xs = np.where(mask)
    if len(xs) == 0:
      continue
    # Stride subsample then random cap for determinism via fixed seed.
    idx = np.arange(0, len(xs), stride)
    xs, ys = xs[idx], ys[idx]
    if len(xs) > max_points // 3:
      rng = np.random.default_rng(0)
      pick = rng.choice(len(xs), size=max_points // 3, replace=False)
      xs, ys = xs[pick], ys[pick]
    pts = np.stack([xs.astype(np.float64), ys.astype(np.float64)], axis=1)
    points.append(pts)
    labels.extend([label] * len(pts))

  if not points:
    return np.zeros((0, 2)), [], {
      "marking_mask": marking,
      "edge_mask": edges,
      "boundary_mask": boundary,
      "ground_mask": ground.astype(np.uint8) * 255,
    }

  return np.vstack(points), labels, {
    "marking_mask": marking,
    "edge_mask": edges,
    "boundary_mask": boundary,
    "ground_mask": ground.astype(np.uint8) * 255,
  }


def extract_camera_edges(frame_bgr, max_points=2000):
  """Camera-frame edge samples for overlay only (not matching)."""
  gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
  blur = cv2.GaussianBlur(gray, (5, 5), 0)
  edges = cv2.Canny(blur, 50, 120)
  # Focus on lower 70% of frame (ground-dominant for traffic cams).
  h = edges.shape[0]
  edges[: int(0.3 * h), :] = 0
  ys, xs = np.where(edges > 0)
  if len(xs) == 0:
    return np.zeros((0, 2)), edges
  idx = np.arange(0, len(xs), 3)
  xs, ys = xs[idx], ys[idx]
  if len(xs) > max_points:
    rng = np.random.default_rng(1)
    pick = rng.choice(len(xs), size=max_points, replace=False)
    xs, ys = xs[pick], ys[pick]
  return np.stack([xs, ys], axis=1).astype(np.float64), edges


def points_in_fov(uv, width, height, margin=2):
  u, v = uv[:, 0], uv[:, 1]
  return (
    (u >= margin) & (u < width - margin) &
    (v >= margin) & (v < height - margin)
  )


def in_front_of_camera(map_xyz, rvec, tvec):
  """True when world points are in front of the camera (positive depth)."""
  rmat, _ = cv2.Rodrigues(rvec)
  # camera frame: X_c = R * X_w + t
  cam = (rmat @ map_xyz.T) + tvec.reshape(3, 1)
  return cam[2] > 0.5  # metres in front


def coverage_metrics(map_xyz, uv, cam_xyz, width, height):
  """Depth / lateral / FOV occupancy for landmarks visible in the camera."""
  if len(map_xyz) == 0:
    return {
      "n_visible": 0,
      "depth_min_m": None,
      "depth_max_m": None,
      "depth_span_m": 0.0,
      "lateral_span_m": 0.0,
      "pca_ratio": 0.0,
      "fov_u_frac": 0.0,
      "fov_v_frac": 0.0,
      "grid_cells_hit": 0,
      "grid_cells_total": 16,
    }

  # Depth along horizontal distance from camera XY.
  dxy = map_xyz[:, :2] - cam_xyz[:2]
  depth = np.linalg.norm(dxy, axis=1)
  # Lateral: signed distance perpendicular to mean look direction in XY.
  if len(dxy) >= 2:
    mean_dir = dxy.mean(axis=0)
    n = np.linalg.norm(mean_dir)
    if n > 1e-6:
      mean_dir = mean_dir / n
      perp = np.array([-mean_dir[1], mean_dir[0]])
      lateral = dxy @ perp
    else:
      lateral = dxy[:, 0]
  else:
    lateral = np.zeros(len(dxy))

  xy = map_xyz[:, :2] - map_xyz[:, :2].mean(axis=0)
  if len(xy) >= 2:
    _, s, _ = np.linalg.svd(xy, full_matrices=False)
    pca_ratio = float(s[1] / s[0]) if s[0] > 1e-9 else 0.0
  else:
    pca_ratio = 0.0

  # 4x4 FOV occupancy grid.
  gu = np.clip((uv[:, 0] / width * 4).astype(int), 0, 3)
  gv = np.clip((uv[:, 1] / height * 4).astype(int), 0, 3)
  cells = set(zip(gu.tolist(), gv.tolist()))

  return {
    "n_visible": int(len(map_xyz)),
    "depth_min_m": float(np.min(depth)),
    "depth_max_m": float(np.max(depth)),
    "depth_span_m": float(np.max(depth) - np.min(depth)),
    "lateral_span_m": float(np.max(lateral) - np.min(lateral)) if len(lateral) else 0.0,
    "pca_ratio": pca_ratio,
    "fov_u_frac": float((np.max(uv[:, 0]) - np.min(uv[:, 0])) / width),
    "fov_v_frac": float((np.max(uv[:, 1]) - np.min(uv[:, 1])) / height),
    "grid_cells_hit": int(len(cells)),
    "grid_cells_total": 16,
  }


def evaluate_camera(cam, map_xyz, map_labels, frame_path, out_dir):
  K = cam["intrinsics"]
  dist = cam["distortion"]
  pose, rvec, tvec = solve_pose(
    cam["map_points"], cam["camera_points"], K, dist)
  cam_xyz = camera_translation(pose)
  width, height = image_resolution_from_intrinsics(K)

  front = in_front_of_camera(map_xyz, rvec, tvec)
  uv_all = project_world_to_image(map_xyz, rvec, tvec, K, dist)
  in_img = points_in_fov(uv_all, width, height) & front
  vis_xyz = map_xyz[in_img]
  vis_uv = uv_all[in_img]
  vis_labels = [map_labels[i] for i, keep in enumerate(in_img) if keep]

  metrics = coverage_metrics(vis_xyz, vis_uv, cam_xyz, width, height)
  by_class = {}
  for lab in ("marking", "edge", "boundary"):
    by_class[lab] = int(sum(1 for x in vis_labels if x == lab))
  metrics["by_class"] = by_class

  # Pass heuristics for V1 (imagery structure visible and well spread).
  metrics["v1_pass"] = bool(
    metrics["n_visible"] >= 80
    and metrics["depth_span_m"] >= 15.0
    and metrics["lateral_span_m"] >= 8.0
    and metrics["pca_ratio"] >= 0.15
    and metrics["grid_cells_hit"] >= 6
  )

  # Overlays
  if frame_path and frame_path.is_file():
    frame = cv2.imread(str(frame_path))
    if frame is not None:
      if frame.shape[1] != width or frame.shape[0] != height:
        frame = cv2.resize(frame, (width, height))
      cam_edges, _ = extract_camera_edges(frame)
      overlay = frame.copy()
      for (u, v) in cam_edges.astype(int):
        if 0 <= u < width and 0 <= v < height:
          overlay[v, u] = (80, 80, 80)
      colors = {"marking": (0, 255, 255), "edge": (0, 255, 0), "boundary": (255, 128, 0)}
      for (u, v), lab in zip(vis_uv, vis_labels):
        cv2.circle(overlay, (int(u), int(v)), 2, colors.get(lab, (255, 255, 255)), -1)
      cv2.putText(
        overlay,
        f"{cam['sensor_id']} n={metrics['n_visible']} "
        f"depth={metrics['depth_span_m']:.0f}m "
        f"lat={metrics['lateral_span_m']:.0f}m "
        f"pass={metrics['v1_pass']}",
        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
      cv2.imwrite(str(out_dir / f"{cam['sensor_id']}_v1_cam.png"), overlay)

  return {
    "sensor_id": cam["sensor_id"],
    "name": cam["name"],
    "gt_translation_m": cam_xyz.tolist(),
    "image_size": [width, height],
    **metrics,
  }


def save_map_landmark_overlay(map_bgr, pix, labels, scale, cams, out_path):
  img = map_bgr.copy()
  colors = {"marking": (0, 255, 255), "edge": (0, 180, 0), "boundary": (0, 128, 255)}
  for (x, y), lab in zip(pix.astype(int), labels):
    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
      img[y, x] = colors.get(lab, (255, 255, 255))
  h = img.shape[0]
  for cam in cams:
    pose, _, _ = solve_pose(
      cam["map_points"], cam["camera_points"],
      cam["intrinsics"], cam["distortion"])
    t = camera_translation(pose)
    p = map_metres_to_pixels(t[:2][None, :], scale, h)[0]
    cv2.drawMarker(
      img, (int(p[0]), int(p[1])), (0, 0, 255),
      markerType=cv2.MARKER_TILTED_CROSS, markerSize=16, thickness=2)
    cv2.putText(
      img, cam["sensor_id"], (int(p[0]) + 6, int(p[1]) - 6),
      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
  cv2.imwrite(str(out_path), img)


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument(
    "--frames-dir",
    type=Path,
    default=None,
    help="Directory with 1122*_h264.jpg stills (from download_si_videos.sh)",
  )
  ap.add_argument("--out-dir", type=Path, default=Path("out"))
  ap.add_argument("--max-points", type=int, default=2500)
  args = ap.parse_args()

  scene, cams = load_smart_intersection(args.fixture_dir)
  args.out_dir.mkdir(parents=True, exist_ok=True)
  map_path = args.fixture_dir / scene["map"]
  map_bgr = cv2.imread(str(map_path))
  if map_bgr is None:
    raise SystemExit(f"failed to read map {map_path}")
  scale = float(scene["scale"])
  map_h = map_bgr.shape[0]

  pix, labels, masks = extract_map_landmarks(map_bgr, max_points=args.max_points)
  metres_xy = map_pixels_to_metres(pix, scale, map_h)
  map_xyz = np.hstack([metres_xy, np.zeros((len(metres_xy), 1))])

  cv2.imwrite(str(args.out_dir / "v1_ground_mask.png"), masks["ground_mask"])
  cv2.imwrite(str(args.out_dir / "v1_marking_mask.png"), masks["marking_mask"])
  save_map_landmark_overlay(
    map_bgr, pix, labels, scale, cams, args.out_dir / "v1_map_landmarks.png")

  frames_dir = args.frames_dir
  if frames_dir is None:
    frames_dir = Path(__file__).resolve().parent / "fixtures" / "videos"

  results = []
  for cam in cams:
    stem = SI_CAMERA_VIDEO.get(cam["sensor_id"])
    frame_path = frames_dir / f"{stem}.jpg" if stem else None
    r = evaluate_camera(cam, map_xyz, labels, frame_path, args.out_dir)
    results.append(r)
    print(
      f"{r['sensor_id']:8s}  n={r['n_visible']:4d}  "
      f"depth={r['depth_span_m']:6.1f}m  "
      f"lat={r['lateral_span_m']:6.1f}m  "
      f"pca={r['pca_ratio']:.2f}  "
      f"grid={r['grid_cells_hit']}/{r['grid_cells_total']}  "
      f"mark={r['by_class'].get('marking', 0)} "
      f"edge={r['by_class'].get('edge', 0)} "
      f"bnd={r['by_class'].get('boundary', 0)}  "
      f"pass={r['v1_pass']}"
    )

  class_counts = {k: int(labels.count(k)) for k in ("marking", "edge", "boundary")}
  summary = {
    "scene": scene["name"],
    "scale_px_per_m": scale,
    "map_landmark_total": len(labels),
    "map_landmark_by_class": class_counts,
    "source": "ortho imagery only (no OSM)",
    "cameras": results,
    "v1_pass": all(c["v1_pass"] for c in results),
    "v1_pass_count": sum(1 for c in results if c["v1_pass"]),
  }
  out_json = args.out_dir / "v1_results.json"
  out_json.write_text(json.dumps(summary, indent=2))
  print(
    f"\nmap_landmarks={len(labels)} {class_counts}  "
    f"v1_pass={summary['v1_pass']} ({summary['v1_pass_count']}/{len(results)})  "
    f"wrote {out_json}"
  )
  return 0 if summary["v1_pass"] else 1


if __name__ == "__main__":
  sys.exit(main())
