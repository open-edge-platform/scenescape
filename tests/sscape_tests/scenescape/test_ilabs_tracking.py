# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import threading
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


@pytest.mark.parametrize('method', ['not-a-real-method', [], {}, ['euclidean'], 1])
def test_normalize_association_config_rejects_unknown_method(method):
  with pytest.raises(ValueError, match='Invalid association method'):
    normalize_association_config({'method': method, 'max_radius_m': 5.0})


def _expected_radius(expected_max_radius_m):
  return None if expected_max_radius_m is None else pytest.approx(expected_max_radius_m)


# Without a valid max_radius_m, euclidean gates on the objects' tracking_radius (None).
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
  assert euclid['max_radius_m'] is None


@pytest.mark.parametrize('max_radius_m', ['nan', 'inf', float('nan'), float('inf')])
@pytest.mark.parametrize('method, expected_max_radius_m', [
  ('euclidean', None),
  ('position_mahalanobis', 10.0),
])
def test_normalize_association_config_nonfinite_max_radius_uses_method_default(
    method, expected_max_radius_m, max_radius_m):
  config = normalize_association_config({'method': method, 'max_radius_m': max_radius_m})
  assert config['max_radius_m'] == _expected_radius(expected_max_radius_m)


@pytest.mark.parametrize('method, expected_max_radius_m', [
  ('euclidean', None),
  ('position_mahalanobis', 10.0),
])
@pytest.mark.parametrize('missing', [{}, {'max_radius_m': None}])
def test_normalize_association_config_missing_max_radius_uses_method_default(
    method, expected_max_radius_m, missing, monkeypatch):
  errors = []
  monkeypatch.setattr('controller.ilabs_tracking.log.error', lambda *args: errors.append(args))
  config = normalize_association_config({'method': method, **missing})
  assert config['max_radius_m'] == _expected_radius(expected_max_radius_m)
  # The normalized config is normalized again downstream (Scene, IntelLabsTracking).
  assert normalize_association_config(config) == config
  assert not errors


def test_normalize_association_config_keeps_explicit_euclidean_max_radius():
  config = normalize_association_config({'method': 'euclidean', 'max_radius_m': 3.0})
  assert config['max_radius_m'] == pytest.approx(3.0)


def test_tight_mahalanobis_ceiling_warns_only_when_the_config_is_loaded(monkeypatch):
  # normalize_association_config runs per frame and per object (association window), so it must not warn.
  from controller.ilabs_tracking import warn_association_config
  warnings = []
  monkeypatch.setattr('controller.ilabs_tracking.log.warning', lambda *args: warnings.append(args))
  config = normalize_association_config({
    'method': 'position_mahalanobis',
    'max_radius_m': 2.0,
  })
  association_match_params(config)
  build_association_window(config, np.eye(7))
  assert config['max_radius_m'] == pytest.approx(2.0)
  assert not warnings

  warn_association_config(config)
  assert len(warnings) == 1
  assert 'position_mahalanobis with max_radius_m' in warnings[0][0]

  warn_association_config(normalize_association_config())
  assert len(warnings) == 1


def test_association_match_params_euclidean_uses_max_radius_as_threshold():
  distance_type, distance_threshold, max_radius_m = association_match_params({
    'method': 'euclidean',
    'max_radius_m': 3.5,
  })
  assert distance_type == rv.tracking.DistanceType.Euclidean
  assert distance_threshold == pytest.approx(3.5)
  assert max_radius_m == pytest.approx(3.5)


@pytest.mark.parametrize('association_config, expected_radius_m', [
  ({'method': 'euclidean'}, 6.0),
  ({'method': 'euclidean', 'max_radius_m': 3.5}, 3.5),
])
def test_association_match_params_euclidean_without_max_radius_uses_tracking_radius(
    association_config, expected_radius_m):
  distance_type, distance_threshold, max_radius_m = association_match_params(
    association_config, tracking_radius_m=6.0)
  assert distance_type == rv.tracking.DistanceType.Euclidean
  assert distance_threshold == pytest.approx(expected_radius_m)
  assert max_radius_m == pytest.approx(expected_radius_m)


