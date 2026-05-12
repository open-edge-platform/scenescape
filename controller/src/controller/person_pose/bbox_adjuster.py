# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from controller.person_pose.named_keypoints import (NamedKeypoint, head_point,
                                                    midpoint, parse_named_keypoints,
                                                    scale_keypoints)
from controller.person_pose.proportion_cache import ProportionCache
from scene_common import log


DEFAULT_RATIO_ANKLE_NOSE_HIP = 2.0
DEFAULT_RATIO_ANKLE_SHOULDER_HIP = 2.5
DEFAULT_RATIO_ANKLE_NOSE_SHOULDER = 4.0
DEFAULT_RATIO_ANKLE_HEAD_HIP = 2.0
DEFAULT_RATIO_ANKLE_KNEE_HIP = 1.0
DEFAULT_X_OFFSET = 0.0

FOOT_NEAR_BOX_BOTTOM_MARGIN = 0.08
BBOX_BOTTOM_SAFETY_MARGIN_DIRECT = 0.0
BBOX_BOTTOM_SAFETY_MARGIN_ESTIMATED = 0.01
IDENTICAL_ANKLE_DISTANCE_FACTOR = 0.02
MIN_SEGMENT_FACTOR = 0.05
MAX_RATIO_VALUE = 10.0
MAX_OFFSET_VALUE = 5.0
DIRECT_FOOT_REWRITE_GAP_FACTOR = 0.25
ESTIMATED_FOOT_REWRITE_GAP_FACTOR = 0.20
DIRECT_ESTIMATE_DISAGREEMENT_FACTOR = 0.15
HIGH_CONFIDENCE_THRESHOLD = 0.6
MIN_ESTIMATE_CONFIDENCE_THRESHOLD = 0.4
LOW_CONFIDENCE_ESTIMATION_METHODS = {
  'estimated_hip',
  'estimated_nose_shoulder',
}


@dataclass(frozen=True)
class FootEstimate:
  x: float
  y: float
  method: str
  learning_x: Optional[float] = None
  confidence: Optional[float] = None
  visible_ankles: int = 0
  allow_horizontal_shift: bool = False


