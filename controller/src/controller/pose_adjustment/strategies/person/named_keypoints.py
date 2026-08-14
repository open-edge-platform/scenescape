# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Dict, Optional

from scene_common import log

# YOLO pose outputs per-keypoint confidence; below 0.5 the keypoint is unreliable.
# Other models may need a different threshold.
# TODO: make configurable via pose-adjustment-route.json.
MIN_KEYPOINT_CONFIDENCE = 0.5

JOINT_ALIASES = {
  'nose': 'nose',
  'eye_l': 'left_eye',
  'left_eye': 'left_eye',
  'l_eye': 'left_eye',
  'eye_r': 'right_eye',
  'right_eye': 'right_eye',
  'r_eye': 'right_eye',
  'ear_l': 'left_ear',
  'left_ear': 'left_ear',
  'l_ear': 'left_ear',
  'ear_r': 'right_ear',
  'right_ear': 'right_ear',
  'r_ear': 'right_ear',
  'shoulder_l': 'left_shoulder',
  'left_shoulder': 'left_shoulder',
  'l_shoulder': 'left_shoulder',
  'shoulder_r': 'right_shoulder',
  'right_shoulder': 'right_shoulder',
  'r_shoulder': 'right_shoulder',
  'hip_l': 'left_hip',
  'left_hip': 'left_hip',
  'l_hip': 'left_hip',
  'hip_r': 'right_hip',
  'right_hip': 'right_hip',
  'r_hip': 'right_hip',
  'knee_l': 'left_knee',
  'left_knee': 'left_knee',
  'l_knee': 'left_knee',
  'knee_r': 'right_knee',
  'right_knee': 'right_knee',
  'r_knee': 'right_knee',
  'ankle_l': 'left_ankle',
  'left_ankle': 'left_ankle',
  'l_ankle': 'left_ankle',
  'ankle_r': 'right_ankle',
  'right_ankle': 'right_ankle',
  'r_ankle': 'right_ankle',
}


@dataclass(frozen=True)
class NamedKeypoint:
  x: float
  y: float
  confidence: Optional[float] = None


def canonical_joint_name(name: str) -> Optional[str]:
  """Map an incoming joint label to an internal canonical name."""
  if not isinstance(name, str):
    return None
  return JOINT_ALIASES.get(name.strip().lower())


def parse_named_keypoints(raw_keypoints) -> Dict[str, NamedKeypoint]:
  """Parse MQTT keypoints into a canonical joint dictionary."""
  if not isinstance(raw_keypoints, list):
    return {}

  parsed = {}
  for item in raw_keypoints:
    if not isinstance(item, dict):
      continue

    joint_name = canonical_joint_name(item.get('name'))
    if joint_name is None:
      continue

    try:
      x_coord = float(item['x'])
      y_coord = float(item['y'])
    except (KeyError, TypeError, ValueError):
      continue

    confidence = item.get('confidence', item.get('score', item.get('probability')))
    try:
      confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
      confidence = None

    if confidence is None or confidence < MIN_KEYPOINT_CONFIDENCE:
      continue

    current = parsed.get(joint_name)
    if current is None or current.confidence < confidence:
      parsed[joint_name] = NamedKeypoint(x_coord, y_coord, confidence)

  return parsed


def keypoints_are_normalized(keypoints: Dict[str, NamedKeypoint]) -> bool:
  """Return True when all keypoints appear to be in normalized frame coordinates."""
  if not keypoints:
    return False
  for keypoint in keypoints.values():
    if keypoint.x < -0.01 or keypoint.x > 1.01:
      return False
    if keypoint.y < -0.01 or keypoint.y > 1.01:
      return False
  return True


def _bbox_is_usable(bbox) -> bool:
  """Return True when bbox contains positive pixel-space dimensions."""
  if not isinstance(bbox, dict):
    return False

  try:
    return float(bbox['width']) > 0 and float(bbox['height']) > 0
  except (KeyError, TypeError, ValueError):
    return False


def scale_keypoints(
  keypoints: Dict[str, NamedKeypoint],
  resolution,
  bbox=None,
) -> Dict[str, NamedKeypoint]:
  """Scale normalized keypoints into pixel coordinates."""
  if not keypoints:
    return keypoints.copy()

  scale_mode = 'preserved'
  if _bbox_is_usable(bbox):
    bbox_x = float(bbox['x'])
    bbox_y = float(bbox['y'])
    bbox_width = float(bbox['width'])
    bbox_height = float(bbox['height'])
    scaled_keypoints = {
      joint_name: NamedKeypoint(
        bbox_x + keypoint.x * bbox_width,
        bbox_y + keypoint.y * bbox_height,
        keypoint.confidence,
      )
      for joint_name, keypoint in keypoints.items()
    }
    scale_mode = 'scaled_bbox'
  elif resolution is not None and len(resolution) == 2 and keypoints_are_normalized(keypoints):
    width, height = float(resolution[0]), float(resolution[1])
    scaled_keypoints = {
      joint_name: NamedKeypoint(
        keypoint.x * width,
        keypoint.y * height,
        keypoint.confidence,
      )
      for joint_name, keypoint in keypoints.items()
    }
    scale_mode = 'scaled_frame'
  else:
    scaled_keypoints = keypoints.copy()

  sample_joint_name, sample_keypoint = next(iter(keypoints.items()))
  sample_scaled = scaled_keypoints[sample_joint_name]
  log.debug(
    f"scale_keypoints {scale_mode} sample_joint={sample_joint_name} "
    f"before=({sample_keypoint.x:.4f}, {sample_keypoint.y:.4f}) "
    f"after=({sample_scaled.x:.4f}, {sample_scaled.y:.4f}) "
    f"resolution={resolution} bbox={bbox}"
  )
  return scaled_keypoints


def midpoint(
  keypoints: Dict[str, NamedKeypoint],
  left_name: str,
  right_name: str,
  allow_single: bool = True,
) -> Optional[NamedKeypoint]:
  """Return the midpoint of a left/right joint pair."""
  left_keypoint = keypoints.get(left_name)
  right_keypoint = keypoints.get(right_name)

  if left_keypoint and right_keypoint:
    confidence = None
    if left_keypoint.confidence is not None and right_keypoint.confidence is not None:
      confidence = (left_keypoint.confidence + right_keypoint.confidence) / 2
    return NamedKeypoint(
      (left_keypoint.x + right_keypoint.x) / 2,
      (left_keypoint.y + right_keypoint.y) / 2,
      confidence,
    )

  if allow_single:
    return left_keypoint or right_keypoint

  return None


def head_point(keypoints: Dict[str, NamedKeypoint]) -> Optional[NamedKeypoint]:
  """Return the best available head reference point."""
  if 'nose' in keypoints:
    return keypoints['nose']

  eyes = midpoint(keypoints, 'left_eye', 'right_eye')
  if eyes is not None:
    return eyes

  return midpoint(keypoints, 'left_ear', 'right_ear')
