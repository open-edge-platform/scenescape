#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Preprocess the raw Wildtrack dataset into canonical evaluation-pipeline formats.

Outputs (written to ``--output``):

- ``scene_config.json`` – dataset scene configuration with explicit per-camera
  intrinsics + extrinsics (canonical camera->world pose).
- ``cam0.json`` .. ``cam6.json`` – one canonical detection JSONL file per camera
  (Input Detection Format), one line per annotated frame.
- ``gtLoc.json`` – per-frame ground-truth object locations (JSONL), decoded from
  the Wildtrack ``positionID`` grid.

The raw dataset path is a required argument and is never hard-coded.

Usage::

    python -m datasets.wildtrack.preprocess \
        --dataset-path /path/to/Wildtrack_dataset \
        --output ../../../tests/system/metric/wildtrack_dataset
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

from datasets.wildtrack import calibration as wt


# Fixed synthetic epoch; annotation filename index is in 0.1 s units.
EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _format_timestamp(file_index: int) -> str:
  """Return an ISO-8601 millisecond timestamp for a Wildtrack file index."""
  ts = EPOCH + timedelta(seconds=file_index * wt.ANNOTATION_TIME_UNIT_S)
  return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def build_scene_config(dataset_path: Path) -> Dict:
  """Build the dataset scene configuration with explicit intrinsics/extrinsics."""
  sensors: Dict[str, Dict] = {}
  for view_num, cam_name in enumerate(wt.WILDTRACK_CAMERA_NAMES):
    cam_id = wt.camera_id_for_view(view_num)
    intrinsics, distortion = wt.parse_intrinsics(
      wt.calibration_path(dataset_path, "intrinsic_zero", cam_name)
    )
    rvec, tvec = wt.parse_extrinsics(
      wt.calibration_path(dataset_path, "extrinsic", cam_name)
    )
    sensors[cam_id] = {
      "intrinsics": intrinsics,
      "distortion": distortion,
      "extrinsics": wt.extrinsics_to_pose(rvec, tvec),
      "width": float(wt.IMAGE_WIDTH),
      "height": float(wt.IMAGE_HEIGHT),
    }
  return {
    "uid": "wildtrack",
    "name": "Wildtrack",
    "sensors": sensors,
  }


def _normalized_box(xmin: float, ymin: float, xmax: float, ymax: float,
                    intrinsics: List[float]) -> Dict[str, float]:
  """Convert a pixel box to the normalized image-plane box (distortion zero)."""
  fx, fy, cx, cy = intrinsics
  return {
    "x": (xmin - cx) / fx,
    "y": (ymin - cy) / fy,
    "width": (xmax - xmin) / fx,
    "height": (ymax - ymin) / fy,
  }


def _detection(det_id: int, xmin: float, ymin: float, xmax: float, ymax: float,
               intrinsics: List[float]) -> Dict:
  """Build a single canonical detection object entry.

  ``det_id`` is a per-frame, per-camera detection index (starting from 0), as
  produced by analytics pipelines.  The original Wildtrack ``personID`` is
  deliberately not propagated into camera inputs so the tracker must associate
  detections to tracks via its matching algorithms rather than input ID hints.
  """
  return {
    "id": det_id,
    "category": wt.OBJECT_CATEGORY,
    "confidence": 1.0,
    "bounding_box_px": {
      "x": xmin,
      "y": ymin,
      "width": xmax - xmin,
      "height": ymax - ymin,
    },
    "bounding_box": _normalized_box(xmin, ymin, xmax, ymax, intrinsics),
  }