class PersonPoseAdjuster:
  """Rewrite person bounding boxes using pose keypoints and learned proportions."""

  def __init__(
    self,
    max_samples: int = 20,
    max_entry_age_seconds: float = 10.0,
    min_observations: int = 3,
  ):
    self.cache = ProportionCache(max_samples, max_entry_age_seconds, min_observations)

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    self.cache.set_max_entry_age_seconds(max_entry_age_seconds)

  def adjust_detection(
    self,
    detection: dict,
    scene_name: str,
    camera_id: str,
    when: float,
    resolution=None,
  ) -> bool:
    """Adjust a person detection in place when enough pose information is available."""
    if not isinstance(detection, dict):
      return False
    if detection.get('category') != 'person':
      return False

    detection_id = detection.get('id')
    if detection_id is None:
      log.debug(
        f"Skipping pose adjustment for camera {camera_id}: person detection missing id"
      )
      return False

    keypoints = parse_named_keypoints(detection.get('keypoints'))
    if not keypoints:
      log.debug(
        f"Skipping pose adjustment for camera {camera_id} detection {detection_id}: "
        "no usable keypoints"
      )
      return False

    cache_key = (scene_name, camera_id, str(detection_id))
    self.cache.prune(when)
    self.cache.mark_seen(cache_key, when)

    adjusted_bbox = None
    method = None

    normalized_bbox = self._coerce_bbox(detection.get('bounding_box'))
    pixel_bbox = self._coerce_bbox(detection.get('bounding_box_px'))
    bbox_mode = (
      'normalized' if normalized_bbox is not None
      else 'pixel' if pixel_bbox is not None
      else 'none'
    )
    log.debug(
      f"Pose adjustment input for {cache_key}: "
      f"bbox_mode={bbox_mode}, joints={sorted(keypoints.keys())}, resolution={resolution}"
    )

    if normalized_bbox is not None:
      frame_keypoints = scale_keypoints(keypoints, None, normalized_bbox)
      adjusted_bbox, method = self._adjust_bbox(
        normalized_bbox,
        frame_keypoints,
        cache_key,
        when,
        bounds=(1.0, 1.0),
      )
      if adjusted_bbox is None:
        log.debug(
          f"No normalized-space pose adjustment produced for {cache_key}: "
          f"bbox={normalized_bbox}"
        )
        return False

      detection['bounding_box'] = adjusted_bbox
      if pixel_bbox is not None:
        derived_pixel_bbox = self._scale_bbox(adjusted_bbox, resolution)
        if derived_pixel_bbox is not None:
          detection['bounding_box_px'] = derived_pixel_bbox
        else:
          detection.pop('bounding_box_px', None)
      log.debug(
        f"Adjusted normalized bbox for {cache_key} using {method}: "
        f"before={normalized_bbox}, after={adjusted_bbox}, "
        f"pixel_bbox={detection.get('bounding_box_px')}"
      )
    elif pixel_bbox is not None:
      if resolution is None or len(resolution) != 2:
        log.debug(
          f"Skipping pixel-space pose adjustment for {cache_key}: missing resolution"
        )
        return False
      pixel_keypoints = scale_keypoints(keypoints, resolution, pixel_bbox)
      adjusted_bbox, method = self._adjust_bbox(
        pixel_bbox,
        pixel_keypoints,
        cache_key,
        when,
        bounds=resolution,
      )
      if adjusted_bbox is None:
        log.debug(
          f"No pixel-space pose adjustment produced for {cache_key}: "
          f"bbox={pixel_bbox}"
        )
        return False

      detection['bounding_box_px'] = adjusted_bbox
      detection.pop('bounding_box', None)
      log.debug(
        f"Adjusted pixel bbox for {cache_key} using {method}: "
        f"before={pixel_bbox}, after={adjusted_bbox}"
      )
    else:
      log.debug(f"Skipping pose adjustment for {cache_key}: no usable bbox fields")
      return False

    if method is not None:
      log.debug(
        f"Adjusted person bbox for camera {camera_id} detection {detection_id} using {method}"
      )
    return True

  def _adjust_bbox(
    self,
    bbox: Dict[str, float],
    keypoints: Dict[str, NamedKeypoint],
    cache_key: Tuple[str, str, str],
    when: float,
    bounds,
  ) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
    direct_foot = self._direct_foot_estimate(bbox, keypoints)
    if direct_foot is not None:
      estimated_foot = self._estimate_foot(cache_key, keypoints, bbox, bounds)
      if estimated_foot is not None:
        disagreement = estimated_foot.y - direct_foot.y
        threshold = bbox['height'] * DIRECT_ESTIMATE_DISAGREEMENT_FACTOR
        if disagreement > threshold:
          log.debug(
            f"Discarding direct foot for {cache_key}: "
            f"estimated_y={estimated_foot.y:.4f} >> direct_y={direct_foot.y:.4f} "
            f"(disagreement={disagreement:.4f} > threshold={threshold:.4f}), "
            f"ankles likely hallucinated"
          )
          direct_foot = None

    if direct_foot is not None:
      log.debug(
        f"Using direct foot estimate for {cache_key}: "
        f"method={direct_foot.method}, x={direct_foot.x:.4f}, y={direct_foot.y:.4f}"
      )
      self._learn_person_proportions(cache_key, keypoints, bbox, direct_foot, when)
      # Visible ankles means person's feet are in frame — not occluded from below.
      # Only learn proportions; never rewrite bbox based on direct ankle observation.
      return None, None

    estimated_foot = self._estimate_foot(cache_key, keypoints, bbox, bounds)
    if estimated_foot is None:
      log.debug(f"No pose-based foot estimate available for {cache_key}: bbox={bbox}")
      return None, None

    if not self._should_rewrite_bbox(bbox, keypoints, estimated_foot):
      log.debug(
        f"Skipping bbox rewrite for {cache_key}: estimated foot does not indicate likely occlusion"
      )
      return None, None

    log.debug(
      f"Using estimated foot for {cache_key}: "
      f"method={estimated_foot.method}, x={estimated_foot.x:.4f}, y={estimated_foot.y:.4f}"
    )
    return self._rewrite_bbox(bbox, estimated_foot, bounds), estimated_foot.method

  def _direct_foot_estimate(
    self,
    bbox: Dict[str, float],
    keypoints: Dict[str, NamedKeypoint],
  ) -> Optional[FootEstimate]:
    left_ankle = keypoints.get('left_ankle')
    right_ankle = keypoints.get('right_ankle')
    candidates = []

    if left_ankle is not None and self._is_valid_ankle(
      'left_ankle', left_ankle, bbox, keypoints
    ):
      candidates.append(left_ankle)
    if right_ankle is not None and self._is_valid_ankle(
      'right_ankle', right_ankle, bbox, keypoints
    ):
      candidates.append(right_ankle)

    if len(candidates) == 2 and self._are_ankles_identical(candidates[0], candidates[1], bbox):
      log.debug(
        f"Rejecting direct foot estimate: ankles are nearly identical for bbox={bbox}"
      )
      return None
    if not candidates:
      log.debug(f"No valid ankle candidates for bbox={bbox}")
      return None

    foot_y = max(point.y for point in candidates)
    if len(candidates) == 2:
      foot_x = sum(point.x for point in candidates) / 2
      confidence = self._mean_confidence(candidates)
      return FootEstimate(
        foot_x,
        foot_y,
        'detected_ankles',
        learning_x=foot_x,
        confidence=confidence,
        visible_ankles=2,
        allow_horizontal_shift=self._is_high_confidence(confidence),
      )

    bbox_center_x = bbox['x'] + bbox['width'] / 2
    confidence = self._mean_confidence(candidates)
    return FootEstimate(
      bbox_center_x,
      foot_y,
      'detected_single_ankle',
      learning_x=candidates[0].x,
      confidence=confidence,
      visible_ankles=1,
      allow_horizontal_shift=False,
    )

  def _is_valid_ankle(
    self,
    ankle_name: str,
    ankle: NamedKeypoint,
    bbox: Dict[str, float],
    keypoints: Dict[str, NamedKeypoint],
  ) -> bool:
    side = 'left' if ankle_name.startswith('left') else 'right'
    same_hip = keypoints.get(f'{side}_hip')
    same_knee = keypoints.get(f'{side}_knee')
    hip_ref = same_hip or midpoint(keypoints, 'left_hip', 'right_hip')
    knee_ref = same_knee or midpoint(keypoints, 'left_knee', 'right_knee')
    box_bottom = bbox['y'] + bbox['height']
    min_segment = max(bbox['height'] * MIN_SEGMENT_FACTOR, 1e-6)

    if hip_ref is not None and ankle.y <= hip_ref.y:
      log.debug(
        f"Rejecting {ankle_name}: ankle_y={ankle.y:.4f} is above hip_y={hip_ref.y:.4f}"
      )
      return False
    if knee_ref is not None and ankle.y <= knee_ref.y:
      log.debug(
        f"Rejecting {ankle_name}: ankle_y={ankle.y:.4f} is above knee_y={knee_ref.y:.4f}"
      )
      return False

    if ankle.y <= box_bottom and (box_bottom - ankle.y) <= bbox['height'] * FOOT_NEAR_BOX_BOTTOM_MARGIN:
      if knee_ref is None or (ankle.y - knee_ref.y) <= min_segment:
        log.debug(
          f"Rejecting {ankle_name}: near bbox bottom without enough separation "
          f"(ankle_y={ankle.y:.4f}, box_bottom={box_bottom:.4f})"
        )
        return False

    return True

  def _are_ankles_identical(
    self,
    left_ankle: NamedKeypoint,
    right_ankle: NamedKeypoint,
    bbox: Dict[str, float],
  ) -> bool:
    threshold = max(min(bbox['width'], bbox['height']) * IDENTICAL_ANKLE_DISTANCE_FACTOR, 1e-6)
    return math.hypot(left_ankle.x - right_ankle.x, left_ankle.y - right_ankle.y) < threshold

  def _learn_person_proportions(
    self,
    cache_key: Tuple[str, str, str],
    keypoints: Dict[str, NamedKeypoint],
    bbox: Dict[str, float],
    foot: FootEstimate,
    when: float,
  ) -> None:
    ankle_x = foot.learning_x if foot.learning_x is not None else foot.x
    ankle_y = foot.y
    nose = keypoints.get('nose')
    head = head_point(keypoints)
    shoulder_mid = midpoint(keypoints, 'left_shoulder', 'right_shoulder')
    hip_mid = midpoint(keypoints, 'left_hip', 'right_hip')
    knee_mid = midpoint(keypoints, 'left_knee', 'right_knee')
    min_segment = max(bbox['height'] * MIN_SEGMENT_FACTOR, 1e-6)
    ratios = {}
    allow_x_offset_learning = foot.visible_ankles >= 2 and foot.allow_horizontal_shift

    if nose is not None and hip_mid is not None:
      denom = hip_mid.y - nose.y
      if denom > min_segment:
        ratios['ratio_ankle_nose_hip'] = (ankle_y - nose.y) / denom
        if allow_x_offset_learning:
          ratios['x_offset_from_hip'] = (ankle_x - hip_mid.x) / denom

    if shoulder_mid is not None and hip_mid is not None:
      denom = hip_mid.y - shoulder_mid.y
      if denom > min_segment:
        ratios['ratio_ankle_shoulder_hip'] = (ankle_y - shoulder_mid.y) / denom
        if allow_x_offset_learning:
          ratios['x_offset_from_torso'] = (ankle_x - hip_mid.x) / denom

    if nose is not None and shoulder_mid is not None:
      denom = shoulder_mid.y - nose.y
      if denom > min_segment:
        ratios['ratio_ankle_nose_shoulder'] = (ankle_y - nose.y) / denom

    if head is not None and hip_mid is not None and nose is None:
      denom = hip_mid.y - head.y
      if denom > min_segment:
        ratios['ratio_ankle_head_hip'] = (ankle_y - head.y) / denom

    if knee_mid is not None and hip_mid is not None:
      denom = knee_mid.y - hip_mid.y
      if denom > min_segment:
        ratios['ratio_ankle_knee_hip'] = (ankle_y - knee_mid.y) / denom
        if allow_x_offset_learning:
          ratios['x_offset_from_knee'] = (ankle_x - knee_mid.x) / denom

    filtered_ratios = {}
    for name, value in ratios.items():
      if not math.isfinite(value):
        continue
      abs_limit = MAX_OFFSET_VALUE if name.startswith('x_offset_') else MAX_RATIO_VALUE
      if abs(value) > abs_limit:
        continue
      filtered_ratios[name] = value

    log.debug(
      f"Learning pose proportions for {cache_key}: raw={ratios}, filtered={filtered_ratios}"
    )
    self.cache.add_observation(cache_key, filtered_ratios, when)

  def _estimate_foot(
    self,
    cache_key: Tuple[str, str, str],
    keypoints: Dict[str, NamedKeypoint],
    bbox: Dict[str, float],
    bounds,
  ) -> Optional[FootEstimate]:
    props = self.cache.get_medians(cache_key)
    if not props:
      log.debug(
        f"Skipping foot estimation for {cache_key}: "
        "proportion cache not yet warmed up"
      )
      return None
    nose = keypoints.get('nose')
    head = head_point(keypoints)
    shoulder_mid = midpoint(keypoints, 'left_shoulder', 'right_shoulder')
    hip_mid = midpoint(keypoints, 'left_hip', 'right_hip')
    knee_mid = midpoint(keypoints, 'left_knee', 'right_knee')
    min_segment = max(bbox['height'] * MIN_SEGMENT_FACTOR, 1e-6)
    est_x = None
    est_y = None
    method = None

    if knee_mid is not None and hip_mid is not None:
      denom = knee_mid.y - hip_mid.y
      if denom > min_segment:
        ratio = props.get('ratio_ankle_knee_hip', DEFAULT_RATIO_ANKLE_KNEE_HIP)
        x_offset = props.get('x_offset_from_knee', DEFAULT_X_OFFSET)
        est_y = knee_mid.y + ratio * denom
        est_x = knee_mid.x + x_offset * denom
        confidence = self._mean_confidence([knee_mid, hip_mid])
        method = 'estimated_knee_hip'

    if est_y is None and nose is not None and hip_mid is not None:
      denom = hip_mid.y - nose.y
      if denom > min_segment:
        ratio = props.get('ratio_ankle_nose_hip', DEFAULT_RATIO_ANKLE_NOSE_HIP)
        x_offset = props.get('x_offset_from_hip', DEFAULT_X_OFFSET)
        est_y = nose.y + ratio * denom
        est_x = hip_mid.x + x_offset * denom
        confidence = self._mean_confidence([nose, hip_mid])
        method = 'estimated_nose_hip'

    if est_y is None and head is not None and hip_mid is not None and nose is None:
      denom = hip_mid.y - head.y
      if denom > min_segment:
        ratio = props.get('ratio_ankle_head_hip', DEFAULT_RATIO_ANKLE_HEAD_HIP)
        x_offset = props.get('x_offset_from_hip', DEFAULT_X_OFFSET)
        est_y = head.y + ratio * denom
        est_x = hip_mid.x + x_offset * denom
        confidence = self._mean_confidence([head, hip_mid])
        method = 'estimated_head_hip'

    if est_y is None and shoulder_mid is not None and hip_mid is not None:
      denom = hip_mid.y - shoulder_mid.y
      if denom > min_segment:
        ratio = props.get('ratio_ankle_shoulder_hip', DEFAULT_RATIO_ANKLE_SHOULDER_HIP)
        x_offset = props.get('x_offset_from_torso', DEFAULT_X_OFFSET)
        est_y = shoulder_mid.y + ratio * denom
        est_x = hip_mid.x + x_offset * denom
        confidence = self._mean_confidence([shoulder_mid, hip_mid])
        method = 'estimated_shoulder_hip'

    if est_y is None and nose is not None and shoulder_mid is not None:
      denom = shoulder_mid.y - nose.y
      if denom > min_segment:
        ratio = props.get('ratio_ankle_nose_shoulder', DEFAULT_RATIO_ANKLE_NOSE_SHOULDER)
        est_y = nose.y + ratio * denom
        est_x = shoulder_mid.x
        confidence = self._mean_confidence([nose, shoulder_mid])
        method = 'estimated_nose_shoulder'

    if est_y is None and hip_mid is not None:
      est_y = hip_mid.y + bbox['height'] * 0.55
      est_x = hip_mid.x
      confidence = hip_mid.confidence
      method = 'estimated_hip'

    if est_y is None or est_x is None:
      log.debug(f"Unable to estimate foot for {cache_key}: insufficient usable joints")
      return None

    est_x, est_y = self._clip_point(est_x, est_y, bounds)
    log.debug(
      f"Estimated foot for {cache_key}: method={method}, x={est_x:.4f}, y={est_y:.4f}"
    )
    return FootEstimate(
      est_x,
      est_y,
      method,
      confidence=confidence,
      visible_ankles=0,
      allow_horizontal_shift=False,
    )

  def _should_rewrite_bbox(
    self,
    bbox: Dict[str, float],
    keypoints: Dict[str, NamedKeypoint],
    foot: FootEstimate,
  ) -> bool:
    box_bottom = bbox['y'] + bbox['height']
    safety_margin = (
      BBOX_BOTTOM_SAFETY_MARGIN_DIRECT if foot.visible_ankles > 0
      else BBOX_BOTTOM_SAFETY_MARGIN_ESTIMATED
    )
    desired_bottom = foot.y + bbox['height'] * safety_margin
    required_extension = desired_bottom - box_bottom
    min_extension = bbox['height'] * (
      DIRECT_FOOT_REWRITE_GAP_FACTOR if foot.visible_ankles > 0
      else ESTIMATED_FOOT_REWRITE_GAP_FACTOR
    )

    if required_extension <= min_extension:
      log.debug(
        f"Skipping bbox rewrite for {foot.method}: extension={required_extension:.4f} "
        f"threshold={min_extension:.4f}"
      )
      return False

    if foot.visible_ankles > 0:
      return True

    if foot.method in LOW_CONFIDENCE_ESTIMATION_METHODS:
      log.debug(f"Skipping bbox rewrite for {foot.method}: low-confidence estimate method")
      return False

    if foot.confidence is not None and foot.confidence < MIN_ESTIMATE_CONFIDENCE_THRESHOLD:
      log.debug(
        f"Skipping bbox rewrite for {foot.method}: estimate confidence={foot.confidence:.4f}"
      )
      return False

    if not self._has_likely_occlusion_signal(keypoints, bbox):
      log.debug(
        f"Skipping bbox rewrite for {foot.method}: pose pattern does not suggest occlusion"
      )
      return False

    return True

  def _has_likely_occlusion_signal(
    self,
    keypoints: Dict[str, NamedKeypoint],
    bbox: Dict[str, float],
  ) -> bool:
    left_ankle = keypoints.get('left_ankle')
    right_ankle = keypoints.get('right_ankle')

    has_valid_ankle = False
    if left_ankle is not None and self._is_valid_ankle(
      'left_ankle', left_ankle, bbox, keypoints
    ):
      has_valid_ankle = True
    if right_ankle is not None and self._is_valid_ankle(
      'right_ankle', right_ankle, bbox, keypoints
    ):
      has_valid_ankle = True

    if has_valid_ankle:
      return False

    knee_mid = midpoint(keypoints, 'left_knee', 'right_knee')
    hip_mid = midpoint(keypoints, 'left_hip', 'right_hip')
    shoulder_mid = midpoint(keypoints, 'left_shoulder', 'right_shoulder')
    head = head_point(keypoints)

    if knee_mid is not None and hip_mid is not None:
      return True

    if hip_mid is not None and (shoulder_mid is not None or head is not None):
      return True

    return False

  def _rewrite_bbox(
    self,
    bbox: Dict[str, float],
    foot: FootEstimate,
    bounds,
  ) -> Dict[str, float]:
    frame_width, frame_height = self._bounds(bounds)
    safety_margin = (
      BBOX_BOTTOM_SAFETY_MARGIN_DIRECT if foot.visible_ankles > 0
      else BBOX_BOTTOM_SAFETY_MARGIN_ESTIMATED
    )
    original_bottom = bbox['y'] + bbox['height']
    desired_bottom = foot.y + bbox['height'] * safety_margin
    bottom_y = max(original_bottom, desired_bottom)

    width = min(bbox['width'], frame_width)
    top_y = self._clip_value(bbox['y'], 0.0, frame_height)
    if foot.allow_horizontal_shift:
      center_x = foot.x if foot.x is not None else (bbox['x'] + bbox['width'] / 2)
      left_x = self._clip_value(center_x - width / 2, 0.0, max(frame_width - width, 0.0))
    else:
      left_x = self._clip_value(bbox['x'], 0.0, max(frame_width - width, 0.0))
    bottom_y = self._clip_value(bottom_y, top_y, frame_height)
    height = max(bottom_y - top_y, bbox['height'])
    height = min(height, frame_height - top_y)

    adjusted_bbox = {
      'x': left_x,
      'y': top_y,
      'width': width,
      'height': height,
    }

    if frame_width > 1.0 or frame_height > 1.0:
      final_bbox = {
        'x': int(round(adjusted_bbox['x'])),
        'y': int(round(adjusted_bbox['y'])),
        'width': int(round(adjusted_bbox['width'])),
        'height': int(round(adjusted_bbox['height'])),
      }
    else:
      final_bbox = {
        key: round(value, 6) for key, value in adjusted_bbox.items()
      }

    log.debug(
      f"Rewriting bbox using {foot.method}: before={bbox}, after={final_bbox}, "
      f"foot=({foot.x:.4f}, {foot.y:.4f}), shift_x={foot.allow_horizontal_shift}"
    )
    return final_bbox

  def _mean_confidence(self, keypoints) -> Optional[float]:
    confidences = [
      keypoint.confidence for keypoint in keypoints
      if keypoint is not None and keypoint.confidence is not None
    ]
    if not confidences:
      return None
    return sum(confidences) / len(confidences)

  def _is_high_confidence(self, confidence: Optional[float]) -> bool:
    return confidence is not None and confidence >= HIGH_CONFIDENCE_THRESHOLD

  def _scale_bbox(self, bbox: Dict[str, float], resolution) -> Optional[Dict[str, int]]:
    if resolution is None or len(resolution) != 2:
      return None
    width, height = float(resolution[0]), float(resolution[1])
    scaled_bbox = {
      'x': bbox['x'] * width,
      'y': bbox['y'] * height,
      'width': bbox['width'] * width,
      'height': bbox['height'] * height,
    }
    return {
      key: int(round(value)) for key, value in scaled_bbox.items()
    }

  def _coerce_bbox(self, bbox) -> Optional[Dict[str, float]]:
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

  def _clip_point(self, x_coord: float, y_coord: float, bounds) -> Tuple[float, float]:
    frame_width, frame_height = self._bounds(bounds)
    return (
      self._clip_value(x_coord, 0.0, frame_width),
      self._clip_value(y_coord, 0.0, frame_height),
    )

  def _clip_value(self, value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))

  def _bounds(self, bounds) -> Tuple[float, float]:
    if bounds is None or len(bounds) != 2:
      return (1.0, 1.0)
    return (float(bounds[0]), float(bounds[1]))
