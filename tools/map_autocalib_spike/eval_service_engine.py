#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Evaluate the productized autocalibration geospatial engine on Smart Intersection.

Uses GT from manual correspondences (spike_common) only for scoring and for
simulated priors; the engine itself never sees GT unless --prior is set.

Example:
  .venv/bin/python eval_service_engine.py --fixture-dir /tmp/si-fixture \\
    --frames-dir fixtures/videos --prior none
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from spike_common import (
  SI_CAMERA_VIDEO, camera_translation, image_resolution_from_intrinsics,
  load_smart_intersection, rotation_angle_deg, solve_pose)
from p2_bev_match import look_yaw_pitch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "autocalibration" / "src"))
from geospatial_map_calibration import GeoMapPrior, GeospatialMapCalibration  # noqa: E402


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument("--prior", choices=("none", "point", "heading", "both"), default="none")
  ap.add_argument("--point-noise-m", type=float, default=5.0)
  ap.add_argument("--heading-noise-deg", type=float, default=10.0)
  args = ap.parse_args()

  scene, cams = load_smart_intersection(args.fixture_dir)
  engine = GeospatialMapCalibration.from_file(
    str(args.fixture_dir / scene["map"]), float(scene["scale"]))
  n_signal = n_pass = n_gated = 0
  for cam in cams:
    frame = cv2.imread(str(args.frames_dir / f"{SI_CAMERA_VIDEO[cam['sensor_id']]}.jpg"))
    K = cam["intrinsics"]
    w, h = image_resolution_from_intrinsics(K)
    frame = cv2.resize(frame, (w, h))
    gt_pose, _, _ = solve_pose(cam["map_points"], cam["camera_points"], K, cam["distortion"])
    gt_t = camera_translation(gt_pose)
    gt_yaw, _ = look_yaw_pitch(gt_pose)
    prior = None
    if args.prior != "none":
      prior = GeoMapPrior()
      if args.prior in ("point", "both"):
        prior.map_point = (gt_t[0] + args.point_noise_m, gt_t[1] - args.point_noise_m)
      if args.prior in ("heading", "both"):
        prior.heading_deg = (gt_yaw + args.heading_noise_deg) % 360.0
    t0 = time.time()
    r = engine.calibrate(frame, K, prior)
    dt = time.time() - t0
    if r["pose"] is None:
      print(f"{cam['sensor_id']}: no pose ({r['reason']}) {dt:.1f}s")
      continue
    d_t = float(np.linalg.norm(r["pose"][:3, 3] - gt_t))
    d_r = float(rotation_angle_deg(r["pose"], gt_pose))
    signal = d_t <= 5.0 and d_r <= 20.0
    n_signal += signal
    n_pass += d_t <= 1.0 and d_r <= 8.0
    n_gated += r["needs_prior"]
    print(f"{cam['sensor_id']}: yaw={r['yaw_deg']:.0f} gt={gt_yaw:.0f} dT={d_t:.2f}m dR={d_r:.1f}deg "
          f"score={r['score']:.3f} needs_prior={r['needs_prior']} signal={signal} "
          f"pts={len(r['calibration_points_2d'])} {dt:.1f}s ({r['reason']})")
  print(f"signal={n_signal}/{len(cams)} pass={n_pass}/{len(cams)} gated={n_gated}")


if __name__ == "__main__":
  main()
