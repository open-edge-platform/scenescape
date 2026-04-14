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

For each detection frame it:
  1. Looks up the pre-built ``CameraPose`` for the camera.
  2. Computes the bottom-centre of each object's bounding box in normalised
     image space.
  3. Projects that 2-D point onto the world ground-plane (z = 0) using
     ``CameraPose.cameraPointToWorldPoint()``.
  4. Records the projected 3-D position.

It writes ``output.json`` – a JSON array of canonical Tracker Output Format
dicts (one entry per input detection frame).

Object ID encoding
------------------
Each output object ID is ``"{camera_id}:{object_id}"`` (e.g.
``"Cam_x1_0:0"``).  The ``CameraAccuracyEvaluator`` parses this separator to
group results per camera and compute per-camera metrics.

Bounding-box convention
-----------------------
The ``bounding_box`` field in the input is in *normalised image space*:

  - ``x``, ``y``  : top-left corner relative to the image centre, in units
                    where one pixel at ``cx`` corresponds to 1/fx in x, etc.
                    (i.e. the output of ``cv2.undistortPoints`` / the
                    ``mapPixelToNormalizedImagePlane`` helper).
  - ``width``      : horizontal extent (positive right).
  - ``height``     : vertical extent (positive downward).

Bottom-centre in normalised image space:
    centre_x = x + width / 2
    bottom_y = y + height

These coordinates are passed directly to
``CameraPose.cameraPointToWorldPoint(Point(centre_x, bottom_y))``.
"""

import json
import sys

from scene_common.transform import CameraPose, CameraIntrinsics
from scene_common.geometry import Point


def load_camera_poses(config: dict) -> dict:
  """Build a mapping from camera ID → CameraPose.

  Args:
    config: Raw scene config dict with a ``"sensors"`` sub-dict.  Each sensor
            entry must contain:
            - ``camera points``  (list of 2-D pixel points)
            - ``map points``     (list of 3-D world points)
            - ``intrinsics``     ([fx, fy, cx, cy] array)
            - ``width``, ``height``  (image resolution)

  Returns:
    Dict mapping sensor name → ``CameraPose`` (actually
    ``PointCorrespondenceTransform``) instance.
  """
  poses = {}
  sensors = config.get("sensors", {})

  for cam_id, sensor_info in sensors.items():
    try:
      intrinsics_raw = sensor_info["intrinsics"]
      # [fx, fy, cx, cy] → CameraIntrinsics accepts this 4-element list
      intrinsics = CameraIntrinsics(intrinsics_raw)

      pose_info = {
        "camera points": sensor_info["camera points"],
        "map points": sensor_info["map points"],
      }
      # CameraPose.__new__ returns a PointCorrespondenceTransform when
      # the dict contains 'camera points' and 'map points'.
      pose = CameraPose(pose_info, intrinsics)
      poses[cam_id] = pose
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
) -> dict | None:
  """Project all detections in one camera frame to world coordinates.

  Args:
    detection_frame: One canonical Input Detection Format dict.  Expected
                     keys: ``id`` (camera ID), ``timestamp``, ``frame``,
                     ``objects`` (dict of ``{category: [obj, ...]}``.
    camera_poses: Mapping from camera ID → ``CameraPose``.

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

  projected_objects = []

  for category, obj_list in detection_frame.get("objects", {}).items():
    for obj in obj_list:
      bb = obj.get("bounding_box")
      if bb is None:
        # Fall back to pixel bounding box if available, but normalised is
        # required – skip objects without it.
        print(
          f"[run_projection] WARNING: object {obj.get('id')} in '{cam_id}' "
          "has no 'bounding_box', skipping",
          file=sys.stderr,
        )
        continue

      # Bottom-centre of the bounding box in normalised image space.
      centre_x = bb["x"] + bb["width"] / 2.0
      bottom_y = bb["y"] + bb["height"]
      cam_point = Point(centre_x, bottom_y)

      world_point = pose.cameraPointToWorldPoint(cam_point)

      obj_id = obj["id"]
      projected_objects.append({
        "id": f"{cam_id}:{obj_id}",
        "translation": [world_point.x, world_point.y, world_point.z],
        "category": category,
      })

  return {
    "cam_id": cam_id,
    "frame": frame_num,
    "timestamp": timestamp,
    "objects": projected_objects,
  }


def main() -> int:
  """Entry point: read inputs, project detections, write output.

  Returns:
    0 on success, 1 on failure.
  """
  print("[run_projection] Starting camera projection script")

  # Load scene configuration
  try:
    with open("config.json") as f:
      config = json.load(f)
  except Exception as exc:
    print(f"[run_projection] ERROR: Failed to load config.json: {exc}", file=sys.stderr)
    return 1

  # Build camera poses from config
  camera_poses = load_camera_poses(config)
  if not camera_poses:
    print("[run_projection] ERROR: No camera poses could be built", file=sys.stderr)
    return 1

  # Stream-process input frames
  output_frames = []
  frame_count = 0
  skipped = 0

  try:
    with open("inputs.json", "r") as f:
      for line in f:
        line = line.strip()
        if not line:
          continue
        detection_frame = json.loads(line)
        result = project_frame(detection_frame, camera_poses)
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

  # Write output
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
