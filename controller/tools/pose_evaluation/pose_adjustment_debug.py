#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Offline pose-adjustment debug tool.

Reads a DL Streamer detection NDJSON file (one JSON object per line),
applies person pose adjustment to every detection, and writes the
adjusted results in the same format.

Usage:
  python controller/tools/pose_adjustment_debug.py \
      --input detections.json --output adjusted.json

This avoids the full controller stack (MQTT, REST, Django) so you can
inspect how pose adjustment changes bounding boxes without timing issues.
"""

import argparse
import json
import sys

from controller.pose_adjustment.strategies.person.bbox_adjuster import PersonPoseAdjuster

# COCO-17 index → canonical joint name
COCO17_INDEX_TO_NAME = {
  0: 'nose',
  1: 'left_eye',
  2: 'right_eye',
  3: 'left_ear',
  4: 'right_ear',
  5: 'left_shoulder',
  6: 'right_shoulder',
  7: 'left_elbow',
  8: 'right_elbow',
  9: 'left_wrist',
  10: 'right_wrist',
  11: 'left_hip',
  12: 'right_hip',
  13: 'left_knee',
  14: 'right_knee',
  15: 'left_ankle',
  16: 'right_ankle',
}


def dlstreamer_to_internal(obj):
  """Convert a DL Streamer detection object to the internal format.

  Mimics how sscape_policies.py + sscape_adapter.py transform detections
  before publishing to MQTT (which the controller then receives).
  Only bounding_box_px is set (no normalized bounding_box), and keypoints
  are in bbox-relative coordinates (0-1 within the pixel bbox).
  """
  det = obj.get('detection', {})

  internal = {
    'category': obj.get('roi_type', det.get('label', 'unknown')),
  }

  if 'id' in obj:
    internal['id'] = obj['id']

  # Only set bounding_box_px (matching what detectionPolicy produces)
  px_x = obj.get('x', 0)
  px_y = obj.get('y', 0)
  px_w = obj.get('w', 1)
  px_h = obj.get('h', 1)

  internal['bounding_box_px'] = {
    'x': px_x,
    'y': px_y,
    'width': px_w,
    'height': px_h,
  }

  # Keypoints in bbox-relative coordinates (0-1 within the bbox).
  # scale_keypoints() will convert these back to absolute pixel space.
  # Filter out keypoints with near-zero confidence (pose model reports
  # positions for occluded joints with confidence ~0, which would fool
  # the adjuster into thinking ankles are visible).
  keypoints = []
  for kp_group in obj.get('keypoints', []):
    for pt in kp_group.get('points', []):
      idx = pt.get('index')
      name = COCO17_INDEX_TO_NAME.get(idx)
      if name is None:
        continue
      keypoints.append({
        'name': name,
        'x': (pt['x'] - px_x) / px_w if px_w > 0 else 0,
        'y': (pt['y'] - px_y) / px_h if px_h > 0 else 0,
        'confidence': pt.get('confidence'),
      })
  internal['keypoints'] = keypoints
  return internal


def internal_to_dlstreamer(internal, original, resolution):
  """Write adjusted bounding box back into a copy of the original object."""
  out = json.loads(json.dumps(original))

  px = internal.get('bounding_box_px')
  if px:
    out['x'] = px['x']
    out['y'] = px['y']
    out['w'] = px['width']
    out['h'] = px['height']
    # Also update the normalized bounding_box in DL Streamer format
    res_w, res_h = resolution
    out.setdefault('detection', {})['bounding_box'] = {
      'x_min': px['x'] / res_w,
      'y_min': px['y'] / res_h,
      'x_max': (px['x'] + px['width']) / res_w,
      'y_max': (px['y'] + px['height']) / res_h,
    }

  return out


def process_file(input_path, output_path, scene_name, camera_id):
  adjuster = PersonPoseAdjuster(
    max_entry_age_seconds=86400,
    min_observations=3,
  )

  total_detections = 0
  total_adjusted = 0

  with open(input_path) as fin, open(output_path, 'w') as fout:
    for line in fin:
      line = line.strip()
      if not line:
        continue

      frame = json.loads(line)
      res = frame.get('resolution', {})
      resolution = (res.get('width', 1280), res.get('height', 720))

      timestamp = frame.get('timestamp', 0)
      when = float(timestamp) / 1e9

      adjusted_objects = []
      for obj in frame.get('objects', []):
        internal = dlstreamer_to_internal(obj)
        total_detections += 1

        if adjuster.adjust_detection(internal, scene_name, camera_id, when, resolution):
          total_adjusted += 1
          adjusted_objects.append(internal_to_dlstreamer(internal, obj, resolution))
        else:
          adjusted_objects.append(obj)

      frame['objects'] = adjusted_objects
      fout.write(json.dumps(frame) + '\n')

  print(f"Processed {total_detections} detections, adjusted {total_adjusted}")


def build_argparser():
  parser = argparse.ArgumentParser(
    description='Offline pose-adjustment debug tool',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument('--input', required=True, help='Input NDJSON detection file')
  parser.add_argument('--output', required=True, help='Output NDJSON file with adjusted bboxes')
  parser.add_argument('--scene-name', default='debug', help='Scene name for proportion cache')
  parser.add_argument('--camera-id', default='debug', help='Camera ID for proportion cache')
  return parser


def main():
  args = build_argparser().parse_args()
  process_file(args.input, args.output, args.scene_name, args.camera_id)


if __name__ == '__main__':
  sys.exit(main() or 0)
