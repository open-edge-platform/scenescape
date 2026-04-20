#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Projection script executed inside the scene_common Docker container.

This script is copied to the shared temporary workspace by
CameraProjectionHarness and executed with:

    python3 /workspace/run_projection.py

It reads:
  - ``config.json``  – raw scene configuration with camera calibration
  - ``inputs.json``  – JSONL file of canonical camera detection frames
  - ``params.json``  – optional projection parameters (object class settings)

For each detection frame it:
  1. Looks up the pre-built ``CameraPose`` for the camera.
  2. Selects the projection point according to the object category's
     ``shift_type`` (TYPE_1 or TYPE_2, see below).
  3. Projects that point onto the world ground-plane (z = 0) using
     ``CameraPose.cameraPointToWorldPoint()``.
  4. Applies the camloc size offset — pushes the result
     ``mean([x_size, y_size]) / 2`` metres away from the camera,
     matching ``MovingObject.mapObjectDetectionToWorld()``.

It writes ``output.json`` – a JSON array of canonical Tracker Output Format
dicts (one entry per input detection frame).

Projection modes (shift_type)
-------------------------------
- **TYPE_1** (``shift_type: 1``, default): uses the bounding-box
  bottom-centre as the ground contact point.
- **TYPE_2** (``shift_type: 2``): shifts the projection point upward
  from the bottom edge by ``(height / 2) * (baseAngle / 90)`` where
  ``baseAngle`` is the angle between the camera and the object base,
  obtained from ``CameraPose.projectBounds()``.  Reduces perspective
  overshoot for objects seen from a steep/far angle.

Object class configuration (params.json)
-----------------------------------------
``params.json`` may contain an ``object_classes`` list, e.g.::

    {"object_classes": [
        {"name": "person", "shift_type": 2, "x_size": 0.5, "y_size": 0.5}
    ]}

Categories not listed fall back to TYPE_1 with no size offset.

