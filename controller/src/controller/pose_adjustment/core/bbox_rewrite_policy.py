# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Callable, Collection, Dict, Optional, Protocol

from scene_common import log

from controller.pose_adjustment.core.bbox_utils import (bounds as bbox_bounds, clip_value, quantize_bbox)


class RewriteAnchorEstimateLike(Protocol):
  x: float
  y: float
  method: str
  confidence: Optional[float]
  direct_observation_count: int
  allow_horizontal_shift: bool


@dataclass(frozen=True)
class BoundingBoxRewriteThresholds:
  direct_safety_margin: float
  estimated_safety_margin: float
  direct_gap_factor: float
  estimated_gap_factor: float
  min_estimate_confidence_threshold: float
  low_confidence_estimation_methods: Collection[str]


class BoundingBoxRewritePolicy:
  """Generic bbox rewrite decision/policy for keypoint-derived anchor strategies."""

  def __init__(
    self,
    thresholds: BoundingBoxRewriteThresholds,
    has_likely_occlusion_signal: Callable[[Dict, Dict], bool],
  ):
    self._thresholds = thresholds
    self._has_likely_occlusion_signal = has_likely_occlusion_signal

  def should_rewrite_bbox(
    self,
    bbox: Dict[str, float],
    keypoints: Dict,
    anchor: RewriteAnchorEstimateLike,
  ) -> bool:
    box_bottom = bbox['y'] + bbox['height']
    safety_margin = (
      self._thresholds.direct_safety_margin if anchor.direct_observation_count > 0
      else self._thresholds.estimated_safety_margin
    )
    desired_bottom = anchor.y + bbox['height'] * safety_margin
    required_extension = desired_bottom - box_bottom
    min_extension = bbox['height'] * (
      self._thresholds.direct_gap_factor if anchor.direct_observation_count > 0
      else self._thresholds.estimated_gap_factor
    )

    if required_extension <= min_extension:
      log.debug(
        f"Skipping bbox rewrite for {anchor.method}: extension={required_extension:.4f} "
        f"threshold={min_extension:.4f}"
      )
      return False

    if anchor.direct_observation_count > 0:
      return True

    if anchor.method in self._thresholds.low_confidence_estimation_methods:
      log.debug(f"Skipping bbox rewrite for {anchor.method}: low-confidence estimate method")
      return False

    if (
      anchor.confidence is not None
      and anchor.confidence < self._thresholds.min_estimate_confidence_threshold
    ):
      log.debug(
        f"Skipping bbox rewrite for {anchor.method}: estimate confidence={anchor.confidence:.4f}"
      )
      return False

    if not self._has_likely_occlusion_signal(keypoints, bbox):
      log.debug(
        f"Skipping bbox rewrite for {anchor.method}: pose pattern does not suggest occlusion"
      )
      return False

    return True

  def rewrite_bbox(
    self,
    bbox: Dict[str, float],
    anchor: RewriteAnchorEstimateLike,
    bounds,
  ) -> Dict[str, float]:
    frame_width, frame_height = bbox_bounds(bounds)
    safety_margin = (
      self._thresholds.direct_safety_margin if anchor.direct_observation_count > 0
      else self._thresholds.estimated_safety_margin
    )
    desired_bottom = anchor.y + bbox['height'] * safety_margin
    bottom_y = max(bbox['y'] + bbox['height'], desired_bottom)

    width = min(bbox['width'], frame_width)
    top_y = clip_value(bbox['y'], 0.0, frame_height)
    left_x = self._compute_left_x(bbox, anchor, width, frame_width)
    bottom_y = clip_value(bottom_y, top_y, frame_height)
    height = min(max(bottom_y - top_y, bbox['height']), frame_height - top_y)

    adjusted_bbox = {'x': left_x, 'y': top_y, 'width': width, 'height': height}
    final_bbox = quantize_bbox(adjusted_bbox, frame_width, frame_height)

    log.debug(
      f"Rewriting bbox using {anchor.method}: before={bbox}, after={final_bbox}, "
      f"anchor=({anchor.x:.4f}, {anchor.y:.4f}), shift_x={anchor.allow_horizontal_shift}"
    )
    return final_bbox

  def _compute_left_x(
    self,
    bbox: Dict[str, float],
    anchor: RewriteAnchorEstimateLike,
    width: float,
    frame_width: float,
  ) -> float:
    max_left = max(frame_width - width, 0.0)
    if anchor.allow_horizontal_shift:
      center_x = anchor.x if anchor.x is not None else (bbox['x'] + bbox['width'] / 2)
      return clip_value(center_x - width / 2, 0.0, max_left)
    return clip_value(bbox['x'], 0.0, max_left)
