#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for pose adjustment.

These tests exercise PersonPoseAdjuster and the PoseAdjustment coordinator with
deterministic inputs and assert specific behavioral outcomes.  They serve as the
CI/CD regression gate: any future change that alters the behavior of pose
adjustment for the covered scenarios will be caught here.

Test Organisation
-----------------
- TestCacheWarmup        : cache not yet ready → no adjustments made
- TestDirectAnkles       : direct ankle observations never rewrite the bbox
- TestBboxRewrite        : occluded-foot scenario triggers bbox extension
- TestMultiPerson        : per-person cache independence
- TestPixelBbox          : same warm-up/occlusion flow for pixel-space bboxes
- TestPoseAdjustmentCoordinator : PoseAdjustment dispatcher (enabled/disabled/types)
"""

import copy
import pytest

from controller.pose_adjustment.strategies.person.bbox_adjuster import PersonPoseAdjuster
from controller.pose_adjustment.pose_adjustment import PoseAdjustment
from controller.pose_adjustment.strategy import PoseAdjustmentStrategy


# ---------------------------------------------------------------------------
# Shared detection builders
# ---------------------------------------------------------------------------

# Full-body detection (bbox-relative keypoints, ankles included).
# bbox = {'x': 0.15, 'y': 0.05, 'width': 0.60, 'height': 0.90}
# Absolute frame positions: nose≈(0.45,0.12) shoulders≈(0.45,0.25)
#   hips≈(0.45,0.43) knees≈(0.45,0.61) ankles≈(0.45,0.84)
_FULL_BODY_BBOX = {'x': 0.15, 'y': 0.05, 'width': 0.60, 'height': 0.90}
_FULL_BODY_KEYPOINTS = [
  {'name': 'nose',           'x': 0.50, 'y': 0.08, 'confidence': 0.95},
  {'name': 'left_shoulder',  'x': 0.38, 'y': 0.22, 'confidence': 0.90},
  {'name': 'right_shoulder', 'x': 0.62, 'y': 0.22, 'confidence': 0.90},
  {'name': 'left_hip',       'x': 0.40, 'y': 0.42, 'confidence': 0.88},
  {'name': 'right_hip',      'x': 0.60, 'y': 0.42, 'confidence': 0.88},
  {'name': 'left_knee',      'x': 0.40, 'y': 0.62, 'confidence': 0.86},
  {'name': 'right_knee',     'x': 0.60, 'y': 0.62, 'confidence': 0.86},
  {'name': 'left_ankle',     'x': 0.41, 'y': 0.88, 'confidence': 0.85},
  {'name': 'right_ankle',    'x': 0.59, 'y': 0.88, 'confidence': 0.85},
]

# Truncated detection: same joints from hips upward, bbox cut at knee level, no ankles.
# bbox = {'x': 0.15, 'y': 0.05, 'width': 0.60, 'height': 0.60}  (box_bottom = 0.65)
# Absolute frame positions are identical to full-body for shared joints.
_TRUNCATED_BBOX = {'x': 0.15, 'y': 0.05, 'width': 0.60, 'height': 0.60}
_TRUNCATED_KEYPOINTS = [
  {'name': 'nose',           'x': 0.50, 'y': 0.12, 'confidence': 0.95},
  {'name': 'left_shoulder',  'x': 0.38, 'y': 0.33, 'confidence': 0.90},
  {'name': 'right_shoulder', 'x': 0.62, 'y': 0.33, 'confidence': 0.90},
  {'name': 'left_hip',       'x': 0.40, 'y': 0.63, 'confidence': 0.88},
  {'name': 'right_hip',      'x': 0.60, 'y': 0.63, 'confidence': 0.88},
  {'name': 'left_knee',      'x': 0.40, 'y': 0.93, 'confidence': 0.86},
  {'name': 'right_knee',     'x': 0.60, 'y': 0.93, 'confidence': 0.86},
]

_RESOLUTION = (1280, 720)


def _full_body_detection(person_id='p1'):
  return {
    'id': person_id,
    'category': 'person',
    'bounding_box': copy.deepcopy(_FULL_BODY_BBOX),
    'keypoints': copy.deepcopy(_FULL_BODY_KEYPOINTS),
  }


def _truncated_detection(person_id='p1'):
  return {
    'id': person_id,
    'category': 'person',
    'bounding_box': copy.deepcopy(_TRUNCATED_BBOX),
    'keypoints': copy.deepcopy(_TRUNCATED_KEYPOINTS),
  }


def _full_body_detection_px(person_id='p1'):
  """Full-body detection with pixel-space bbox (no normalized bbox)."""
  det = {
    'id': person_id,
    'category': 'person',
    'bounding_box_px': {'x': 150, 'y': 50, 'width': 600, 'height': 550},
    'keypoints': [
      {'name': 'nose',           'x': 0.50, 'y': 0.08, 'confidence': 0.95},
      {'name': 'left_shoulder',  'x': 0.38, 'y': 0.22, 'confidence': 0.90},
      {'name': 'right_shoulder', 'x': 0.62, 'y': 0.22, 'confidence': 0.90},
      {'name': 'left_hip',       'x': 0.40, 'y': 0.42, 'confidence': 0.88},
      {'name': 'right_hip',      'x': 0.60, 'y': 0.42, 'confidence': 0.88},
      {'name': 'left_knee',      'x': 0.40, 'y': 0.62, 'confidence': 0.86},
      {'name': 'right_knee',     'x': 0.60, 'y': 0.62, 'confidence': 0.86},
      {'name': 'left_ankle',     'x': 0.41, 'y': 0.88, 'confidence': 0.85},
      {'name': 'right_ankle',    'x': 0.59, 'y': 0.88, 'confidence': 0.85},
    ],
  }
  return det


def _truncated_detection_px(person_id='p1'):
  """Truncated detection with pixel-space bbox only."""
  return {
    'id': person_id,
    'category': 'person',
    'bounding_box_px': {'x': 150, 'y': 50, 'width': 600, 'height': 400},
    'keypoints': [
      {'name': 'nose',           'x': 0.50, 'y': 0.12, 'confidence': 0.95},
      {'name': 'left_shoulder',  'x': 0.38, 'y': 0.33, 'confidence': 0.90},
      {'name': 'right_shoulder', 'x': 0.62, 'y': 0.33, 'confidence': 0.90},
      {'name': 'left_hip',       'x': 0.40, 'y': 0.63, 'confidence': 0.88},
      {'name': 'right_hip',      'x': 0.60, 'y': 0.63, 'confidence': 0.88},
      {'name': 'left_knee',      'x': 0.40, 'y': 0.93, 'confidence': 0.86},
      {'name': 'right_knee',     'x': 0.60, 'y': 0.93, 'confidence': 0.86},
    ],
  }


def _warm_up(adjuster, person_id='p1', frames=3):
  """Submit `frames` full-body detections to warm the proportion cache."""
  for i in range(frames):
    det = _full_body_detection(person_id)
    adjuster.adjust_detection(
      det,
      scene_name='test_scene',
      camera_id='cam-1',
      when=float(i + 1),
      resolution=_RESOLUTION,
    )


# ---------------------------------------------------------------------------
# TestCacheWarmup
# ---------------------------------------------------------------------------

class TestCacheWarmup:
  """Cache not warmed up yet → no adjustments regardless of inputs."""

  def test_no_adjustment_before_cache_is_ready(self):
    """Returns False for the first min_observations frames (cache not ready)."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    # Two frames with ankles absent → cache cannot warm, always False
    for i in range(2):
      det = _truncated_detection()
      result = adjuster.adjust_detection(
        det,
        scene_name='s', camera_id='c', when=float(i), resolution=_RESOLUTION,
      )
      assert result is False