def preprocess(dataset_path: Path, output_dir: Path) -> Dict[str, int]:
  """Run the full preprocessing and write all canonical artifacts.

  Args:
    dataset_path: Root of the raw Wildtrack dataset.
    output_dir: Destination directory for canonical artifacts.

  Returns:
    Summary dict with counts (frames, ground-truth rows, per-camera detections).
  """
  annotations_dir = dataset_path / "annotations_positions"
  if not annotations_dir.is_dir():
    raise FileNotFoundError(f"Annotations folder not found: {annotations_dir}")

  output_dir.mkdir(parents=True, exist_ok=True)

  scene_config = build_scene_config(dataset_path)
  intrinsics_by_cam = {
    cam_id: sensor["intrinsics"] for cam_id, sensor in scene_config["sensors"].items()
  }
  (output_dir / "scene_config.json").write_text(json.dumps(scene_config, indent=2))

  annotation_files = sorted(annotations_dir.glob("*.json"))
  if not annotation_files:
    raise FileNotFoundError(f"No annotation files in {annotations_dir}")

  cam_handles = {
    cam_id: (output_dir / f"{cam_id}.json").open("w") for cam_id in wt.CAMERA_IDS
  }
  gt_handle = (output_dir / "gtLoc.json").open("w")

  per_cam_detections = {cam_id: 0 for cam_id in wt.CAMERA_IDS}
  gt_rows = 0

  try:
    for frame_seq, ann_file in enumerate(annotation_files):
      file_index = int(ann_file.stem)
      timestamp = _format_timestamp(file_index)
      people = json.loads(ann_file.read_text())

      frame_objects: Dict[str, List[Dict]] = {cam_id: [] for cam_id in wt.CAMERA_IDS}
      gt_objects: List[Dict] = []

      for person in people:
        person_id = person["personID"]
        x, y = wt.decode_position_id(person["positionID"])
        gt_objects.append({
          "category": wt.OBJECT_CATEGORY,
          "id": person_id,
          "translation": [x, y, 0.0],
        })

        for view in person.get("views", []):
          if view["xmin"] == -1 and view["ymin"] == -1 \
             and view["xmax"] == -1 and view["ymax"] == -1:
            continue
          cam_id = wt.camera_id_for_view(view["viewNum"])
          # Detection IDs are assigned incrementally per camera per frame
          # (starting from 0), mirroring analytics-pipeline output. The original
          # personID is intentionally dropped from camera inputs.
          frame_objects[cam_id].append(
            _detection(len(frame_objects[cam_id]), view["xmin"], view["ymin"],
                       view["xmax"], view["ymax"], intrinsics_by_cam[cam_id])
          )

      for cam_id in wt.CAMERA_IDS:
        objects = frame_objects[cam_id]
        per_cam_detections[cam_id] += len(objects)
        cam_handles[cam_id].write(json.dumps({
          "timestamp": timestamp,
          "id": cam_id,
          "frame": frame_seq,
          "objects": {wt.OBJECT_CATEGORY: objects},
        }) + "\n")

      gt_handle.write(json.dumps({
        "timestamp": timestamp,
        "objects": {wt.OBJECT_CATEGORY: gt_objects},
      }) + "\n")
      gt_rows += len(gt_objects)
  finally:
    for handle in cam_handles.values():
      handle.close()
    gt_handle.close()

  return {
    "frames": len(annotation_files),
    "ground_truth_rows": gt_rows,
    **{f"detections_{cam_id}": count for cam_id, count in per_cam_detections.items()},
  }


def main(argv: List[str] | None = None) -> int:
  """CLI entry point."""
  parser = argparse.ArgumentParser(description="Preprocess the Wildtrack dataset.")
  parser.add_argument(
    "--dataset-path", required=True, type=Path,
    help="Path to the raw Wildtrack dataset root (parameterized, not hard-coded).",
  )
  parser.add_argument(
    "--output", required=True, type=Path,
    help="Destination directory for canonical artifacts.",
  )
  args = parser.parse_args(argv)

  if not args.dataset_path.is_dir():
    print(f"ERROR: dataset path not found: {args.dataset_path}", file=sys.stderr)
    return 1

  summary = preprocess(args.dataset_path, args.output)
  print("Wildtrack preprocessing complete:")
  for key, value in summary.items():
    print(f"  {key}: {value}")
  print(f"  output: {args.output}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
