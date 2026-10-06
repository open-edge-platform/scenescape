#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export the gate-passing rich-yaw poses as one Scenescape scene-import ZIP.

Builds a single scene from a p2_rich_yaw results JSON (estimated poses only),
plus an optional top-down overlay PNG (est vs GT for local debug).

Upload:
  python3 tools/upload_scenes/upload-scenes https://localhost/api/v1 \\
    out/ui_scenes --restauth admin:PASSWORD --insecure

Example:
  .venv-roma/bin/python export_ui_scene.py \\
    --fixture-dir /tmp/smart-intersection-v0 \\
    --poses out/p2_rich_yaw_search_results.json \\
    --out-dir out/ui_scenes --scene-name SI-AutoCalib
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
import zipfile
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from spike_common import (
  camera_translation,
  image_resolution_from_intrinsics,
  load_smart_intersection,
  map_metres_to_pixels,
  pose_from_look,
  solve_pose,
)
from p2_bev_match import look_yaw_pitch


def pose_to_euler(pose_mat):
  """Match scene_common CameraPose._poseMatToPose (XYZ degrees + translation)."""
  rmat = pose_mat[:3, :3]
  t = pose_mat[:3, 3]
  euler = Rotation.from_matrix(rmat).as_euler("XYZ", degrees=True)
  return t.astype(float).tolist(), euler.astype(float).tolist()


def cam_export(uid, name, K, dist, translation, rotation, resolution, scene_uid,
               command):
  w, h = resolution
  return {
    "uid": uid,
    "name": name,
    "intrinsics": {
      "fx": float(K[0, 0]), "fy": float(K[1, 1]),
      "cx": float(K[0, 2]), "cy": float(K[1, 2]),
    },
    "distortion": {
      "k1": float(dist[0]), "k2": float(dist[1]),
      "p1": float(dist[2]), "p2": float(dist[3]), "k3": float(dist[4]),
    },
    "transform_type": "euler",
    "transforms": list(translation) + list(rotation) + [1.0, 1.0, 1.0],
    "translation": list(translation),
    "rotation": list(rotation),
    "scale": [1.0, 1.0, 1.0],
    "resolution": [int(w), int(h)],
    "scene": scene_uid,
    "cv_subsystem": "AUTO",
    "undistort": False,
    "modelconfig": "model_config.json",
    "use_camera_pipeline": False,
    "command": command,
    "camerachain": "passthrough=CPU",
  }


def write_scene_zip(out_dir: Path, scene_name: str, scene_json: dict, map_path: Path):
  """Import matcher requires the map filename to contain the scene name."""
  scene_dir = out_dir / scene_name
  scene_dir.mkdir(parents=True, exist_ok=True)
  map_name = f"{scene_name}{Path(map_path).suffix or '.jpg'}"
  scene_json["map"] = map_name
  scene_json["name"] = scene_name
  dest_map = scene_dir / map_name
  dest_map.write_bytes(map_path.read_bytes())
  json_path = scene_dir / f"{scene_name}.json"
  json_path.write_text(json.dumps(scene_json, indent=2))
  zip_path = scene_dir / f"{scene_name}.zip"
  with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.write(json_path, arcname=f"{scene_name}.json")
    zf.write(dest_map, arcname=map_name)
  return zip_path