# ---------------------------------------------------------------------------
# TestDirectAnkles
# ---------------------------------------------------------------------------

class TestDirectAnkles:
  """Frames with valid direct ankle keypoints never trigger a bbox rewrite."""

  def test_adjust_detection_returns_false_when_ankles_visible(self):
    """With direct ankles in frame, adjust_detection always returns False."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    for i in range(5):
      det = _full_body_detection()
      result = adjuster.adjust_detection(
        det,
        scene_name='s', camera_id='c', when=float(i), resolution=_RESOLUTION,
      )
      assert result is False, f'Frame {i}: expected False with ankles visible'

  def test_bbox_unchanged_when_ankles_visible(self):
    """Bbox is not mutated when direct ankles are observed."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    for i in range(5):
      det = _full_body_detection()
      original_bbox = copy.deepcopy(det['bounding_box'])
      adjuster.adjust_detection(
        det, scene_name='s', camera_id='c', when=float(i), resolution=_RESOLUTION,
      )
      assert det['bounding_box'] == original_bbox, f'Frame {i}: bbox must not be mutated'

  def test_missing_person_id_skipped(self):
    """Detection without an id field is silently skipped."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    det = _full_body_detection()
    del det['id']
    result = adjuster.adjust_detection(
      det, scene_name='s', camera_id='c', when=1.0, resolution=_RESOLUTION,
    )
    assert result is False

  def test_wrong_category_skipped(self):
    """Detection with category != 'person' is silently skipped."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    det = _full_body_detection()
    det['category'] = 'vehicle'
    result = adjuster.adjust_detection(
      det, scene_name='s', camera_id='c', when=1.0, resolution=_RESOLUTION,
    )
    assert result is False

  def test_empty_keypoints_skipped(self):
    """Detection without usable keypoints is silently skipped."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    det = _full_body_detection()
    det['keypoints'] = []
    result = adjuster.adjust_detection(
      det, scene_name='s', camera_id='c', when=1.0, resolution=_RESOLUTION,
    )
    assert result is False


# ---------------------------------------------------------------------------
# TestBboxRewrite
# ---------------------------------------------------------------------------

class TestBboxRewrite:
  """Warm cache + occluded lower body → bbox is extended downward."""

  def test_rewrite_returns_true_after_cache_warm(self):
    """adjust_detection returns True when estimated foot indicates occlusion."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, frames=3)
    det = _truncated_detection()
    result = adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    assert result is True

  def test_rewrite_extends_bbox_downward(self):
    """Adjusted bbox height is strictly larger than the original."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, frames=3)
    det = _truncated_detection()
    original_height = det['bounding_box']['height']
    adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    assert det['bounding_box']['height'] > original_height

  def test_rewrite_preserves_top_left(self):
    """x and y of the bbox are not changed when no horizontal shift applies."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, frames=3)
    det = _truncated_detection()
    orig_x = det['bounding_box']['x']
    orig_y = det['bounding_box']['y']
    adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    assert det['bounding_box']['x'] == orig_x
    assert det['bounding_box']['y'] == orig_y

  def test_rewrite_bbox_stays_within_frame(self):
    """Extended bbox must not exceed frame bounds (0–1 for normalized)."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, frames=3)
    det = _truncated_detection()
    adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    bb = det['bounding_box']
    assert bb['y'] >= 0.0
    assert bb['x'] >= 0.0
    assert bb['y'] + bb['height'] <= 1.0
    assert bb['x'] + bb['width'] <= 1.0

  def test_rewrite_expected_values(self):
    """Bbox values after rewrite match the analytically expected result.

    With ratio_ankle_knee_hip ≈ 1.3 (learned from full-body warm-up):
      knee_mid_abs ≈ 0.608, hip_mid_abs ≈ 0.428
      estimated_foot_y = 0.608 + 1.3 * (0.608 - 0.428) = 0.842
      desired_bottom   = 0.842 + 0.60 * 0.01 = 0.848
      new height       = 0.848 - 0.05 = 0.798
    """
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, frames=3)
    det = _truncated_detection()
    adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    bb = det['bounding_box']
    assert bb['x'] == pytest.approx(0.15, abs=1e-4)
    assert bb['y'] == pytest.approx(0.05, abs=1e-4)
    assert bb['width'] == pytest.approx(0.60, abs=1e-4)
    assert bb['height'] == pytest.approx(0.798, abs=0.005)

  def test_second_occluded_frame_also_rewrites(self):
    """Consecutive occluded frames both receive bbox extension."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, frames=3)
    for t in (4.0, 5.0):
      det = _truncated_detection()
      result = adjuster.adjust_detection(
        det, scene_name='test_scene', camera_id='cam-1', when=t, resolution=_RESOLUTION,
      )
      assert result is True, f'Frame at t={t}: expected True'


