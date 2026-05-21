# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Dict, Optional, Tuple


def coerce_bbox(bbox) -> Optional[Dict[str, float]]:
  if not isinstance(bbox, dict):
    return None
  try:
    x_coord = float(bbox['x'])
    y_coord = float(bbox['y'])
    width = float(bbox['width'])
    height = float(bbox['height'])
  except (KeyError, TypeError, ValueError):
    return None

  if width <= 0 or height <= 0:
    return None

  return {
    'x': x_coord,
    'y': y_coord,
    'width': width,
    'height': height,
  }


def clip_value(value: float, minimum: float, maximum: float) -> float:
  return max(minimum, min(value, maximum))


def bounds(bounds_value) -> Tuple[float, float]:
  if bounds_value is None or len(bounds_value) != 2:
    return (1.0, 1.0)
  return (float(bounds_value[0]), float(bounds_value[1]))


def clip_point(x_coord: float, y_coord: float, bounds_value) -> Tuple[float, float]:
  frame_width, frame_height = bounds(bounds_value)
  return (
    clip_value(x_coord, 0.0, frame_width),
    clip_value(y_coord, 0.0, frame_height),
  )


def scale_bbox(bbox: Dict[str, float], resolution) -> Optional[Dict[str, int]]:
  if resolution is None or len(resolution) != 2:
    return None
  width, height = float(resolution[0]), float(resolution[1])
  scaled_bbox = {
    'x': bbox['x'] * width,
    'y': bbox['y'] * height,
    'width': bbox['width'] * width,
    'height': bbox['height'] * height,
  }
  return {key: int(round(value)) for key, value in scaled_bbox.items()}


def quantize_bbox(
  bbox: Dict[str, float], frame_width: float, frame_height: float,
) -> Dict:
  """Round bbox values to integers for pixel space or 6 decimals for normalized."""
  if frame_width > 1.0 or frame_height > 1.0:
    return {key: int(round(value)) for key, value in bbox.items()}
  return {key: round(value, 6) for key, value in bbox.items()}
