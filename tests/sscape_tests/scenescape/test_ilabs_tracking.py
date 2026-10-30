# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
from types import SimpleNamespace

import numpy as np
import pytest

from controller.ilabs_tracking import (IntelLabsTracking, _quaternion_to_yaw,
                                       _yaw_to_quaternion,
                                       association_match_params,
                                       build_association_window,
                                       normalize_association_config)
from scene_common.geometry import Point

import robot_vision as rv


def test_normalize_association_config_defaults():
  config = normalize_association_config()
  assert config == {
    'method': 'position_mahalanobis',
    'gate_probability': 0.99,
    'max_radius_m': 10.0,
  }


def test_normalize_association_config_rejects_unknown_method():
  with pytest.raises(ValueError, match='Invalid association method'):
    normalize_association_config({'method': 'not-a-real-method', 'max_radius_m': 5.0})


def test_normalize_association_config_invalid_max_radius_uses_method_default():
  mahal = normalize_association_config({
    'method': 'position_mahalanobis',
    'max_radius_m': 'bad',
  })
  assert mahal['max_radius_m'] == pytest.approx(10.0)

  euclid = normalize_association_config({
    'method': 'euclidean',
    'max_radius_m': -1.0,
  })
  assert euclid['max_radius_m'] == pytest.approx(2.0)


def test_normalize_association_config_warns_on_tight_mahalanobis_ceiling(monkeypatch):
  warnings = []

  def capture_warning(*args):
    warnings.append(args)

  monkeypatch.setattr('controller.ilabs_tracking.log.warning', capture_warning)
  config = normalize_association_config({
    'method': 'position_mahalanobis',
    'max_radius_m': 2.0,
  })
  assert config['max_radius_m'] == pytest.approx(2.0)
  assert warnings
  assert 'position_mahalanobis with max_radius_m' in warnings[0][0]


def test_association_match_params_euclidean_uses_max_radius_as_threshold():
  distance_type, distance_threshold, max_radius_m = association_match_params({
    'method': 'euclidean',
    'max_radius_m': 3.5,
  })
  assert distance_type == rv.tracking.DistanceType.Euclidean
  assert distance_threshold == pytest.approx(3.5)
  assert max_radius_m == pytest.approx(3.5)


def test_association_match_params_mahalanobis_uses_chi2_gate():
  distance_type, distance_threshold, max_radius_m = association_match_params({
    'method': 'position_mahalanobis',
    'gate_probability': 0.99,
    'max_radius_m': 10.0,
  })
  assert distance_type == rv.tracking.DistanceType.PositionMahalanobis
  assert distance_threshold == pytest.approx(rv.tracking.chi2_threshold(0.99))
  assert max_radius_m == pytest.approx(10.0)


def test_apply_association_config_updates_tracker():
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config()
  child = IntelLabsTracking.__new__(IntelLabsTracking)
  child.association_config = normalize_association_config({
    'method': 'euclidean',
    'max_radius_m': 2.0,
  })
  child.trackers = {}
  tracker.trackers = {'person': child}
  tracker.applyAssociationConfig({
    'method': 'position_mahalanobis',
    'gate_probability': 0.95,
    'max_radius_m': 10.0,
  })
  assert tracker.association_config['method'] == 'position_mahalanobis'
  assert tracker.association_config['gate_probability'] == pytest.approx(0.95)
  assert child.association_config['method'] == 'position_mahalanobis'
  assert child.association_config['gate_probability'] == pytest.approx(0.95)
  assert child.association_config['max_radius_m'] == pytest.approx(10.0)


def test_create_trackers_propagates_association_config(monkeypatch):
  """Category workers created by Tracking._createTrackers inherit association."""
  from controller.tracking import Tracking

  parent = IntelLabsTracking.__new__(IntelLabsTracking)
  parent.reid_config_data = {}
  parent.association_config = normalize_association_config({
    'method': 'position_mahalanobis',
    'gate_probability': 0.99,
    'max_radius_m': 10.0,
  })
  parent.trackers = {}
  parent.uuid_manager = SimpleNamespace(scene_id='scene')

  captured = {}

  def fake_init(self, *args, **kwargs):
    captured['kwargs'] = kwargs
    self.uuid_manager = SimpleNamespace(scene_id=None)
    self.queue = SimpleNamespace()

  monkeypatch.setattr(IntelLabsTracking, '__init__', fake_init)
  monkeypatch.setattr(IntelLabsTracking, 'start', lambda self: None)
  # Ensure __class__ resolves to IntelLabsTracking for construction
  parent.__class__ = IntelLabsTracking
  Tracking._createTrackers(parent, ['person'], 1.0, 0.8, 1.6, 10)

  assert captured['kwargs']['association_config']['method'] == 'position_mahalanobis'
  assert 'person' in parent.trackers