def test_association_match_params_mahalanobis_uses_chi2_gate():
  distance_type, distance_threshold, max_radius_m = association_match_params({
    'method': 'position_mahalanobis',
    'gate_probability': 0.99,
    'max_radius_m': 10.0,
  })
  assert distance_type == rv.tracking.DistanceType.PositionMahalanobis
  assert distance_threshold == pytest.approx(rv.tracking.chi2_threshold(0.99, 3))
  assert max_radius_m == pytest.approx(10.0)


def _association_parent(trackers):
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config()
  tracker._lifecycle_lock = threading.Lock()
  tracker.trackers = trackers
  return tracker


def _association_child():
  child = IntelLabsTracking.__new__(IntelLabsTracking)
  child.association_config = normalize_association_config({
    'method': 'euclidean',
    'max_radius_m': 2.0,
  })
  child._lifecycle_lock = threading.Lock()
  child.trackers = {}
  return child


MAHALANOBIS_095 = {'method': 'position_mahalanobis', 'gate_probability': 0.95, 'max_radius_m': 10.0}


def test_apply_association_config_updates_tracker():
  child = _association_child()
  tracker = _association_parent({'person': child})
  tracker.applyAssociationConfig(MAHALANOBIS_095)
  assert tracker.association_config['method'] == 'position_mahalanobis'
  assert tracker.association_config['gate_probability'] == pytest.approx(0.95)
  assert child.association_config['method'] == 'position_mahalanobis'
  assert child.association_config['gate_probability'] == pytest.approx(0.95)
  assert child.association_config['max_radius_m'] == pytest.approx(10.0)


def test_apply_association_config_survives_a_tracker_added_meanwhile():
  # The MQTT thread adds category trackers while a cache refresh applies the config.
  tracker = _association_parent({})
  late = _association_child()
  first = SimpleNamespace(
    applyAssociationConfig=lambda config: tracker.trackers.setdefault('vehicle', late))
  tracker.trackers['person'] = first

  tracker.applyAssociationConfig(MAHALANOBIS_095)

  assert set(tracker.trackers) == {'person', 'vehicle'}


def test_apply_association_config_reaches_a_tracker_created_under_the_lock():
  # _createTrackers holds the lock from reading association_config until the tracker is in trackers.
  tracker = _association_parent({})
  created = _association_child()
  with tracker._lifecycle_lock:
    applying = threading.Thread(target=tracker.applyAssociationConfig, args=(MAHALANOBIS_095,))
    applying.start()
    applying.join(0.2)
    tracker.trackers['person'] = created
  applying.join(5)

  assert not applying.is_alive()
  assert created.association_config['method'] == 'position_mahalanobis'


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
  parent._lifecycle_lock = threading.Lock()
  parent._joined = False

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


@pytest.mark.parametrize('association_config, expected', [
  ({'method': 'euclidean', 'max_radius_m': 3.0},
   (rv.tracking.DistanceType.Euclidean, 3.0, 3.0)),
  ({'method': 'position_mahalanobis', 'gate_probability': 0.95, 'max_radius_m': 7.0},
   (rv.tracking.DistanceType.PositionMahalanobis, rv.tracking.chi2_threshold(0.95, 3), 7.0)),
])
def test_update_tracks_forwards_association_params(monkeypatch, association_config, expected):
  calls = []
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config(association_config)
  tracker.tracker = SimpleNamespace(track=lambda objects, timestamp, **kwargs: calls.append(
    (objects, timestamp, kwargs)))
  monkeypatch.setattr(IntelLabsTracking, 'to_rv_object', lambda self, sscape_object: sscape_object.name)
  person = SimpleNamespace(name='person', tracking_radius=2.0)
  car = SimpleNamespace(name='car', tracking_radius=10.0)

  tracker.update_tracks([person], 1.0)
  tracker.update_tracks_batched([[person], [car]], 2.0)

  assert [(objects, timestamp) for objects, timestamp, _ in calls] == [
    (['person'], 1.0), ([['person'], ['car']], 2.0)]
  distance_type, distance_threshold, max_radius_m = expected
  for _, _, kwargs in calls:
    assert kwargs['distance_type'] == distance_type
    assert kwargs['distance_threshold'] == pytest.approx(distance_threshold)
    assert kwargs['max_radius_m'] == pytest.approx(max_radius_m)
  # With max_radius_m set, objects' tracking_radius does not change birth clustering.
  assert calls[1][2]['birth_cluster_radius_m'] == pytest.approx(rv.tracking.DEFAULT_BIRTH_CLUSTER_RADIUS_M)


