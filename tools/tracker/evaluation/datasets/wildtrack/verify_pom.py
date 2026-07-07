#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Cross-check Wildtrack camera projection against ``rectangles.pom``.

``rectangles.pom`` lists, for every grid cell and every camera, the pixel
bounding box of a standing person projected with the dataset calibration.  This
script validates that our calibration parsing and grid decoding reproduce that
projection by projecting the ground (foot) point of sampled grid cells and
comparing it to the bottom-centre of the corresponding POM rectangle.

Two projection paths are checked, to validate both stages independently:

- ``raw``       – original world->camera ``rvec`` / ``tvec`` (centimetres),
                  exactly as POM was generated (validates XML + grid parsing).
- ``canonical`` – the derived camera->world extrinsics in metres from
                  ``scene_config.json`` (validates ``extrinsics_to_pose``).

Errors are reported as pixel distances; there is no hard pass/fail.

Usage::

    python -m datasets.wildtrack.verify_pom \
        --dataset-path /path/to/Wildtrack_dataset \
        --scene-config ../../../tests/system/metric/wildtrack_dataset/scene_config.json \
        --stride 4999 --max-per-camera 300
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import cv2
from scipy.spatial.transform import Rotation

from datasets.wildtrack import calibration as wt


def _raw_projector(dataset_path: Path) -> Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
  """Build per-view (K, rvec, tvec) using the raw calibration in centimetres."""
  projectors = {}
  for view_num, cam_name in enumerate(wt.WILDTRACK_CAMERA_NAMES):
    intrinsics, _ = wt.parse_intrinsics(
      wt.calibration_path(dataset_path, "intrinsic_zero", cam_name))
    fx, fy, cx, cy = intrinsics
    k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    rvec, tvec = wt.parse_extrinsics(
      wt.calibration_path(dataset_path, "extrinsic", cam_name))
    projectors[view_num] = (k, rvec, tvec)
  return projectors


def _canonical_projector(scene_config: dict) -> Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
  """Build per-view (K, rvec, tvec) from canonical metres extrinsics."""
  projectors = {}
  for view_num in range(wt.NUM_CAMERAS):
    sensor = scene_config["sensors"][wt.camera_id_for_view(view_num)]
    fx, fy, cx, cy = sensor["intrinsics"]
    k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    ext = sensor["extrinsics"]
    r_cw = Rotation.from_euler("XYZ", ext["rotation"], degrees=True).as_matrix()
    centre = np.array(ext["translation"], dtype=np.float64).reshape(3, 1)
    r_wc = r_cw.T
    t_wc = -r_wc @ centre
    rvec, _ = cv2.Rodrigues(r_wc)
    projectors[view_num] = (k, rvec, t_wc)
  return projectors


def _project_foot(position_id: int, view_num: int, in_metres: bool,
                  projector: Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]) -> np.ndarray:
  """Project the foot point of a grid cell to pixels for one camera."""
  x_m, y_m = wt.decode_position_id(position_id)
  scale = 1.0 if in_metres else wt.CM_PER_M
  point = np.array([[x_m * scale, y_m * scale, 0.0]], dtype=np.float64)
  k, rvec, tvec = projector[view_num]
  pixels, _ = cv2.projectPoints(point, rvec, tvec, k, None)
  return pixels.reshape(2)


def _iter_pom_samples(pom_path: Path, stride: int, max_per_camera: int):
  """Stream visible POM rectangles, sampling by positionID stride."""
  counts = {v: 0 for v in range(wt.NUM_CAMERAS)}
  with pom_path.open() as handle:
    for line in handle:
      if not line.startswith("RECTANGLE"):
        continue
      parts = line.split()
      if len(parts) < 4 or parts[3] == "notvisible":
        continue
      view_num = int(parts[1])
      position_id = int(parts[2])
      if position_id % stride != 0:
        continue
      if counts.get(view_num, max_per_camera) >= max_per_camera:
        continue
      xmin, ymin, xmax, ymax = (float(v) for v in parts[3:7])
      counts[view_num] += 1
      yield view_num, position_id, (xmin, ymin, xmax, ymax)
      if all(c >= max_per_camera for c in counts.values()):
        break


def verify(dataset_path: Path, scene_config: dict, stride: int,
           max_per_camera: int) -> Dict[str, Dict[str, float]]:
  """Compute per-camera foot-point pixel error vs POM for both projection paths."""
  raw_proj = _raw_projector(dataset_path)
  canon_proj = _canonical_projector(scene_config)

  errors: Dict[int, Dict[str, List[float]]] = {
    v: {"raw": [], "canonical": []} for v in range(wt.NUM_CAMERAS)
  }

  pom_path = dataset_path / "rectangles.pom"
  if not pom_path.exists():
    raise FileNotFoundError(f"POM file not found: {pom_path}")

  for view_num, position_id, (xmin, ymin, xmax, ymax) in _iter_pom_samples(
      pom_path, stride, max_per_camera):
    target = np.array([(xmin + xmax) / 2.0, ymax])
    raw_px = _project_foot(position_id, view_num, in_metres=False, projector=raw_proj)
    canon_px = _project_foot(position_id, view_num, in_metres=True, projector=canon_proj)
    errors[view_num]["raw"].append(float(np.linalg.norm(raw_px - target)))
    errors[view_num]["canonical"].append(float(np.linalg.norm(canon_px - target)))

  summary: Dict[str, Dict[str, float]] = {}
  for view_num in range(wt.NUM_CAMERAS):
    cam_id = wt.camera_id_for_view(view_num)
    entry: Dict[str, float] = {}
    for path_name in ("raw", "canonical"):
      values = errors[view_num][path_name]
      if values:
        entry[f"{path_name}_mean_px"] = float(np.mean(values))
        entry[f"{path_name}_median_px"] = float(np.median(values))
        entry[f"{path_name}_max_px"] = float(np.max(values))
      entry[f"{path_name}_samples"] = len(values)
    summary[cam_id] = entry
  return summary


def main(argv: Optional[List[str]] = None) -> int:
  """CLI entry point."""
  parser = argparse.ArgumentParser(description="Verify Wildtrack projection vs rectangles.pom.")
  parser.add_argument("--dataset-path", required=True, type=Path,
                      help="Path to the raw Wildtrack dataset root.")
  parser.add_argument("--scene-config", required=True, type=Path,
                      help="Path to the preprocessed scene_config.json.")
  parser.add_argument("--stride", type=int, default=4999,
                      help="positionID sampling stride (coprime-ish to grid width spreads samples).")
  parser.add_argument("--max-per-camera", type=int, default=300,
                      help="Maximum sampled rectangles per camera.")
  args = parser.parse_args(argv)

  scene_config = json.loads(args.scene_config.read_text())
  summary = verify(args.dataset_path, scene_config, args.stride, args.max_per_camera)

  print("Wildtrack POM projection cross-check (foot-point pixel error):")
  for cam_id, entry in summary.items():
    raw = entry.get("raw_mean_px")
    canon = entry.get("canonical_mean_px")
    raw_s = f"{raw:.2f}" if raw is not None else "n/a"
    canon_s = f"{canon:.2f}" if canon is not None else "n/a"
    print(f"  {cam_id}: raw_mean={raw_s}px  canonical_mean={canon_s}px  "
          f"samples={entry.get('raw_samples', 0)}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