@pytest.mark.parametrize("yaw", [
  -math.pi,
  -math.pi / 2.0,
  0.0,
  math.pi / 2.0,
  math.pi,
])
def test_quaternion_to_yaw_for_z_axis_rotation(yaw):
  quaternion = [0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)]

  actual = _quaternion_to_yaw(quaternion)

  assert math.cos(actual) == pytest.approx(math.cos(yaw))
  assert math.sin(actual) == pytest.approx(math.sin(yaw))


def test_quaternion_to_yaw_does_not_treat_y_component_as_yaw():
  pitch = math.pi / 4.0
  quaternion = [0.0, math.sin(pitch / 2.0), 0.0, math.cos(pitch / 2.0)]

  assert _quaternion_to_yaw(quaternion) == pytest.approx(0.0)


@pytest.mark.parametrize("rotation", [None, [], [0.0, 0.0, 0.0, 0.0], [0.0, math.nan, 0.0, 1.0]])
def test_quaternion_to_yaw_returns_zero_for_invalid_rotation(rotation):
  assert _quaternion_to_yaw(rotation) == 0.0


def test_to_rv_object_converts_quaternion_to_yaw():
  yaw = math.pi / 2.0
  detected_object = SimpleNamespace(
    sceneLoc=Point(1.0, 2.0, 3.0),
    size=[4.0, 2.0, 1.5],
    rotation=[0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)],
    confidence=0.9,
    info={},
    frameCount=1,
    metadata={},
    has_detection_rotation=True,
  )
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)

  rv_object = tracker.to_rv_object(detected_object)

  assert rv_object.yaw == pytest.approx(yaw)
  assert rv_object.attributes.get('has_orientation') == 'true'


def test_to_rv_object_omits_orientation_without_detection_rotation():
  detected_object = SimpleNamespace(
    sceneLoc=Point(1.0, 2.0, 3.0),
    size=[4.0, 2.0, 1.5],
    rotation=[0.0, 0.0, 0.0, 1.0],
    confidence=0.9,
    info={},
    frameCount=1,
    metadata={},
    has_detection_rotation=False,
  )
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)

  rv_object = tracker.to_rv_object(detected_object)

  assert rv_object.yaw == 0.0
  assert 'has_orientation' not in rv_object.attributes


@pytest.mark.parametrize("yaw", [
  -math.pi,
  -math.pi / 2.0,
  0.0,
  math.pi / 2.0,
  math.pi,
])
def test_yaw_to_quaternion_produces_z_axis_only_quaternion(yaw):
  quaternion = _yaw_to_quaternion(yaw)

  assert quaternion == pytest.approx([0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)])


def _make_tracked_object(uuid_value, yaw=0.0, attributes=None, vx=0.1, vy=0.2):
  attrs = {'info': uuid_value}
  if attributes:
    attrs.update(attributes)
  return SimpleNamespace(
    attributes=attrs,
    x=1.0, y=2.0, z=0.0,
    vx=vx, vy=vy,
    yaw=yaw,
    id=42,
    measurement_covariance=np.eye(7) * 0.25,
  )


def _make_sscape_object(uuid_value, has_detection_rotation, rotation=None):
  obj = SimpleNamespace(
    uuid=uuid_value,
    has_detection_rotation=has_detection_rotation,
    location=[SimpleNamespace(point=None)],
    rotation=rotation if rotation is not None else [0.0, 0.0, 0.0, 1.0],
    velocity=None,
    setGID=lambda gid: None,
    metadata={},
  )
  obj.inferRotationFromVelocity = lambda: setattr(obj, 'velocity_inferred', True)
  return obj


def test_build_association_window_euclidean_is_circle():
  window = build_association_window({
    'method': 'euclidean',
    'max_radius_m': 2.5,
  })
  assert window == {
    'method': 'euclidean',
    'shape': 'circle',
    'radius_m': 2.5,
  }