def test_update_tracks_euclidean_without_max_radius_gates_on_average_tracking_radius(monkeypatch):
  # As on main: the frame's average tracking_radius is the gate and the birth-clustering radius, the default
  # tracking_radius without objects.
  calls = []
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config({'method': 'euclidean'})
  tracker.tracker = SimpleNamespace(track=lambda objects, timestamp, **kwargs: calls.append(kwargs))
  monkeypatch.setattr(IntelLabsTracking, 'to_rv_object', lambda self, sscape_object: sscape_object.name)
  person = SimpleNamespace(name='person', tracking_radius=2.0)
  car = SimpleNamespace(name='car', tracking_radius=10.0)

  tracker.update_tracks([person, car], 1.0)
  tracker.update_tracks_batched([[person], [car, car]], 2.0)
  tracker.update_tracks([], 3.0)
  tracker.update_tracks_batched([[], []], 4.0)

  assert [kwargs['distance_type'] for kwargs in calls] == [rv.tracking.DistanceType.Euclidean] * 4
  assert [kwargs['distance_threshold'] for kwargs in calls] == pytest.approx([6.0, 22.0 / 3.0, 2.0, 2.0])
  assert [kwargs['max_radius_m'] for kwargs in calls] == pytest.approx([6.0, 22.0 / 3.0, 2.0, 2.0])
  assert calls[1]['birth_cluster_radius_m'] == pytest.approx(22.0 / 3.0)
  assert calls[3]['birth_cluster_radius_m'] == pytest.approx(2.0)


@pytest.mark.parametrize('association_config, warns', [
  ({'method': 'euclidean'}, False),
  ({'method': 'euclidean', 'max_radius_m': 3.0}, True),
  ({'method': 'position_mahalanobis'}, True),
])
def test_update_tracks_warns_when_tracking_radius_is_ignored(monkeypatch, association_config, warns):
  # Once per tracker, not every frame: the default config with the default vehicle asset (10 m) hits it.
  warnings = []
  monkeypatch.setattr('controller.ilabs_tracking.log.warning', lambda *args: warnings.append(args))
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.association_config = normalize_association_config(association_config)
  tracker.tracker = SimpleNamespace(track=lambda objects, timestamp, **kwargs: None)
  monkeypatch.setattr(IntelLabsTracking, 'to_rv_object', lambda self, sscape_object: sscape_object.name)
  car = SimpleNamespace(name='car', tracking_radius=10.0)

  for timestamp in (1.0, 2.0, 3.0):
    tracker.update_tracks([car], timestamp)
  tracker.update_tracks_batched([[car], [car]], 4.0)

  assert len(warnings) == (1 if warns else 0)
  # Another tracker warns again.
  other = IntelLabsTracking.__new__(IntelLabsTracking)
  other.association_config = tracker.association_config
  other.tracker = tracker.tracker
  other.update_tracks([car], 5.0)
  assert len(warnings) == (2 if warns else 0)


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
    has_measured_z=True,
  )
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)

  rv_object = tracker.to_rv_object(detected_object)

  assert rv_object.yaw == pytest.approx(yaw)
  assert rv_object.attributes.get('has_orientation') == 'true'
  assert rv_object.zMeasured is True


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
    has_measured_z=False,
  )
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)

  rv_object = tracker.to_rv_object(detected_object)

  assert rv_object.yaw == 0.0
  assert 'has_orientation' not in rv_object.attributes
  assert rv_object.zMeasured is False


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


