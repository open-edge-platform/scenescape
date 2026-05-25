# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Person bounding-box adjustment using pose keypoints and learned body proportions."""

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from controller.pose_adjustment.core.bbox_utils import (clip_point,
                                                        coerce_bbox,
                                                        scale_bbox)
from controller.pose_adjustment.core.bbox_rewrite_policy import (BoundingBoxRewritePolicy,
                                                                 BoundingBoxRewriteThresholds)
from controller.pose_adjustment.strategies.person.named_keypoints import (NamedKeypoint, head_point,
                                                                          midpoint, parse_named_keypoints,
                                                                          scale_keypoints)
from controller.pose_adjustment.strategies.person.proportion_cache import ProportionCache
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
class ProportionRule:
  """Rule mapping a pair of body landmarks to a learned ankle-position ratio."""

  ratio_name: str
  default_ratio: float
  denom_top_key: str
  denom_bottom_key: str
  anchor_is_bottom: bool
  method: str
  learn_x_offset_name: Optional[str] = None
  estimate_x_offset_name: Optional[str] = None
  exclude_if_present: Optional[str] = None


PROPORTION_RULES = (
  ProportionRule(
    ratio_name='ratio_ankle_knee_hip',
    default_ratio=DEFAULT_RATIO_ANKLE_KNEE_HIP,
    denom_top_key='hip_mid',
    denom_bottom_key='knee_mid',
    anchor_is_bottom=True,
    method='estimated_knee_hip',
    learn_x_offset_name='x_offset_from_knee',
    estimate_x_offset_name='x_offset_from_knee',
  ),
  ProportionRule(
    ratio_name='ratio_ankle_nose_hip',
    default_ratio=DEFAULT_RATIO_ANKLE_NOSE_HIP,
    denom_top_key='nose',
    denom_bottom_key='hip_mid',
    anchor_is_bottom=False,
    method='estimated_nose_hip',
    learn_x_offset_name='x_offset_from_hip',
    estimate_x_offset_name='x_offset_from_hip',
  ),
  ProportionRule(
    ratio_name='ratio_ankle_head_hip',
    default_ratio=DEFAULT_RATIO_ANKLE_HEAD_HIP,
    denom_top_key='head',
    denom_bottom_key='hip_mid',
    anchor_is_bottom=False,
    method='estimated_head_hip',
    estimate_x_offset_name='x_offset_from_hip',
    exclude_if_present='nose',
  ),
  ProportionRule(
    ratio_name='ratio_ankle_shoulder_hip',
    default_ratio=DEFAULT_RATIO_ANKLE_SHOULDER_HIP,
    denom_top_key='shoulder_mid',
    denom_bottom_key='hip_mid',
    anchor_is_bottom=False,
    method='estimated_shoulder_hip',
    learn_x_offset_name='x_offset_from_torso',
    estimate_x_offset_name='x_offset_from_torso',
  ),
  ProportionRule(
    ratio_name='ratio_ankle_nose_shoulder',
    default_ratio=DEFAULT_RATIO_ANKLE_NOSE_SHOULDER,
    denom_top_key='nose',
    denom_bottom_key='shoulder_mid',
    anchor_is_bottom=False,
    method='estimated_nose_shoulder',
  ),
)


