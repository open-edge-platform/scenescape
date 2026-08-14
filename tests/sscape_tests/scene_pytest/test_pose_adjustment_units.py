#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the pose_adjustment module components.

Covers the individual building-block modules in isolation:
  - core/bbox_utils.py
  - core/bbox_rewrite_policy.py
  - strategies/person/named_keypoints.py
  - strategies/person/proportion_cache.py
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from controller.pose_adjustment.core.bbox_utils import (
  bounds,
  clip_point,
  clip_value,
  coerce_bbox,
  quantize_bbox,
  scale_bbox,
)
from controller.pose_adjustment.core.bbox_rewrite_policy import (
  BoundingBoxRewritePolicy,
  BoundingBoxRewriteThresholds,
)
from controller.pose_adjustment.strategies.person.named_keypoints import (
  NamedKeypoint,
  canonical_joint_name,
  keypoints_are_normalized,
  parse_named_keypoints,
  scale_keypoints,
)
from controller.pose_adjustment.strategies.person.proportion_cache import (
  PersonProportionEntry,
  ProportionCache,
)


# ---------------------------------------------------------------------------
# TestCoerceBbox
# ---------------------------------------------------------------------------

class TestCoerceBbox:
  def test_valid_dict_returns_floats(self):
    result = coerce_bbox({'x': 10, 'y': 20, 'width': 100, 'height': 200})
    assert result == {'x': 10.0, 'y': 20.0, 'width': 100.0, 'height': 200.0}

  def test_none_returns_none(self):
    assert coerce_bbox(None) is None

  def test_non_dict_returns_none(self):
    assert coerce_bbox([1, 2, 3, 4]) is None

  def test_missing_key_returns_none(self):
    assert coerce_bbox({'x': 1, 'y': 2, 'width': 10}) is None

  def test_zero_width_returns_none(self):
    assert coerce_bbox({'x': 0, 'y': 0, 'width': 0, 'height': 10}) is None

  def test_negative_height_returns_none(self):
    assert coerce_bbox({'x': 0, 'y': 0, 'width': 10, 'height': -1}) is None

  def test_string_numeric_values_are_coerced(self):
    result = coerce_bbox({'x': '5', 'y': '10', 'width': '50', 'height': '100'})
    assert result == {'x': 5.0, 'y': 10.0, 'width': 50.0, 'height': 100.0}

  def test_non_numeric_value_returns_none(self):
    assert coerce_bbox({'x': 'a', 'y': 0, 'width': 10, 'height': 10}) is None


# ---------------------------------------------------------------------------
# TestClipValue
# ---------------------------------------------------------------------------

class TestClipValue:
  def test_value_in_range_unchanged(self):
    assert clip_value(0.5, 0.0, 1.0) == 0.5

  def test_value_below_min_clamped(self):
    assert clip_value(-0.1, 0.0, 1.0) == 0.0

  def test_value_above_max_clamped(self):
    assert clip_value(1.5, 0.0, 1.0) == 1.0

  def test_value_at_boundaries(self):
    assert clip_value(0.0, 0.0, 1.0) == 0.0
    assert clip_value(1.0, 0.0, 1.0) == 1.0


# ---------------------------------------------------------------------------
# TestBounds
# ---------------------------------------------------------------------------

class TestBounds:
  def test_none_returns_default(self):
    assert bounds(None) == (1.0, 1.0)

  def test_wrong_length_returns_default(self):
    assert bounds((1280,)) == (1.0, 1.0)
    assert bounds((1280, 720, 3)) == (1.0, 1.0)

  def test_valid_tuple(self):
    assert bounds((1280, 720)) == (1280.0, 720.0)

  def test_valid_list(self):
    assert bounds([640, 480]) == (640.0, 480.0)


# ---------------------------------------------------------------------------
# TestClipPoint
# ---------------------------------------------------------------------------

class TestClipPoint:
  def test_point_inside_frame_unchanged(self):
    assert clip_point(0.5, 0.5, (1.0, 1.0)) == (0.5, 0.5)

  def test_point_outside_frame_clipped(self):
    x, y = clip_point(-0.1, 1.5, (1.0, 1.0))
    assert x == 0.0
    assert y == 1.0

  def test_pixel_space_clipping(self):
    x, y = clip_point(1300, 800, (1280, 720))
    assert x == 1280
    assert y == 720


# ---------------------------------------------------------------------------
# TestScaleBbox
# ---------------------------------------------------------------------------