def _make_tracked_object(uuid_value, yaw=0.0, attributes=None, vx=0.1, vy=0.2, vz=0.0):
  attrs = {'info': uuid_value}
  if attributes:
    attrs.update(attributes)
  return SimpleNamespace(
    attributes=attrs,
    x=1.0, y=2.0, z=0.0,
    vx=vx, vy=vy, vz=vz,
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


def test_build_association_window_euclidean_without_max_radius_draws_tracking_radius():
  config = normalize_association_config({'method': 'euclidean'})
  assert build_association_window(config, tracking_radius_m=6.0)['radius_m'] == pytest.approx(6.0)
  assert build_association_window(config)['radius_m'] == pytest.approx(2.0)


def test_from_tracked_object_draws_the_last_tracking_radius_gate(monkeypatch):
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config({'method': 'euclidean'})
  tracker.tracker = SimpleNamespace(track=lambda objects, timestamp, **kwargs: None)
  monkeypatch.setattr(IntelLabsTracking, 'to_rv_object', lambda self, sscape_object: None)
  tracker.update_tracks([SimpleNamespace(tracking_radius=2.0), SimpleNamespace(tracking_radius=10.0)], 1.0)

  result = tracker.from_tracked_object(
    _make_tracked_object("uuid-1"), [_make_sscape_object("uuid-1", has_detection_rotation=False)])

  assert result.association_window == {'method': 'euclidean', 'shape': 'circle', 'radius_m': pytest.approx(6.0)}


def test_from_tracked_object_publishes_vertical_velocity():
  tracked_object = _make_tracked_object("uuid-vz", vx=0.3, vy=-0.1, vz=0.45)
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config({'method': 'euclidean'})
  tracker.tracking_radius_m = 2.0

  result = tracker.from_tracked_object(
    tracked_object, [_make_sscape_object("uuid-vz", has_detection_rotation=False)])

  assert result.velocity.x == pytest.approx(0.3)
  assert result.velocity.y == pytest.approx(-0.1)
  assert result.velocity.z == pytest.approx(0.45)


def test_build_association_window_mahalanobis_is_ellipse():
  # Diagonal covariance → axis-aligned ellipse; a track without measured z: χ²(0.99,2) ≈ 9.21
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


def _mahalanobis_window(s00, s01, s11, gate_probability=0.99, z_measured=False):
  cov = np.eye(7)
  cov[0, 0], cov[0, 1], cov[1, 0], cov[1, 1] = s00, s01, s01, s11
  return build_association_window({
    'method': 'position_mahalanobis',
    'gate_probability': gate_probability,
    'max_radius_m': 10.0,
  }, cov, z_measured=z_measured)


def test_build_association_window_uses_the_track_degrees_of_freedom():
  """chi2(p, 2) for a track without measured z (x/y gate), chi2(p, 3) once it has measured z."""
  planar = _mahalanobis_window(1.0, 0.0, 0.25)
  assert planar['semi_major_m'] == pytest.approx(math.sqrt(rv.tracking.chi2_threshold(0.99, 2) * 1.0))
  assert planar['semi_minor_m'] == pytest.approx(math.sqrt(rv.tracking.chi2_threshold(0.99, 2) * 0.25))
  measured = _mahalanobis_window(1.0, 0.0, 0.25, z_measured=True)
  assert measured['semi_major_m'] == pytest.approx(math.sqrt(rv.tracking.chi2_threshold(0.99, 3) * 1.0))
  assert measured['semi_minor_m'] == pytest.approx(math.sqrt(rv.tracking.chi2_threshold(0.99, 3) * 0.25))


@pytest.mark.parametrize('z_measured, df', [(False, 2), (True, 3)])
def test_from_tracked_object_draws_the_window_with_the_track_degrees_of_freedom(z_measured, df):
  tracked_object = _make_tracked_object("uuid-3")
  tracked_object.zMeasured = z_measured
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.all_tracker_objects = []
  tracker.uuid_manager = SimpleNamespace(assignID=lambda obj: None)
  tracker.association_config = normalize_association_config()
  tracker.tracking_radius_m = 2.0

  result = tracker.from_tracked_object(tracked_object, [_make_sscape_object("uuid-3", has_detection_rotation=False)])

  # measurement_covariance is 0.25 * I.
  assert result.association_window['semi_major_m'] == pytest.approx(
    math.sqrt(rv.tracking.chi2_threshold(0.99, df) * 0.25))


def _angle_difference_modulo_pi(a, b):
  """An ellipse is symmetric under a half turn, so its angle is defined modulo pi."""
  return math.remainder(a - b, math.pi)


@pytest.mark.parametrize('degrees', [0.0, 30.0, 90.0, -60.0, 135.0])
def test_build_association_window_follows_rotated_covariance(degrees):
  """S_xy = R diag(4, 1) R^T: semi-axes sqrt(chi2 * 4) and sqrt(chi2 * 1), major axis at the angle."""
  angle = math.radians(degrees)
  c, s = math.cos(angle), math.sin(angle)
  window = _mahalanobis_window(4 * c * c + s * s, 3 * c * s, 4 * s * s + c * c, 0.95)
  chi2 = rv.tracking.chi2_threshold(0.95, 2)
  assert window['shape'] == 'ellipse'
  assert window['semi_major_m'] == pytest.approx(math.sqrt(chi2 * 4.0))
  assert window['semi_minor_m'] == pytest.approx(math.sqrt(chi2 * 1.0))
  assert _angle_difference_modulo_pi(window['angle_rad'], angle) == pytest.approx(0.0, abs=1e-9)


def test_build_association_window_major_axis_follows_larger_variance():
  window = _mahalanobis_window(1.0, 0.0, 4.0)
  chi2 = rv.tracking.chi2_threshold(0.99, 2)
  assert window['semi_major_m'] == pytest.approx(math.sqrt(chi2 * 4.0))
  assert window['semi_minor_m'] == pytest.approx(math.sqrt(chi2 * 1.0))
  assert _angle_difference_modulo_pi(window['angle_rad'], math.pi / 2) == pytest.approx(0.0, abs=1e-9)


def test_build_association_window_clamps_negative_eigenvalues():
  """Eigenvalues 3 and -1, major axis at 45 degrees: the minor semi-axis is 0, not NaN."""
  window = _mahalanobis_window(1.0, 2.0, 1.0)
  assert window['semi_major_m'] == pytest.approx(math.sqrt(rv.tracking.chi2_threshold(0.99, 2) * 3.0))
  assert window['semi_minor_m'] == 0.0
  assert _angle_difference_modulo_pi(window['angle_rad'], math.pi / 4) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize('s00', [math.nan, math.inf])
def test_build_association_window_falls_back_to_circle_for_nonfinite_covariance(s00):
  window = _mahalanobis_window(s00, 0.1, 0.3)
  assert window == {'method': 'position_mahalanobis', 'shape': 'circle', 'radius_m': 10.0}


def test_build_association_window_clips_semi_axes_to_max_radius():
  # Unclipped χ²(0.99) radius for S=100·I is ~30 m; the hard gate is 10 m.
  cov = np.diag([100.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0])
  window = build_association_window({
    'method': 'position_mahalanobis',
    'gate_probability': 0.99,
    'max_radius_m': 10.0,
  }, cov)
  assert window['shape'] == 'ellipse'
  assert window['semi_major_m'] == pytest.approx(10.0)
  assert window['semi_minor_m'] == pytest.approx(10.0)


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