def draw_overlay(map_bgr, scale, cams_gt, cams_est, out_path: Path):
  """Top-down: GT green, est red; look ray ~25 m (local debug only)."""
  vis = map_bgr.copy()
  map_h = map_bgr.shape[0]
  arrow_m = 25.0

  def draw_one(pose, color, label):
    t = camera_translation(pose)
    yaw, _ = look_yaw_pitch(pose)
    tip = t[:2] + arrow_m * np.array([
      math.cos(math.radians(yaw)), math.sin(math.radians(yaw))])
    pts = map_metres_to_pixels(np.stack([t[:2], tip]), scale, map_h)
    p0 = tuple(np.round(pts[0]).astype(int))
    p1 = tuple(np.round(pts[1]).astype(int))
    cv2.arrowedLine(vis, p0, p1, color, 3, tipLength=0.15)
    cv2.circle(vis, p0, 8, color, -1)
    cv2.putText(vis, label, (p0[0] + 10, p0[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

  for sid, pose in cams_gt.items():
    draw_one(pose, (0, 200, 0), f"{sid}_gt")
  for sid, pose in cams_est.items():
    draw_one(pose, (0, 0, 255), sid)
  cv2.putText(vis, "green=GT  red=rich-yaw est", (20, 40),
              cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
  cv2.imwrite(str(out_path), vis)
  return out_path


def main():
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--fixture-dir", type=Path, required=True)
  ap.add_argument("--poses", type=Path, required=True,
                  help="Gate-passing rich-yaw JSON (cameras[].est_*)")
  ap.add_argument("--out-dir", type=Path, default=Path("out/ui_scenes"))
  ap.add_argument("--scene-name", type=str, default="SmartIntersection",
                  help="Single scene name / zip basename")
  ap.add_argument("--overlay", action="store_true",
                  help="Also write poses_overlay.png (GT vs est)")
  args = ap.parse_args()

  scene_fields, cams = load_smart_intersection(args.fixture_dir)
  map_path = args.fixture_dir / scene_fields["map"]
  if not map_path.is_file():
    raise SystemExit(f"missing map {map_path}")
  map_bgr = cv2.imread(str(map_path))
  scale = float(scene_fields["scale"])
  poses_doc = json.loads(args.poses.read_text())
  est_by_id = {
    c["sensor_id"]: c for c in poses_doc["cameras"] if "est_translation_m" in c
  }

  scene_uid = str(uuid.uuid4())
  est_cams_export = []
  gt_poses, est_poses = {}, {}

  for cam in cams:
    sid = cam["sensor_id"]
    K, dist = cam["intrinsics"], cam["distortion"]
    # SI scene dump stores width/height as 640x480, but videos + intrinsics
    # (cx=640, cy=360) are 1280x720 — match the real SI media, not the dump.
    w, h = image_resolution_from_intrinsics(K, fallback=(1280, 720))
    gt_pose, _, _ = solve_pose(cam["map_points"], cam["camera_points"], K, dist)
    gt_poses[sid] = gt_pose

    est = est_by_id.get(sid)
    if est is None:
      print(f"WARNING: no estimate for {sid}; skip")
      continue
    est_pose = pose_from_look(
      float(est["est_translation_m"][0]),
      float(est["est_translation_m"][1]),
      float(est["est_translation_m"][2]),
      float(est["est_yaw_deg"]),
      float(est.get("est_pitch_deg", look_yaw_pitch(gt_pose)[1])),
    )
    est_poses[sid] = est_pose
    et, ee = pose_to_euler(est_pose)
    label = cam.get("name") or sid
    # Stable ids: si-cameraN RTSP paths from si_video_compose.yaml
    est_cams_export.append(cam_export(
      f"si_{sid}", f"SI {label}", K, dist, et, ee, (w, h), scene_uid,
      command=f"rtsp://mediaserver:8554/si-{sid}"))
    print(
      f"{sid}: est yaw={est['est_yaw_deg']:.1f} "
      f"err={est.get('yaw_err_to_gt_deg')} dxy={est.get('xy_err_m')}"
    )

  scene_json = {
    "uid": scene_uid,
    "name": args.scene_name,
    "map_type": "map_upload",
    "use_tracker": False,
    "output_lla": False,
    "map": map_path.name,
    "cameras": est_cams_export,
    "mesh_translation": [0, 0, 0],
    "mesh_rotation": [0, 0, 0],
    "mesh_scale": [1, 1, 1],
    "scale": scale,
    "regulated_rate": 30,
    "external_update_rate": 30,
    "camera_calibration": "Manual",
  }

  args.out_dir.mkdir(parents=True, exist_ok=True)
  # Drop prior multi-stage exports so upload-scenes only sees this scene.
  for child in list(args.out_dir.iterdir()):
    if child.is_dir() and child.name != args.scene_name:
      for f in child.iterdir():
        f.unlink()
      child.rmdir()

  zpath = write_scene_zip(args.out_dir, args.scene_name, scene_json, map_path)
  print(f"\nWrote {zpath}")
  if args.overlay:
    overlay = draw_overlay(
      map_bgr, scale, gt_poses, est_poses, args.out_dir / "poses_overlay.png")
    print(f"Wrote {overlay}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