Object ID encoding
------------------
Each output object ID is ``"{camera_id}:{object_id}"`` (e.g.
``"Cam_x1_0:0"``).  The ``CameraAccuracyEvaluator`` parses this separator to
group results per camera and compute per-camera metrics.
"""

import json
import sys

import numpy as np
from scene_common.transform import CameraPose, CameraIntrinsics
from scene_common.geometry import Line, Point, Rectangle

TYPE_1 = 1
TYPE_2 = 2
DEFAULT_SHIFT_TYPE = TYPE_1
DEFAULT_X_SIZE = 0.0
DEFAULT_Y_SIZE = 0.0


def _build_class_map(object_classes: list) -> dict:
  """Build a category-name → settings dict from the object_classes list.

  Returns:
    Dict mapping lower-case category name to
    ``{"shift_type": int, "x_size": float, "y_size": float}``.
  """
  result = {}
  for entry in object_classes:
    name = str(entry.get("name", "")).lower()
    if not name:
      continue
    result[name] = {
      "shift_type": int(entry.get("shift_type", DEFAULT_SHIFT_TYPE)),
      "x_size": float(entry.get("x_size", DEFAULT_X_SIZE)),
      "y_size": float(entry.get("y_size", DEFAULT_Y_SIZE)),
    }
  return result


def load_camera_poses(config: dict) -> dict:
  """Build a mapping from camera ID → CameraPose."""
  poses = {}
  for cam_id, sensor_info in config.get("sensors", {}).items():
    try:
      intrinsics = CameraIntrinsics(sensor_info["intrinsics"])
      pose_info = {
        "camera points": sensor_info["camera points"],
        "map points": sensor_info["map points"],
      }
      poses[cam_id] = CameraPose(pose_info, intrinsics)
      print(f"[run_projection] Built pose for camera '{cam_id}'")
    except Exception as exc:
      print(
        f"[run_projection] WARNING: Could not build pose for '{cam_id}': {exc}",
        file=sys.stderr,
      )
  return poses


def project_frame(
  detection_frame: dict,
  camera_poses: dict,
  class_map: dict,
) -> dict | None:
  """Project all detections in one camera frame to world coordinates.

  Uses per-category shift_type and size offset from class_map.

  Returns:
    Canonical Tracker Output Format dict, or ``None`` if the camera pose is
    unknown.
  """
  cam_id = detection_frame.get("id")
  if cam_id not in camera_poses:
    print(
      f"[run_projection] WARNING: No pose for camera '{cam_id}', skipping frame",
      file=sys.stderr,
    )
    return None

  pose = camera_poses[cam_id]
  timestamp = detection_frame["timestamp"]
  frame_num = detection_frame.get("frame", 0)
  cam_t = pose.translation

  projected_objects = []

  for category, obj_list in detection_frame.get("objects", {}).items():
    cls = class_map.get(category.lower(), {})
    shift_type = cls.get("shift_type", DEFAULT_SHIFT_TYPE)
    x_size = cls.get("x_size", DEFAULT_X_SIZE)
    y_size = cls.get("y_size", DEFAULT_Y_SIZE)

    for obj in obj_list:
      bb = obj.get("bounding_box")
      if bb is None:
        print(
          f"[run_projection] WARNING: object {obj.get('id')} in '{cam_id}' "
          "has no 'bounding_box', skipping",
          file=sys.stderr,
        )
        continue

      centre_x = bb["x"] + bb["width"] / 2.0
      bottom_y = bb["y"] + bb["height"]

      # TYPE_2: shift projection point upward based on camera elevation angle
      if shift_type == TYPE_2:
        try:
          bb_rect = Rectangle(bb)
          _, _, base_angle = pose.projectBounds(bb_rect)
          bottom_y = bottom_y - (bb["height"] / 2.0) * (base_angle / 90.0)
        except Exception as exc:
          print(
            f"[run_projection] WARNING: TYPE_2 shift failed for "
            f"'{obj.get('id')}': {exc}, falling back to TYPE_1",
            file=sys.stderr,
          )

      world_point = pose.cameraPointToWorldPoint(Point(centre_x, bottom_y))

      # Camloc compensation: exact production code from
      # MovingObject.mapObjectDetectionToWorld() (controller/moving_object.py).
      # line1 from camera translation to projected world point gives the
      # bearing angle; line2 pushes world_point along that bearing by
      # mean([x_size, y_size]) / 2 metres.
      offset = np.mean([x_size, y_size]) / 2
      if offset > 1e-9:
        line1 = Line(cam_t, world_point)
        line2 = Line(world_point, Point(offset, line1.angle, 0, polar=True), relative=True)
        world_point = line2.end

      projected_objects.append({
        "id": f"{cam_id}:{obj['id']}",
        "translation": [world_point.x, world_point.y, 0.0],
        "category": category,
      })

  return {
    "cam_id": cam_id,
    "frame": frame_num,
    "timestamp": timestamp,
    "camera_position": [cam_t.x, cam_t.y, cam_t.z],
    "objects": projected_objects,
  }


def main() -> int:
  """Entry point: read inputs, project detections, write output."""
  print("[run_projection] Starting camera projection script")

  try:
    with open("config.json") as f:
      config = json.load(f)
  except Exception as exc:
    print(f"[run_projection] ERROR: Failed to load config.json: {exc}", file=sys.stderr)
    return 1

  # Load optional projection parameters
  class_map: dict = {}
  try:
    with open("params.json") as f:
      params = json.load(f)
    class_map = _build_class_map(params.get("object_classes", []))
    if class_map:
      print(f"[run_projection] Loaded class settings: {list(class_map.keys())}")
  except FileNotFoundError:
    print("[run_projection] No params.json found, using TYPE_1 defaults")
  except Exception as exc:
    print(f"[run_projection] WARNING: Failed to load params.json: {exc}", file=sys.stderr)

  camera_poses = load_camera_poses(config)
  if not camera_poses:
    print("[run_projection] ERROR: No camera poses could be built", file=sys.stderr)
    return 1

  output_frames = []
  frame_count = 0
  skipped = 0

  try:
    with open("inputs.json") as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        detection_frame = json.loads(line)
        result = project_frame(detection_frame, camera_poses, class_map)
        if result is not None:
          output_frames.append(result)
        else:
          skipped += 1
        frame_count += 1
  except Exception as exc:
    print(f"[run_projection] ERROR: Failed to process inputs: {exc}", file=sys.stderr)
    return 1

  print(
    f"[run_projection] Processed {frame_count} frames, "
    f"projected {len(output_frames)}, skipped {skipped}"
  )

  try:
    with open("output.json", "w") as f:
      json.dump(output_frames, f)
    print(f"[run_projection] Wrote {len(output_frames)} frames to output.json")
  except Exception as exc:
    print(f"[run_projection] ERROR: Failed to write output.json: {exc}", file=sys.stderr)
    return 1

  return 0


if __name__ == "__main__":
  sys.exit(main())