# ---------------------------------------------------------------------------
# TestMultiPerson
# ---------------------------------------------------------------------------

class TestMultiPerson:
  """Two persons tracked simultaneously have independent proportion caches."""

  def test_p2_cache_not_warmed_by_p1_observations(self):
    """Warming p1's cache has no effect on p2's estimation readiness."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, person_id='p1', frames=3)
    # p2 has zero observations → cannot estimate → no rewrite
    det_p2 = _truncated_detection(person_id='p2')
    result = adjuster.adjust_detection(
      det_p2, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    assert result is False

  def test_both_persons_rewrite_when_both_caches_warm(self):
    """When both caches are warmed, both persons receive bbox extension."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    _warm_up(adjuster, person_id='p1', frames=3)
    _warm_up(adjuster, person_id='p2', frames=3)
    for pid in ('p1', 'p2'):
      det = _truncated_detection(person_id=pid)
      result = adjuster.adjust_detection(
        det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
      )
      assert result is True, f'Person {pid}: expected rewrite'


# ---------------------------------------------------------------------------
# TestPixelBbox
# ---------------------------------------------------------------------------

class TestPixelBbox:
  """Pixel-space bbox detections follow the same warm-up / occlusion flow."""

  def _warm_up_px(self, adjuster, person_id='p1', frames=3):
    for i in range(frames):
      det = _full_body_detection_px(person_id)
      adjuster.adjust_detection(
        det,
        scene_name='test_scene',
        camera_id='cam-1',
        when=float(i + 1),
        resolution=_RESOLUTION,
      )

  def test_no_adjustment_with_direct_ankles_in_pixel_mode(self):
    """Pixel bbox: direct ankles → no rewrite."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    for i in range(5):
      det = _full_body_detection_px()
      result = adjuster.adjust_detection(
        det, scene_name='s', camera_id='c', when=float(i), resolution=_RESOLUTION,
      )
      assert result is False

  def test_pixel_bbox_rewrite_after_warmup(self):
    """Pixel bbox: cache warm + truncated detection → adjust_detection returns True."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    self._warm_up_px(adjuster, frames=3)
    det = _truncated_detection_px()
    result = adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    assert result is True

  def test_pixel_bbox_extended_downward(self):
    """Pixel bbox is extended (height increases) when foot is occluded."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    self._warm_up_px(adjuster, frames=3)
    det = _truncated_detection_px()
    orig_h = det['bounding_box_px']['height']
    adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=_RESOLUTION,
    )
    assert det['bounding_box_px']['height'] > orig_h

  def test_pixel_bbox_no_resolution_skips_adjustment(self):
    """Pixel-only bbox without resolution → pixel adjustment cannot proceed."""
    adjuster = PersonPoseAdjuster(max_entry_age_seconds=120)
    # Warm with normalized bbox so cache is ready
    _warm_up(adjuster, frames=3)
    det = _truncated_detection_px()
    result = adjuster.adjust_detection(
      det, scene_name='test_scene', camera_id='cam-1', when=4.0, resolution=None,
    )
    assert result is False


# ---------------------------------------------------------------------------
# TestPoseAdjustmentCoordinator
# ---------------------------------------------------------------------------

class TestPoseAdjustmentCoordinator:
  """PoseAdjustment coordinator — dispatch, enable/disable, type routing."""

  def _make_camera(self, camera_id='cam-1', width=1280, height=720):
    """Minimal mock camera object accepted by PersonPoseAdjustmentStrategy."""
    class _Camera:
      def __init__(self):
        self.cameraID = camera_id
        self.width = width
        self.height = height
    return _Camera()

  def test_disabled_coordinator_returns_zero(self):
    """adjust_detections on a disabled coordinator always returns 0."""
    pa = PoseAdjustment(enabled=False, max_entry_age_seconds=120)
    camera = self._make_camera()
    result = pa.adjust_detections(
      'person', [_full_body_detection()], 'scene', camera, when=1.0,
    )
    assert result == 0

  def test_unknown_detection_type_returns_zero(self):
    """adjust_detections returns 0 for an unregistered detection type."""
    pa = PoseAdjustment(enabled=True, max_entry_age_seconds=120)
    camera = self._make_camera()
    result = pa.adjust_detections(
      'vehicle', [_full_body_detection()], 'scene', camera, when=1.0,
    )
    assert result == 0

  def test_person_type_is_registered_by_default(self):
    """'person' is a supported detection type in the default configuration."""
    pa = PoseAdjustment(enabled=True, max_entry_age_seconds=120)
    assert 'person' in pa.supported_detection_types()

  def test_custom_strategy_replaces_existing(self):
    """Registering a strategy for an existing type replaces it."""
    class _DummyStrategy:
      def detection_type(self):
        return 'person'
      def adjust_detections(self, detections, scene_name, camera, when):
        return 99
      def set_max_entry_age_seconds(self, v):
        pass

    pa = PoseAdjustment(enabled=True, max_entry_age_seconds=120)
    pa.register_strategy(_DummyStrategy())
    camera = self._make_camera()
    result = pa.adjust_detections(
      'person', [_full_body_detection()], 'scene', camera, when=1.0,
    )
    assert result == 99

  def test_set_max_entry_age_propagates_to_strategies(self):
    """set_max_entry_age_seconds updates all registered strategies."""
    pa = PoseAdjustment(enabled=True, max_entry_age_seconds=10)
    pa.set_max_entry_age_seconds(300)
    # Access the internal PersonPoseAdjustmentStrategy via the registry
    strategy = pa._strategies.get('person')
    assert strategy is not None
    assert strategy._adjuster.cache.max_entry_age_seconds == 300

  def test_route_mapping_routes_to_registered_strategy(self):
    """Configured route labels (e.g. pedestrian -> person) are resolved before dispatch."""
    class _PersonStrategy:
      def detection_type(self):
        return 'person'
      def adjust_detections(self, detections, scene_name, camera, when):
        return 7
      def set_max_entry_age_seconds(self, v):
        pass

    pa = PoseAdjustment(
      enabled=True,
      max_entry_age_seconds=120,
      strategies=[_PersonStrategy()],
      detection_type_routes={'person': ['pedestrian']},
    )
    camera = self._make_camera()
    result = pa.adjust_detections(
      'pedestrian', [_full_body_detection()], 'scene', camera, when=1.0,
    )
    assert result == 7

  def test_route_mapping_supports_multiple_labels_per_strategy(self):
    """A strategy can advertise multiple external labels through route config."""
    class _VehicleStrategy:
      def detection_type(self):
        return 'vehicle'
      def adjust_detections(self, detections, scene_name, camera, when):
        return 42
      def set_max_entry_age_seconds(self, v):
        pass

    pa = PoseAdjustment(
      enabled=True,
      max_entry_age_seconds=120,
      strategies=[_VehicleStrategy()],
      detection_type_routes={'vehicle': ['car', 'truck']},
    )
    camera = self._make_camera()
    result = pa.adjust_detections(
      'truck', [_full_body_detection()], 'scene', camera, when=1.0,
    )
    assert result == 42

  def test_exact_match_precedes_route_mapping(self):
    """Directly registered labels are preferred before configured route labels."""
    class _TruckStrategy:
      def detection_type(self):
        return 'truck'
      def adjust_detections(self, detections, scene_name, camera, when):
        return 11
      def set_max_entry_age_seconds(self, v):
        pass

    class _VehicleStrategy:
      def detection_type(self):
        return 'vehicle'
      def adjust_detections(self, detections, scene_name, camera, when):
        return 42
      def set_max_entry_age_seconds(self, v):
        pass

    pa = PoseAdjustment(
      enabled=True,
      max_entry_age_seconds=120,
      strategies=[_TruckStrategy(), _VehicleStrategy()],
      detection_type_routes={'vehicle': ['truck']},
    )
    camera = self._make_camera()
    result = pa.adjust_detections(
      'truck', [_full_body_detection()], 'scene', camera, when=1.0,
    )
    assert result == 11
