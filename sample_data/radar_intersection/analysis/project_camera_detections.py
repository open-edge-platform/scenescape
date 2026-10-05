#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Project camera detections onto the scene ground plane and radar-local frame.

Reads JSONL from ``detect_camera_frames.py`` (or equivalent) and a scene
``RadarIntersection.json``. Outputs a JSON list of
``{frame_index, label, conf, scene, radar_local, px}`` for person and vehicle
(and cyclist) detections.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

_RI_ROOT = Path(__file__).resolve().parents[1]

# Prefer scene_common when available (scene container / host venv).
try:
  from scene_common.geometry import Line, Point, Rectangle
  from scene_common.transform import CameraPose
  from scene_common.camera import Camera
  _HAS_SC = True
except ImportError:  # pragma: no cover - host without scene_common
  _HAS_SC = False


PERSON_SIZE_M = 0.6
VEHICLE_SIZE_M = 1.5


def _radar_pose_mats(radar: dict) -> tuple[np.ndarray, np.ndarray]:
  """Return (radar_local→scene, scene→radar_local) 4×4 matrices."""
  if _HAS_SC:
    rpose = CameraPose(
      {"translation": radar["translation"], "rotation": radar["rotation"],
       "scale": radar.get("scale", [1, 1, 1])},
      None)
    m = np.array(rpose.pose_mat, dtype=np.float64)
    return m, np.linalg.inv(m)
  # Fallback: yaw-only (rz) + translation, matching VIDETEC radar poses.
  t = np.asarray(radar["translation"], dtype=np.float64)
  rot = radar["rotation"]
  yaw = math.radians(float(rot[2]) if len(rot) >= 3 else float(rot[0]))
  c, s = math.cos(yaw), math.sin(yaw)
  m = np.eye(4)
  m[0, 0], m[0, 1] = c, -s
  m[1, 0], m[1, 1] = s, c
  m[0:3, 3] = t
  return m, np.linalg.inv(m)


def _project_bottom_centre(pose, x, y, w, h, half_size: float):
  """Map bbox bottom-centre to a scene ground point (z≈0)."""
  bb = pose.intrinsics.mapPixelToNormalizedImagePlane(
    Rectangle({"x": x, "y": y, "width": w, "height": h}))
  pt = Point(bb.x + bb.width / 2, bb.y2)
  world = pose.cameraPointToWorldPoint(pt)
  if not pt.is3D:
    line1 = Line(pose.translation, world)
    line2 = Line(world, Point(half_size, line1.angle, 0, polar=True), relative=True)
    world = line2.end
  return [float(world.x), float(world.y), float(world.z)]


def project_detections(
    dets_jsonl: Path,
    scene_json: Path,
    cam_id: str,
    labels: set[str] | None = None,
) -> list[dict]:
  if not _HAS_SC:
    raise RuntimeError(
      "scene_common is required for camera projection; run inside the scene "
      "container or with scene_common on PYTHONPATH")
  labels = labels or {"person", "vehicle", "cyclist"}
  scene = json.loads(scene_json.read_text())
  cams = {c["uid"]: c for c in scene["cameras"]}
  if cam_id not in cams:
    raise KeyError(f"camera {cam_id!r} not in {scene_json}")
  camera = Camera(cam_id, dict(cams[cam_id]), resolution=[1920, 1200])
  pose = camera.pose
  radar = scene["radars"][0]
  _, minv = _radar_pose_mats(radar)

  rows: list[dict] = []
  for line in dets_jsonl.open():
    d = json.loads(line)
    for x in d.get("dets", []):
      lab = x.get("label")
      if lab not in labels:
        continue
      half = PERSON_SIZE_M / 2 if lab == "person" else VEHICLE_SIZE_M / 2
      scene_xyz = _project_bottom_centre(
        pose, x["x"], x["y"], x["w"], x["h"], half)
      loc = minv @ np.array([scene_xyz[0], scene_xyz[1], scene_xyz[2], 1.0])
      rows.append({
        "frame_index": d["frame_index"],
        "label": lab,
        "conf": float(x["conf"]),
        "scene": scene_xyz,
        "radar_local": [float(loc[0]), float(loc[1]), float(loc[2])],
        "px": [x["x"], x["y"], x["w"], x["h"]],
      })
  return rows


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--dets", type=Path, required=True,
                  help="JSONL from detect_camera_frames.py")
  ap.add_argument("--scene", type=Path,
                  default=_RI_ROOT / "RadarIntersection.json")
  ap.add_argument("--camera", default="radar-cam1")
  ap.add_argument("--labels", default="person,vehicle,cyclist")
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  labels = {s.strip() for s in args.labels.split(",") if s.strip()}
  rows = project_detections(args.dets, args.scene, args.camera, labels)
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(rows))
  by = {}
  for r in rows:
    by[r["label"]] = by.get(r["label"], 0) + 1
  print(f"projected {len(rows)}: {by}")


if __name__ == "__main__":
  main()