@dataclass(frozen=True)
class FootEstimate:
  """Estimated or directly observed foot position for a person detection."""

  x: float
  y: float
  method: str
  learning_x: Optional[float] = None
  confidence: Optional[float] = None
  direct_observation_count: int = 0
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
    self._rewrite_policy = BoundingBoxRewritePolicy(
      thresholds=BoundingBoxRewriteThresholds(
        direct_safety_margin=BBOX_BOTTOM_SAFETY_MARGIN_DIRECT,
        estimated_safety_margin=BBOX_BOTTOM_SAFETY_MARGIN_ESTIMATED,
        direct_gap_factor=DIRECT_FOOT_REWRITE_GAP_FACTOR,
        estimated_gap_factor=ESTIMATED_FOOT_REWRITE_GAP_FACTOR,
        min_estimate_confidence_threshold=MIN_ESTIMATE_CONFIDENCE_THRESHOLD,
        low_confidence_estimation_methods=LOW_CONFIDENCE_ESTIMATION_METHODS,
      ),
      has_likely_occlusion_signal=self._has_likely_occlusion_signal,
    )

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    """Update the maximum age before a cached proportion entry is pruned."""
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
    if not isinstance(detection, dict) or detection.get('category') != 'person':
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

    normalized_bbox = coerce_bbox(detection.get('bounding_box'))
    pixel_bbox = coerce_bbox(detection.get('bounding_box_px'))
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
      method = self._apply_normalized_bbox(
        detection, normalized_bbox, pixel_bbox, keypoints, cache_key, when, resolution,
      )
    elif pixel_bbox is not None:
      method = self._apply_pixel_bbox(
        detection, pixel_bbox, keypoints, cache_key, when, resolution,
      )
    else:
      log.debug(f"Skipping pose adjustment for {cache_key}: no usable bbox fields")
      return False

    if method is None:
      return False
    log.debug(
      f"Adjusted person bbox for camera {camera_id} detection {detection_id} using {method}"
    )
    return True

  def _apply_normalized_bbox(
    self, detection, normalized_bbox, pixel_bbox, keypoints, cache_key, when, resolution,
  ) -> Optional[str]:
    """Attempt pose adjustment in normalized coordinate space."""
    frame_keypoints = scale_keypoints(keypoints, None, normalized_bbox)
    adjusted_bbox, method = self._adjust_bbox(
      normalized_bbox, frame_keypoints, cache_key, when, bounds=(1.0, 1.0),
    )
    if adjusted_bbox is None:
      log.debug(
        f"No normalized-space pose adjustment produced for {cache_key}: "
        f"bbox={normalized_bbox}"
      )
      return None

    detection['bounding_box'] = adjusted_bbox
    if pixel_bbox is not None:
      derived_pixel_bbox = scale_bbox(adjusted_bbox, resolution)
      if derived_pixel_bbox is not None:
        detection['bounding_box_px'] = derived_pixel_bbox
      else:
        detection.pop('bounding_box_px', None)
    log.debug(
      f"Adjusted normalized bbox for {cache_key} using {method}: "
      f"before={normalized_bbox}, after={adjusted_bbox}, "
      f"pixel_bbox={detection.get('bounding_box_px')}"
    )
    return method

  def _apply_pixel_bbox(
    self, detection, pixel_bbox, keypoints, cache_key, when, resolution,
  ) -> Optional[str]:
    """Attempt pose adjustment in pixel coordinate space."""
    if resolution is None or len(resolution) != 2:
      log.debug(
        f"Skipping pixel-space pose adjustment for {cache_key}: missing resolution"
      )
      return None
    pixel_keypoints = scale_keypoints(keypoints, resolution, pixel_bbox)
    adjusted_bbox, method = self._adjust_bbox(
      pixel_bbox, pixel_keypoints, cache_key, when, bounds=resolution,
    )
    if adjusted_bbox is None:
      log.debug(
        f"No pixel-space pose adjustment produced for {cache_key}: "
        f"bbox={pixel_bbox}"
      )
      return None

    detection['bounding_box_px'] = adjusted_bbox
    detection.pop('bounding_box', None)
    log.debug(
      f"Adjusted pixel bbox for {cache_key} using {method}: "
      f"before={pixel_bbox}, after={adjusted_bbox}"
    )
    return method

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

    if not self._rewrite_policy.should_rewrite_bbox(bbox, keypoints, estimated_foot):
      log.debug(
        f"Skipping bbox rewrite for {cache_key}: estimated foot does not indicate likely occlusion"
      )
      return None, None

    log.debug(
      f"Using estimated foot for {cache_key}: "
      f"method={estimated_foot.method}, x={estimated_foot.x:.4f}, y={estimated_foot.y:.4f}"
    )
    return self._rewrite_policy.rewrite_bbox(bbox, estimated_foot, bounds), estimated_foot.method

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
        direct_observation_count=2,
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
      direct_observation_count=1,
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

    near_bottom = (ankle.y <= box_bottom
                   and (box_bottom - ankle.y) <= bbox['height'] * FOOT_NEAR_BOX_BOTTOM_MARGIN)
    if near_bottom:
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

  def _resolve_landmarks(
    self,
    keypoints: Dict[str, NamedKeypoint],
  ) -> Dict[str, Optional[NamedKeypoint]]:
    return {
      'nose': keypoints.get('nose'),
      'head': head_point(keypoints),
      'shoulder_mid': midpoint(keypoints, 'left_shoulder', 'right_shoulder'),
      'hip_mid': midpoint(keypoints, 'left_hip', 'right_hip'),
      'knee_mid': midpoint(keypoints, 'left_knee', 'right_knee'),
    }

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
    landmarks = self._resolve_landmarks(keypoints)
    min_segment = max(bbox['height'] * MIN_SEGMENT_FACTOR, 1e-6)
    allow_x_offset = foot.direct_observation_count >= 2 and foot.allow_horizontal_shift
    filtered_ratios = self._compute_ratios(
      landmarks, min_segment, ankle_x, ankle_y, allow_x_offset,
    )

    log.debug(
      f"Learning pose proportions for {cache_key}: filtered={filtered_ratios}"
    )
    self.cache.add_observation(cache_key, filtered_ratios, when)

  def _compute_ratios(
    self, landmarks, min_segment, ankle_x, ankle_y, allow_x_offset,
  ) -> Dict[str, float]:
    """Compute body-proportion ratios from landmarks and ankle position."""
    ratios = {}
    for rule in PROPORTION_RULES:
      top = landmarks.get(rule.denom_top_key)
      bottom = landmarks.get(rule.denom_bottom_key)
      if top is None or bottom is None:
        continue
      if rule.exclude_if_present and landmarks.get(rule.exclude_if_present) is not None:
        continue
      denom = bottom.y - top.y
      if denom <= min_segment:
        continue
      anchor = bottom if rule.anchor_is_bottom else top
      ratios[rule.ratio_name] = (ankle_y - anchor.y) / denom
      if allow_x_offset and rule.learn_x_offset_name is not None:
        ratios[rule.learn_x_offset_name] = (ankle_x - bottom.x) / denom

    return {
      name: value for name, value in ratios.items()
      if math.isfinite(value)
      and abs(value) <= (MAX_OFFSET_VALUE if name.startswith('x_offset_') else MAX_RATIO_VALUE)
    }

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
    landmarks = self._resolve_landmarks(keypoints)
    min_segment = max(bbox['height'] * MIN_SEGMENT_FACTOR, 1e-6)
    result = self._estimate_foot_from_rules(landmarks, props, min_segment)

    if result is None:
      hip_mid = landmarks.get('hip_mid')
      if hip_mid is not None:
        result = (hip_mid.x, hip_mid.y + bbox['height'] * 0.55,
                  hip_mid.confidence, 'estimated_hip')

    if result is None:
      log.debug(f"Unable to estimate foot for {cache_key}: insufficient usable joints")
      return None

    est_x, est_y, confidence, method = result
    est_x, est_y = clip_point(est_x, est_y, bounds)
    log.debug(
      f"Estimated foot for {cache_key}: method={method}, x={est_x:.4f}, y={est_y:.4f}"
    )
    return FootEstimate(
      est_x,
      est_y,
      method,
      confidence=confidence,
      direct_observation_count=0,
      allow_horizontal_shift=False,
    )

  def _estimate_foot_from_rules(
    self, landmarks, props, min_segment,
  ) -> Optional[Tuple[float, float, Optional[float], str]]:
    """Find the first matching proportion rule and return (x, y, confidence, method)."""
    for rule in PROPORTION_RULES:
      top = landmarks.get(rule.denom_top_key)
      bottom = landmarks.get(rule.denom_bottom_key)
      if top is None or bottom is None:
        continue
      if rule.exclude_if_present and landmarks.get(rule.exclude_if_present) is not None:
        continue
      denom = bottom.y - top.y
      if denom <= min_segment:
        continue
      ratio = props.get(rule.ratio_name, rule.default_ratio)
      anchor = bottom if rule.anchor_is_bottom else top
      est_y = anchor.y + ratio * denom
      if rule.estimate_x_offset_name is not None:
        x_offset = props.get(rule.estimate_x_offset_name, DEFAULT_X_OFFSET)
        est_x = bottom.x + x_offset * denom
      else:
        est_x = bottom.x
      confidence = self._mean_confidence([top, bottom])
      return (est_x, est_y, confidence, rule.method)
    return None

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
