#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Visualize pose adjustment on video.

Overlays original and adjusted bounding boxes on video frames to show
the effect of pose adjustment.

Usage:
  python controller/tools/visualize_pose_adjustment.py \
      --video sample_data/qcam2_occlusion_improved_less_occlusion.mp4 \
      --original detections.json \
      --adjusted adjusted.json \
      --output visualized.mp4
"""

import argparse
import json
import sys

import cv2


COLOR_ORIGINAL = (0, 0, 255)    # Red - original bbox
COLOR_ADJUSTED = (0, 255, 0)    # Green - adjusted bbox
COLOR_KEYPOINT = (255, 255, 0)  # Cyan - keypoints
THICKNESS = 2
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.5


def load_detections(path):
  """Load NDJSON detection file, keyed by timestamp."""
  frames = []
  with open(path) as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      frames.append(json.loads(line))
  return frames


def draw_bbox_from_detection(frame, obj, color, label=None):
  """Draw bounding box from DL Streamer detection object."""
  x = int(obj.get('x', 0))
  y = int(obj.get('y', 0))
  w = int(obj.get('w', 0))
  h = int(obj.get('h', 0))
  cv2.rectangle(frame, (x, y), (x + w, y + h), color, THICKNESS)
  if label:
    cv2.putText(frame, label, (x, y - 5), FONT, FONT_SCALE, color, 1)


def draw_keypoints(frame, obj):
  """Draw keypoints from DL Streamer detection object."""
  for kp_group in obj.get('keypoints', []):
    for pt in kp_group.get('points', []):
      conf = pt.get('confidence', 0)
      if conf < 0.3:
        continue
      px = int(pt['x'])
      py = int(pt['y'])
      cv2.circle(frame, (px, py), 3, COLOR_KEYPOINT, -1)


def bboxes_differ(obj1, obj2):
  """Check if bounding boxes differ between two detection objects."""
  bb1 = obj1.get('detection', {}).get('bounding_box', {})
  bb2 = obj2.get('detection', {}).get('bounding_box', {})
  return bb1 != bb2


def build_timestamp_to_frame_map(detections, fps):
  """Map each detection to a video frame number using its timestamp."""
  if not detections:
    return {}

  frame_map = {}  # video_frame_index (0-based) → detection index
  for det_idx, det in enumerate(detections):
    ts = det.get('timestamp', 0)
    elapsed_s = ts / 1e9
    video_frame = int(round(elapsed_s * fps))
    frame_map[video_frame] = det_idx
  return frame_map


def process_video(video_path, original_dets, adjusted_dets, output_path):
  cap = cv2.VideoCapture(video_path)
  if not cap.isOpened():
    print(f"Error: cannot open video {video_path}")
    return 1

  fps = cap.get(cv2.CAP_PROP_FPS)
  frame_size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
  total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

  fourcc = cv2.VideoWriter_fourcc(*'mp4v')
  out = cv2.VideoWriter(output_path, fourcc, fps, frame_size)

  frame_map = build_timestamp_to_frame_map(original_dets, fps)
  frame_num = 0
  adjusted_frame_count = 0

  while True:
    ret, frame = cap.read()
    if not ret:
      break

    det_idx = frame_map.get(frame_num)
    if det_idx is not None and det_idx < len(original_dets):
      orig_frame = original_dets[det_idx]
      adj_frame = adjusted_dets[det_idx]

      orig_objs = orig_frame.get('objects', [])
      adj_objs = adj_frame.get('objects', [])

      has_adjustment = False
      for orig_obj, adj_obj in zip(orig_objs, adj_objs):
        draw_keypoints(frame, orig_obj)
        obj_id = orig_obj.get('id', '')

        if bboxes_differ(orig_obj, adj_obj):
          draw_bbox_from_detection(frame, orig_obj, COLOR_ORIGINAL, f"id:{obj_id} original")
          draw_bbox_from_detection(frame, adj_obj, COLOR_ADJUSTED, f"id:{obj_id} adjusted")
          has_adjustment = True
        else:
          draw_bbox_from_detection(frame, orig_obj, COLOR_ORIGINAL, f"id:{obj_id}")

      if has_adjustment:
        adjusted_frame_count += 1

    # Draw frame info
    info = f"Frame {frame_num}/{total_frames}"
    if det_idx is not None:
      info += f" | Det {det_idx}/{len(original_dets)}"
    cv2.putText(frame, info, (10, frame_size[1] - 10), FONT, FONT_SCALE, (255, 255, 255), 1)

    out.write(frame)
    frame_num += 1

  cap.release()
  out.release()
  print(f"Written {output_path}: {frame_num} frames, {adjusted_frame_count} with adjustments")
  return 0


def build_argparser():
  parser = argparse.ArgumentParser(
    description='Visualize pose adjustment bounding box changes on video',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument('--video', required=True, help='Input video file')
  parser.add_argument('--original', required=True, help='Original detections NDJSON')
  parser.add_argument('--adjusted', required=True, help='Adjusted detections NDJSON')
  parser.add_argument('--output', default='visualized.mp4', help='Output video path')
  return parser


def main():
  args = build_argparser().parse_args()
  original_dets = load_detections(args.original)
  adjusted_dets = load_detections(args.adjusted)

  if len(original_dets) != len(adjusted_dets):
    print(f"Warning: detection count mismatch: original={len(original_dets)}, adjusted={len(adjusted_dets)}")

  return process_video(args.video, original_dets, adjusted_dets, args.output)


if __name__ == '__main__':
  sys.exit(main() or 0)
