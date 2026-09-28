# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from analytics.prediction import PredictionManager
from scene_common.geometry import Point, Region, Tripwire


def _scene(regions=None, tripwires=None):
  return SimpleNamespace(
    uid='scene-1',
    name='Scene 1',
    regions=regions or {},
    tripwires=tripwires or {},
  )


def _object(
    location, velocity=(1.0, 0.0, 0.0), interval_ms=1000,
    start_delay_ms=None, horizon_intervals=2, enabled=True):
  return SimpleNamespace(
    gid='object-1',
    sceneLoc=Point(location),
    velocity=Point(velocity),
    extrapolation_enabled=enabled,
    extrapolation_interval_ms=interval_ms,
    extrapolation_start_delay_ms=start_delay_ms,
    extrapolation_horizon_intervals=horizon_intervals,
    position_source='observed',
  )


class TestPredictionManager:

  def test_uses_source_velocity_after_expected_interval(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((1.0, 2.0, 3.0))], 10.0)

    before = manager.predict(scene, 10.999)
    result = manager.predict(scene, 11.0)

    assert before.samples == []
    assert result.samples[0].location.asCartesianVector == pytest.approx(
      [2.0, 2.0, 3.0])
    assert result.samples[0].prediction_age_ms == pytest.approx(1000.0)

  def test_predictions_always_use_latest_real_baseline(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((0.0, 0.0, 0.0))], 0.0)

    first = manager.predict(scene, 1.0).samples[0]
    second = manager.predict(scene, 2.0).samples[0]

    assert first.location.x == pytest.approx(1.0)
    assert second.location.x == pytest.approx(2.0)

  def test_consecutive_observation_smooths_source_and_measured_velocity(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(
      scene, 'person', [_object((0.0, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 0.0)
    manager.observe(
      scene, 'person', [_object((1.0, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 1.0)

    result = manager.predict(scene, 2.0)

    assert result.samples[0].location.x == pytest.approx(2.75)

  def test_real_observation_resets_position_exactly(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((0.0, 0.0, 0.0))], 0.0)
    manager.predict(scene, 1.5)
    manager.observe(scene, 'person', [_object((10.0, 0.0, 0.0))], 2.0)

    result = manager.predict(scene, 3.0)

    assert result.samples[0].location.x == pytest.approx(12.0)

  def test_out_of_order_observation_is_ignored(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((0.0, 0.0, 0.0))], 5.0)
    manager.observe(scene, 'person', [_object((10.0, 0.0, 0.0))], 4.0)

    result = manager.predict(scene, 6.0)

    assert result.samples[0].location.x == pytest.approx(1.0)

  def test_duplicate_observation_timestamp_is_not_fresh(self):
    manager = PredictionManager()
    scene = _scene()
    obj = _object((0.0, 0.0, 0.0))
    obj.observation_timestamp = 5.0
    manager.observe(scene, 'person', [obj], 5.0)

    assert manager.is_fresh_observation(
      scene.uid, 'person', obj, 6.0) is False

  def test_receipt_time_advances_freshness_when_source_time_is_stale(self):
    manager = PredictionManager()
    scene = _scene()
    obj = _object((0.0, 0.0, 0.0))
    obj.observation_timestamp = 5.0
    manager.observe(scene, 'person', [obj], 5.0, scheduling_timestamp=10.0)

    assert manager.is_fresh_observation(
      scene.uid, 'person', obj, 5.0, scheduling_timestamp=11.0) is True

  def test_disabled_object_is_not_predicted(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(
      scene, 'person', [_object((0.0, 0.0, 0.0), enabled=False)], 0.0)

    assert manager.predict(scene, 2.0).samples == []

  def test_prediction_expires_at_bounded_horizon(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(
      scene, 'person', [_object((0.0, 0.0, 0.0), interval_ms=1000, horizon_intervals=2)], 0.0)

    manager.predict(scene, 1.0)
    manager.predict(scene, 2.0)
    at_horizon = manager.predict(scene, 3.0)
    after_horizon = manager.predict(scene, 4.001)

    assert len(at_horizon.samples) == 1
    assert after_horizon.samples == []
    assert manager.has_scene(scene.uid) is False

  def test_prediction_starts_after_configured_delay(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object(
      (0.0, 0.0, 0.0), interval_ms=200, start_delay_ms=1500,
      horizon_intervals=2)], 0.0)

    before_delay = manager.predict(scene, 1.499)
    first = manager.predict(scene, 1.5).samples[0]
    second = manager.predict(scene, 1.7).samples[0]

    assert before_delay.samples == []
    assert first.location.x == pytest.approx(1.5)
    assert first.prediction_age_ms == pytest.approx(1500.0)
    assert second.location.x == pytest.approx(1.7)

  def test_prediction_waits_for_next_scheduled_interval(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((0.0, 0.0, 0.0))], 0.0)

    first = manager.predict(scene, 1.0).samples[0]
    no_duplicate = manager.predict(scene, 1.5).samples
    second = manager.predict(scene, 2.0).samples[0]

    assert first.prediction_timestamp == pytest.approx(1.0)
    assert no_duplicate == []
    assert second.prediction_timestamp == pytest.approx(2.0)

  def test_delayed_prediction_tick_does_not_replay_missed_samples(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((0.0, 0.0, 0.0))], 0.0)

    delayed = manager.predict(scene, 1.9).samples[0]
    no_replay = manager.predict(scene, 1.91).samples

    assert delayed.prediction_timestamp == pytest.approx(1.9)
    assert delayed.location.x == pytest.approx(1.9)
    assert no_replay == []

  def test_discard_scene_removes_all_prediction_state(self):
    manager = PredictionManager()
    scene = _scene()
    manager.observe(scene, 'person', [_object((0.0, 0.0, 0.0))], 0.0)

    manager.discard_scene(scene.uid, 1.0)

    assert manager.has_scene(scene.uid) is False


class TestPotentialEvents:

  @staticmethod
  def _region():
    return Region('roi-1', 'ROI', {
      'points': [[1.0, -1.0], [3.0, -1.0], [3.0, 1.0], [1.0, 1.0]],
    })

  def test_region_prediction_is_confirmed_by_real_membership_change(self):
    manager = PredictionManager()
    scene = _scene(regions={'roi-1': self._region()})
    manager.observe(
      scene, 'person', [_object((0.0, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 0.0)
    potential = manager.predict(scene, 1.0).events

    resolved = manager.observe(
      scene, 'person', [_object((2.0, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 1.1)

    assert len(potential) == 1
    assert potential[0].transition == 'entered'
    assert resolved[0].event_id == potential[0].event_id
    assert resolved[0].status == 'confirmed'

  def test_region_prediction_is_rejected_by_real_observation(self):
    manager = PredictionManager()
    scene = _scene(regions={'roi-1': self._region()})
    manager.observe(
      scene, 'person', [_object((0.0, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 0.0)
    potential = manager.predict(scene, 1.0).events[0]

    resolved = manager.observe(
      scene, 'person', [_object((0.5, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 1.1)

    assert resolved[0].event_id == potential.event_id
    assert resolved[0].status == 'rejected'

  def test_unresolved_event_expires_with_prediction(self):
    manager = PredictionManager()
    scene = _scene(regions={'roi-1': self._region()})
    manager.observe(
      scene, 'person', [_object((0.0, 0.0, 0.0), velocity=(2.0, 0.0, 0.0))], 0.0)
    potential = manager.predict(scene, 1.0).events[0]

    expired = manager.predict(scene, 3.001).events

    assert expired[0].event_id == potential.event_id
    assert expired[0].status == 'expired'

  def test_tripwire_prediction_is_deduplicated(self):
    manager = PredictionManager()
    tripwire = Tripwire(
      'tw-1', 'Tripwire', {'points': [[-2.0, 0.0], [2.0, 0.0]]})
    scene = _scene(tripwires={'tw-1': tripwire})
    manager.observe(
      scene, 'person',
      [_object((0.0, -1.0, 0.0), velocity=(0.0, 2.0, 0.0))], 0.0)

    first = manager.predict(scene, 1.0)
    second = manager.predict(scene, 1.5)

    assert len(first.events) == 1
    assert first.events[0].geometry_type == 'tripwire'
    assert second.events == []