class TestScaleBbox:
  def test_scales_normalized_to_pixels(self):
    bbox = {'x': 0.1, 'y': 0.2, 'width': 0.5, 'height': 0.4}
    result = scale_bbox(bbox, (1000, 500))
    assert result == {'x': 100, 'y': 100, 'width': 500, 'height': 200}

  def test_none_resolution_returns_none(self):
    assert scale_bbox({'x': 0, 'y': 0, 'width': 1, 'height': 1}, None) is None

  def test_wrong_resolution_length_returns_none(self):
    assert scale_bbox({'x': 0, 'y': 0, 'width': 1, 'height': 1}, (1280,)) is None


# ---------------------------------------------------------------------------
# TestQuantizeBbox
# ---------------------------------------------------------------------------

class TestQuantizeBbox:
  def test_pixel_space_rounds_to_int(self):
    result = quantize_bbox({'x': 1.6, 'y': 2.4, 'width': 100.7, 'height': 200.3}, 1280, 720)
    assert result == {'x': 2, 'y': 2, 'width': 101, 'height': 200}

  def test_normalized_space_rounds_to_6_decimals(self):
    result = quantize_bbox(
      {'x': 0.123456789, 'y': 0.987654321, 'width': 0.5, 'height': 0.25},
      1.0, 1.0,
    )
    assert result == {'x': 0.123457, 'y': 0.987654, 'width': 0.5, 'height': 0.25}


# ---------------------------------------------------------------------------
# TestBoundingBoxRewritePolicy
# ---------------------------------------------------------------------------

@dataclass
class _Anchor:
  """Minimal stub for RewriteAnchorEstimateLike."""
  x: float
  y: float
  method: str
  confidence: Optional[float]
  direct_observation_count: int
  allow_horizontal_shift: bool


def _make_policy(
  direct_gap=0.25,
  estimated_gap=0.20,
  direct_safety=0.0,
  estimated_safety=0.01,
  min_confidence=0.4,
  low_conf_methods=frozenset({'estimated_hip', 'estimated_nose_shoulder'}),
  occlusion_signal=True,
):
  thresholds = BoundingBoxRewriteThresholds(
    direct_safety_margin=direct_safety,
    estimated_safety_margin=estimated_safety,
    direct_gap_factor=direct_gap,
    estimated_gap_factor=estimated_gap,
    min_estimate_confidence_threshold=min_confidence,
    low_confidence_estimation_methods=low_conf_methods,
  )
  return BoundingBoxRewritePolicy(
    thresholds=thresholds,
    has_likely_occlusion_signal=lambda kp, bb: occlusion_signal,
  )