def test_build_association_window_mahalanobis_is_ellipse():
  # Diagonal covariance → axis-aligned ellipse; χ²(0.99,2) ≈ 9.21
  cov = np.diag([1.0, 0.25, 1.0, 1.0, 1.0, 1.0, 1.0])
  window = build_association_window({
    'method': 'position_mahalanobis',
    'gate_probability': 0.99,
    'max_radius_m': 10.0,
  }, cov)
  assert window['method'] == 'position_mahalanobis'
  assert window['shape'] == 'ellipse'
  assert window['semi_major_m'] == pytest.approx(math.sqrt(9.21034037198 * 1.0), rel=1e-4)
  assert window['semi_minor_m'] == pytest.approx(math.sqrt(9.21034037198 * 0.25), rel=1e-4)
  assert window['angle_rad'] == pytest.approx(0.0, abs=1e-6)


def test_from_tracked_object_overwrites_rotation_when_detection_rotation_present():
  yaw = math.pi / 2.0
  tracked_object = _make_tracked_object("uuid-1", yaw=yaw)
  sscape_object = _make_sscape_object("uuid-1", has_detection_rotation=True)

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config({'method': 'euclidean', 'max_radius_m': 2.0})

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  assert result.rotation == pytest.approx(_yaw_to_quaternion(yaw))
  assert result.association_window['shape'] == 'circle'
  assert result.association_window['radius_m'] == pytest.approx(2.0)


def test_from_tracked_object_uses_kalman_yaw_when_orientation_observed_on_track():
  yaw = math.pi / 3.0
  tracked_object = _make_tracked_object(
    "uuid-cam", yaw=yaw, attributes={'orientation_observed': 'true'})
  sscape_object = _make_sscape_object("uuid-cam", has_detection_rotation=False,
                                      rotation=[0.0, 0.0, 0.1, 0.9])

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config()

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  assert result.rotation == pytest.approx(_yaw_to_quaternion(yaw))
  assert not hasattr(result, 'velocity_inferred')


def test_from_tracked_object_uses_velocity_when_kalman_yaw_lags_turn():
  """Sticky LiDAR yaw with camera-only curve: publish velocity heading."""
  kalman_yaw = 0.0
  # ~1 rad heading while Kalman still points east — matches live turn case.
  tracked_object = _make_tracked_object(
    "uuid-turn", yaw=kalman_yaw, vx=4.0, vy=5.0,
    attributes={'orientation_observed': 'true'})
  sscape_object = _make_sscape_object("uuid-turn", has_detection_rotation=False,
                                      rotation=[0.0, 0.0, 0.0, 1.0])

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config()

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  expected_heading = math.atan2(5.0, 4.0)
  assert result.rotation == pytest.approx(_yaw_to_quaternion(expected_heading))


def test_from_tracked_object_uses_velocity_when_orienting_yaw_lags_motion():
  """Orienting detection still publishes velocity when Kalman yaw lags a turn."""
  kalman_yaw = math.pi / 2.0
  tracked_object = _make_tracked_object(
    "uuid-orient", yaw=kalman_yaw, vx=5.0, vy=0.1,
    attributes={'orientation_observed': 'true', 'has_orientation': 'true'})
  sscape_object = _make_sscape_object("uuid-orient", has_detection_rotation=True)

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config()

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  expected_heading = math.atan2(0.1, 5.0)
  assert result.rotation == pytest.approx(_yaw_to_quaternion(expected_heading))


def test_from_tracked_object_overrides_absurd_lidar_yaw_with_velocity():
  """Detector yaw ~180° off motion while moving → publish velocity heading."""
  kalman_yaw = 0.0
  tracked_object = _make_tracked_object(
    "uuid-flip", yaw=kalman_yaw, vx=-5.0, vy=0.0,
    attributes={'orientation_observed': 'true', 'has_orientation': 'true'})
  sscape_object = _make_sscape_object("uuid-flip", has_detection_rotation=True)

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config()

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  assert result.rotation == pytest.approx(_yaw_to_quaternion(math.pi))


def test_from_tracked_object_does_not_overwrite_rotation_for_velocity_inferred_rotation():
  original_rotation = [0.0, 0.0, 0.1, 0.9]
  tracked_object = _make_tracked_object("uuid-2", yaw=math.pi / 2.0)
  sscape_object = _make_sscape_object("uuid-2", has_detection_rotation=False,
                                      rotation=original_rotation)

  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config()

  result = tracker.from_tracked_object(tracked_object, [sscape_object])

  assert result.rotation == original_rotation
  assert result.association_window['shape'] == 'ellipse'
  assert getattr(result, 'velocity_inferred', False) is True
