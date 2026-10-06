#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for map-autocalib verification spikes (V0–V2)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

POINT_CORRESPONDENCE = "3d-2d point correspondence"

# Smart Intersection sensor_id -> sample video stem
SI_CAMERA_VIDEO = {
  "camera1": "1122south_h264",
  "camera2": "1122west_h264",
  "camera3": "1122north_h264",
  "camera4": "1122east_h264",
}


def parse_transforms(array, transform_type):
  """Mirror scene_common.transform.CameraPose.arrayToDictionary for 3d-2d."""
  if transform_type != POINT_CORRESPONDENCE:
    raise ValueError(f"unsupported transform_type: {transform_type}")
  if isinstance(array, str):
    array = json.loads(array)
  array = list(array)
  if len(array) % 5 == 0:
    split = (len(array) // 5) * 2
    cam = np.asarray(array[:split], dtype=np.float64).reshape(-1, 2)
    maps = np.asarray(array[split:], dtype=np.float64).reshape(-1, 3)
  elif len(array) % 4 == 0:
    split = len(array) // 2
    cam = np.asarray(array[:split], dtype=np.float64).reshape(-1, 2)
    maps = np.asarray(array[split:], dtype=np.float64).reshape(-1, 2)
    maps = np.hstack([maps, np.zeros((maps.shape[0], 1))])
  else:
    raise ValueError(f"invalid transforms length {len(array)}")
  return cam, maps


def load_smart_intersection(fixture_dir: Path):
  data = json.loads((fixture_dir / "data.json").read_text())
  scene = next(x for x in data if x["model"] == "manager.scene")
  sensors = {x["pk"]: x["fields"] for x in data if x["model"] == "manager.sensor"}
  cams = []
  for x in data:
    if x["model"] != "manager.cam":
      continue
    fields = x["fields"]
    transforms = fields["transforms"]
    if isinstance(transforms, str):
      transforms = json.loads(transforms)
    cam_pts, map_pts = parse_transforms(transforms, fields["transform_type"])
    sensor = sensors.get(x["pk"], {})
    cams.append({
      "pk": x["pk"],
      "sensor_id": sensor.get("sensor_id", f"cam-{x['pk']}"),
      "name": sensor.get("name", ""),
      "camera_points": cam_pts,
      "map_points": map_pts,
      "intrinsics": np.array([
        [fields["intrinsics_fx"], 0.0, fields["intrinsics_cx"]],
        [0.0, fields["intrinsics_fy"], fields["intrinsics_cy"]],
        [0.0, 0.0, 1.0],
      ], dtype=np.float64),
      "distortion": np.array([
        fields["distortion_k1"], fields["distortion_k2"],
        fields["distortion_p1"], fields["distortion_p2"],
        fields["distortion_k3"],
      ], dtype=np.float64),
      "width": int(fields.get("width") or 0) or None,
      "height": int(fields.get("height") or 0) or None,
    })
  return scene["fields"], cams


def solve_pose(map_pts, cam_pts, K, dist):
  """World-from-camera pose matrix via solvePnP."""
  ok, rvec, tvec = cv2.solvePnP(
    map_pts.astype(np.float32),
    cam_pts.astype(np.float32),
    K,
    dist,
    flags=cv2.SOLVEPNP_ITERATIVE,
  )
  if not ok:
    raise RuntimeError("solvePnP failed")
  rmat, _ = cv2.Rodrigues(rvec)
  cam_from_world = np.vstack([np.hstack([rmat, tvec]), [0, 0, 0, 1]])
  world_from_cam = np.linalg.inv(cam_from_world)
  return world_from_cam, rvec, tvec


def camera_translation(pose_mat):
  return pose_mat[:3, 3].copy()


def project_world_to_image(map_pts, rvec, tvec, K, dist):
  img, _ = cv2.projectPoints(
    map_pts.astype(np.float32), rvec, tvec, K, dist)
  return img.reshape(-1, 2)


def map_metres_to_pixels(map_pts_xy, scale, map_h):
  # SceneScape: x = px / S, y = (H - py) / S  =>  px = x*S, py = H - y*S
  px = map_pts_xy[:, 0] * scale
  py = map_h - map_pts_xy[:, 1] * scale
  return np.stack([px, py], axis=1)


def map_pixels_to_metres(pix_xy, scale, map_h):
  x = pix_xy[:, 0] / scale
  y = (map_h - pix_xy[:, 1]) / scale
  return np.stack([x, y], axis=1)


def image_resolution_from_intrinsics(K, fallback=(1280, 720)):
  cx, cy = float(K[0, 2]), float(K[1, 2])
  w, h = int(round(cx * 2)), int(round(cy * 2))
  if w < 64 or h < 64:
    return fallback
  return w, h


def rotation_angle_deg(pose_a, pose_b):
  """Geodesic angle between two 4x4 (or 3x3) rotations, in degrees."""
  Ra = pose_a[:3, :3]
  Rb = pose_b[:3, :3]
  rel = Ra.T @ Rb
  cos_theta = np.clip((np.trace(rel) - 1.0) / 2.0, -1.0, 1.0)
  return math.degrees(math.acos(cos_theta))


def pose_from_look(cx, cy, height, yaw_deg, pitch_deg, roll_deg=0.0):
  """World-from-camera pose: z-up world, OpenCV camera (x right, y down, z forward).

  yaw_deg: heading of the optical-axis ground projection, 0 along +X, CCW.
  pitch_deg: downward tilt from horizontal (positive looks at the ground).
  roll_deg: rotation about the optical axis.
  height: camera Z, must be > 0.
  """
  if height <= 0:
    raise ValueError("camera height must be above ground (z > 0)")
  yaw = math.radians(yaw_deg)
  pitch = math.radians(pitch_deg)
  roll = math.radians(roll_deg)
  look = np.array([
    math.cos(pitch) * math.cos(yaw),
    math.cos(pitch) * math.sin(yaw),
    -math.sin(pitch),
  ], dtype=np.float64)
  world_up = np.array([0.0, 0.0, 1.0])
  right = np.cross(look, world_up)
  n = np.linalg.norm(right)
  if n < 1e-8:
    right = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
    n = np.linalg.norm(right)
  right = right / n
  down = np.cross(look, right)
  down = down / np.linalg.norm(down)
  if abs(roll) > 1e-9:
    c, s = math.cos(roll), math.sin(roll)
    right, down = (c * right + s * down), (-s * right + c * down)
  r_wc = np.column_stack([right, down, look])
  pose = np.eye(4, dtype=np.float64)
  pose[:3, :3] = r_wc
  pose[:3, 3] = [cx, cy, height]
  return pose


def ray_to_ground(pose_mat, K, dist, cam_pts):
  """Intersect camera rays with z=0. Returns Nx3 world points (nan if invalid)."""
  pts = np.asarray(cam_pts, dtype=np.float32).reshape(-1, 1, 2)
  und = cv2.undistortPoints(pts, K, dist).reshape(-1, 2)
  origin = pose_mat[:3, 3]
  dirs = (pose_mat[:3, :3] @ np.column_stack([und, np.ones(len(und))]).T).T
  out = np.full((len(und), 3), np.nan)
  dz = dirs[:, 2]
  valid = np.abs(dz) >= 1e-9
  t = np.full(len(und), np.nan)
  t[valid] = -origin[2] / dz[valid]
  valid &= t > 0.3
  out[valid] = origin + t[valid, None] * dirs[valid]
  return out


def image_from_ground_homography(pose_mat, K):
  """3x3 homography mapping ground metres [x, y, 1] to image pixels."""
  cam_from_world = np.linalg.inv(pose_mat)
  r_cw = cam_from_world[:3, :3]
  t_cw = cam_from_world[:3, 3]
  return K @ np.column_stack([r_cw[:, 0], r_cw[:, 1], t_cw])