class TestShouldRewriteBbox:
  _BBOX = {'x': 0.1, 'y': 0.1, 'width': 0.4, 'height': 0.6}

  def test_direct_observation_sufficient_extension_returns_true(self):
    """Direct ankle well below bbox → rewrite."""
    policy = _make_policy()
    # box_bottom=0.7, anchor.y=0.9 → extension=0.2, threshold=0.6*0.25=0.15 → 0.2>0.15
    anchor = _Anchor(x=0.3, y=0.9, method='detected_ankles',
                     confidence=0.9, direct_observation_count=2, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is True

  def test_direct_observation_insufficient_extension_returns_false(self):
    """Direct ankle only slightly below bbox → no rewrite."""
    policy = _make_policy()
    # box_bottom=0.7, anchor.y=0.71 → extension=0.01, threshold=0.15 → 0.01<=0.15
    anchor = _Anchor(x=0.3, y=0.71, method='detected_ankles',
                     confidence=0.9, direct_observation_count=2, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is False

  def test_estimated_sufficient_extension_occlusion_true_returns_true(self):
    """Estimated anchor far below bbox + occlusion signal → rewrite."""
    policy = _make_policy(occlusion_signal=True)
    # box_bottom=0.7, anchor.y=0.95 → ext=0.25, threshold=0.6*0.20=0.12 → 0.25>0.12
    anchor = _Anchor(x=0.3, y=0.95, method='estimated_knee_hip',
                     confidence=0.8, direct_observation_count=0, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is True

  def test_estimated_sufficient_extension_occlusion_false_returns_false(self):
    """Estimated anchor far below bbox but no occlusion signal → no rewrite."""
    policy = _make_policy(occlusion_signal=False)
    anchor = _Anchor(x=0.3, y=0.95, method='estimated_knee_hip',
                     confidence=0.8, direct_observation_count=0, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is False

  def test_low_confidence_method_skipped(self):
    """Estimation method in low_confidence_estimation_methods → no rewrite."""
    policy = _make_policy(
      occlusion_signal=True,
      low_conf_methods={'estimated_hip'},
    )
    anchor = _Anchor(x=0.3, y=0.95, method='estimated_hip',
                     confidence=0.8, direct_observation_count=0, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is False

  def test_low_confidence_value_skipped(self):
    """Estimated anchor with confidence below threshold → no rewrite."""
    policy = _make_policy(occlusion_signal=True, min_confidence=0.6)
    anchor = _Anchor(x=0.3, y=0.95, method='estimated_nose_hip',
                     confidence=0.3, direct_observation_count=0, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is False

  def test_none_confidence_not_blocked_by_threshold(self):
    """Confidence=None bypasses the threshold check (confidence unknown)."""
    policy = _make_policy(occlusion_signal=True, min_confidence=0.6)
    anchor = _Anchor(x=0.3, y=0.95, method='estimated_nose_hip',
                     confidence=None, direct_observation_count=0, allow_horizontal_shift=False)
    assert policy.should_rewrite_bbox(self._BBOX, {}, anchor) is True


class TestRewriteBbox:
  _BBOX = {'x': 0.1, 'y': 0.1, 'width': 0.4, 'height': 0.6}

  def test_no_horizontal_shift_preserves_x(self):
    """Without horizontal shift, x is unchanged."""
    policy = _make_policy()
    anchor = _Anchor(x=0.5, y=0.9, method='estimated_knee_hip',
                     confidence=0.8, direct_observation_count=0, allow_horizontal_shift=False)
    result = policy.rewrite_bbox(self._BBOX, anchor, (1.0, 1.0))
    assert result['x'] == pytest.approx(0.1, abs=1e-4)

  def test_height_extended_to_cover_anchor(self):
    """New bbox bottom >= anchor.y."""
    policy = _make_policy(estimated_safety=0.0)
    anchor = _Anchor(x=0.3, y=0.9, method='estimated_knee_hip',
                     confidence=0.8, direct_observation_count=0, allow_horizontal_shift=False)
    result = policy.rewrite_bbox(self._BBOX, anchor, (1.0, 1.0))
    assert result['y'] + result['height'] >= 0.9

  def test_horizontal_shift_centers_on_anchor(self):
    """With horizontal shift, bbox is centered on anchor.x."""
    policy = _make_policy()
    anchor = _Anchor(x=0.5, y=0.9, method='detected_ankles',
                     confidence=0.9, direct_observation_count=2, allow_horizontal_shift=True)
    result = policy.rewrite_bbox(self._BBOX, anchor, (1.0, 1.0))
    center_x = result['x'] + result['width'] / 2
    assert center_x == pytest.approx(0.5, abs=1e-4)

  def test_result_stays_within_normalized_bounds(self):
    """Rewritten bbox must stay within [0,1] frame."""
    policy = _make_policy()
    # anchor near frame bottom
    anchor = _Anchor(x=0.3, y=0.99, method='estimated_knee_hip',
                     confidence=0.8, direct_observation_count=0, allow_horizontal_shift=False)
    result = policy.rewrite_bbox(self._BBOX, anchor, (1.0, 1.0))
    assert result['y'] >= 0.0
    assert result['x'] >= 0.0
    assert result['y'] + result['height'] <= 1.0 + 1e-6  # allow float rounding
    assert result['x'] + result['width'] <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# TestCanonicalJointName
# ---------------------------------------------------------------------------

class TestCanonicalJointName:
  def test_exact_canonical_name(self):
    assert canonical_joint_name('left_ankle') == 'left_ankle'

  def test_alias_resolves(self):
    assert canonical_joint_name('ankle_l') == 'left_ankle'
    assert canonical_joint_name('r_knee') == 'right_knee'

  def test_case_insensitive(self):
    assert canonical_joint_name('Left_Hip') == 'left_hip'
    assert canonical_joint_name('NOSE') == 'nose'

  def test_unknown_name_returns_none(self):
    assert canonical_joint_name('pinky_toe') is None

  def test_non_string_returns_none(self):
    assert canonical_joint_name(42) is None
    assert canonical_joint_name(None) is None


# ---------------------------------------------------------------------------
# TestParseNamedKeypoints
# ---------------------------------------------------------------------------

class TestParseNamedKeypoints:
  def test_parses_valid_list(self):
    raw = [
      {'name': 'left_hip', 'x': 0.4, 'y': 0.6, 'confidence': 0.9},
      {'name': 'right_hip', 'x': 0.6, 'y': 0.6, 'confidence': 0.8},
    ]
    result = parse_named_keypoints(raw)
    assert 'left_hip' in result
    assert result['left_hip'].x == pytest.approx(0.4)
    assert result['left_hip'].confidence == pytest.approx(0.9)

  def test_non_list_returns_empty(self):
    assert parse_named_keypoints({}) == {}
    assert parse_named_keypoints(None) == {}

  def test_item_with_missing_coords_skipped(self):
    raw = [{'name': 'nose', 'confidence': 0.9}]  # no x or y
    assert parse_named_keypoints(raw) == {}

  def test_alias_name_is_canonicalized(self):
    raw = [{'name': 'ankle_r', 'x': 0.5, 'y': 0.9, 'confidence': 0.9}]
    result = parse_named_keypoints(raw)
    assert 'right_ankle' in result

  def test_duplicate_joint_higher_confidence_wins(self):
    raw = [
      {'name': 'nose', 'x': 0.3, 'y': 0.1, 'confidence': 0.5},
      {'name': 'nose', 'x': 0.4, 'y': 0.2, 'confidence': 0.9},
    ]
    result = parse_named_keypoints(raw)
    assert result['nose'].x == pytest.approx(0.4)

  def test_unknown_joint_name_skipped(self):
    raw = [{'name': 'pinky_toe', 'x': 0.5, 'y': 0.9}]
    assert parse_named_keypoints(raw) == {}

  def test_non_dict_item_in_list_skipped(self):
    raw = ['bad', {'name': 'nose', 'x': 0.5, 'y': 0.1, 'confidence': 0.9}]
    result = parse_named_keypoints(raw)
    assert 'nose' in result

  def test_missing_confidence_skipped(self):
    raw = [{'name': 'nose', 'x': 0.5, 'y': 0.1}]
    assert parse_named_keypoints(raw) == {}

  def test_low_confidence_skipped(self):
    raw = [{'name': 'nose', 'x': 0.5, 'y': 0.1, 'confidence': 0.01}]
    assert parse_named_keypoints(raw) == {}

  def test_at_threshold_confidence_included(self):
    raw = [{'name': 'nose', 'x': 0.5, 'y': 0.1, 'confidence': 0.5}]
    result = parse_named_keypoints(raw)
    assert 'nose' in result


# ---------------------------------------------------------------------------
# TestKeypointsAreNormalized
# ---------------------------------------------------------------------------

class TestKeypointsAreNormalized:
  def test_empty_dict_returns_false(self):
    assert keypoints_are_normalized({}) is False

  def test_all_in_range_returns_true(self):
    kps = {'nose': NamedKeypoint(0.5, 0.2), 'left_hip': NamedKeypoint(0.4, 0.6)}
    assert keypoints_are_normalized(kps) is True

  def test_x_out_of_range_returns_false(self):
    kps = {'nose': NamedKeypoint(1.5, 0.2)}
    assert keypoints_are_normalized(kps) is False

  def test_y_out_of_range_returns_false(self):
    kps = {'nose': NamedKeypoint(0.5, -0.5)}
    assert keypoints_are_normalized(kps) is False


# ---------------------------------------------------------------------------
# TestScaleKeypoints
# ---------------------------------------------------------------------------

class TestScaleKeypoints:
  def test_scales_with_resolution_only(self):
    """Without a bbox, keypoints are scaled by resolution."""
    kps = {'nose': NamedKeypoint(0.5, 0.2)}
    result = scale_keypoints(kps, (1000, 500))
    assert result['nose'].x == pytest.approx(500.0)
    assert result['nose'].y == pytest.approx(100.0)

  def test_scales_with_bbox_relative(self):
    """With bbox provided, keypoints are treated as bbox-relative."""
    kps = {'nose': NamedKeypoint(0.5, 0.5)}
    bbox = {'x': 0.2, 'y': 0.1, 'width': 0.4, 'height': 0.6}
    result = scale_keypoints(kps, None, bbox)
    assert result['nose'].x == pytest.approx(0.2 + 0.5 * 0.4)
    assert result['nose'].y == pytest.approx(0.1 + 0.5 * 0.6)

  def test_empty_keypoints_returns_empty(self):
    assert scale_keypoints({}, (1280, 720)) == {}

  def test_no_resolution_no_bbox_preserves_coords(self):
    """Without resolution or bbox the keypoints should pass through unchanged."""
    kps = {'nose': NamedKeypoint(0.5, 0.2)}
    result = scale_keypoints(kps, None, None)
    assert result['nose'].x == pytest.approx(0.5)
    assert result['nose'].y == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# TestPersonProportionEntry
# ---------------------------------------------------------------------------

class TestPersonProportionEntry:
  def test_initial_observation_count_is_zero(self):
    entry = PersonProportionEntry(max_samples=10)
    assert entry.observation_count == 0
    assert entry.detection_count == 0

  def test_mark_seen_increments_detection_count(self):
    entry = PersonProportionEntry(max_samples=10)
    entry.mark_seen(1.0)
    entry.mark_seen(2.0)
    assert entry.detection_count == 2

  def test_add_observation_increments_observation_count(self):
    entry = PersonProportionEntry(max_samples=10)
    entry.add_observation({'ratio_ankle_knee_hip': 1.3}, when=1.0)
    assert entry.observation_count == 1

  def test_add_empty_observation_does_not_increment_count(self):
    entry = PersonProportionEntry(max_samples=10)
    entry.add_observation({}, when=1.0)
    assert entry.observation_count == 0

  def test_medians_returns_correct_median(self):
    entry = PersonProportionEntry(max_samples=10)
    for v in (1.0, 2.0, 3.0):
      entry.add_observation({'ratio_ankle_knee_hip': v}, when=float(v))
    medians = entry.medians()
    assert medians['ratio_ankle_knee_hip'] == pytest.approx(2.0)

  def test_max_samples_caps_deque_length(self):
    entry = PersonProportionEntry(max_samples=3)
    for v in (1.0, 2.0, 3.0, 4.0, 5.0):
      entry.add_observation({'ratio_ankle_knee_hip': v}, when=float(v))
    # Deque keeps the last 3; median of [3,4,5] = 4
    assert entry.medians()['ratio_ankle_knee_hip'] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# TestProportionCache
# ---------------------------------------------------------------------------

class TestProportionCache:
  _KEY = ('scene', 'cam', 'p1')

  def test_get_medians_returns_empty_before_min_observations(self):
    cache = ProportionCache(min_observations=3)
    cache.add_observation(self._KEY, {'ratio_ankle_knee_hip': 1.3}, when=1.0)
    cache.add_observation(self._KEY, {'ratio_ankle_knee_hip': 1.3}, when=2.0)
    assert cache.get_medians(self._KEY) == {}

  def test_get_medians_returns_values_after_min_observations(self):
    cache = ProportionCache(min_observations=3)
    for t in (1.0, 2.0, 3.0):
      cache.add_observation(self._KEY, {'ratio_ankle_knee_hip': 1.3}, when=t)
    result = cache.get_medians(self._KEY)
    assert 'ratio_ankle_knee_hip' in result
    assert result['ratio_ankle_knee_hip'] == pytest.approx(1.3)

  def test_get_medians_for_missing_key_returns_empty(self):
    cache = ProportionCache(min_observations=3)
    assert cache.get_medians(('no', 'such', 'key')) == {}

  def test_prune_removes_stale_entry(self):
    cache = ProportionCache(max_entry_age_seconds=10)
    for t in (1.0, 2.0, 3.0):
      cache.add_observation(self._KEY, {'ratio_ankle_knee_hip': 1.3}, when=t)
    # last_seen=3.0; prune at 14.0 → stale (14-3=11 > 10)
    cache.prune(now=14.0)
    assert cache.get_medians(self._KEY) == {}

  def test_prune_keeps_recent_entry(self):
    cache = ProportionCache(max_entry_age_seconds=10)
    for t in (1.0, 2.0, 3.0):
      cache.add_observation(self._KEY, {'ratio_ankle_knee_hip': 1.3}, when=t)
    # last_seen=3.0; prune at 12.0 → still fresh (12-3=9 < 10)
    cache.prune(now=12.0)
    result = cache.get_medians(self._KEY)
    assert 'ratio_ankle_knee_hip' in result

  def test_set_max_entry_age_updates_future_pruning(self):
    cache = ProportionCache(max_entry_age_seconds=10)
    cache.set_max_entry_age_seconds(100)
    for t in (1.0, 2.0, 3.0):
      cache.add_observation(self._KEY, {'ratio_ankle_knee_hip': 1.3}, when=t)
    # last_seen=3.0; prune at 50 → not stale with 100s TTL
    cache.prune(now=50.0)
    assert cache.get_medians(self._KEY) != {}

  def test_multiple_persons_tracked_independently(self):
    cache = ProportionCache(min_observations=3)
    key_a = ('s', 'c', 'a')
    key_b = ('s', 'c', 'b')
    for t in (1.0, 2.0, 3.0):
      cache.add_observation(key_a, {'ratio_ankle_knee_hip': 1.5}, when=t)
    assert cache.get_medians(key_a) != {}
    assert cache.get_medians(key_b) == {}
