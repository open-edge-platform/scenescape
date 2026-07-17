# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import orjson
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from analytics.analytics_models import AnalyticsObject
from analytics.event_publisher import publish_events
from analytics.state import AnalyticsStateStore
from analytics.tripwire import TripwireEvent
from scene_common.chain_data import ChainData
from scene_common.geometry import Point, Region, Tripwire


def _region(uid='roi-1', name='ROI', singleton_type=None):
  return Region(uid, name, {
    'points': [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
    'singleton_type': singleton_type,
  })


def _tripwire(uid='tw-1', name='Tripwire'):
  return Tripwire(uid, name, {'points': [[0.0, 0.0], [10.0, 0.0]]})


def _analytics_object(gid='obj-1'):
  return AnalyticsObject(
    gid=gid,
    category='person',
    frameCount=5,
    sceneLoc=Point(1.0, 1.0, 0.0),
    chain_data=ChainData(regions={}, publishedLocations=[], persist={}),
  )


def _scene(events, analytics_state, uid='scene-1', name='Test Scene'):
  return SimpleNamespace(uid=uid, name=name, events=events, analytics_state=analytics_state)


class TestEventPublisher:
  """Unit tests for analytics.event_publisher.publish_events."""

  def test_publish_events_publishes_region_events_and_clears_transient_event_lists(self):
    """Region events are published and objects/count queues are cleared afterward."""

    class FakeRegion:
      def __init__(self):
        self.uuid = 'roi-1'
        self.name = 'ROI'
        self.singleton_type = None

      def serialize(self):
        return {'name': self.name}

    region = FakeRegion()
    mock_publish = MagicMock()
    scene = SimpleNamespace(
      uid='scene-1',
      name='Test Scene',
      events={'objects': [('roi-1', region)]},
      analytics_state=AnalyticsStateStore(),
    )

    with patch('analytics.event_publisher._build_all_region_objs_list', return_value=({}, 0)), \
         patch('analytics.event_publisher._build_entered_objs_list'), \
         patch('analytics.event_publisher._build_exited_objs_list'), \
         patch('analytics.event_publisher._clear_sensor_values_on_exit'), \
         patch('analytics.event_publisher.Region', FakeRegion):
      publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    assert mock_publish.call_count == 1
    assert 'objects' not in scene.events
    assert 'count' not in scene.events

  def test_region_event_metadata_reflects_singleton_type(self):
    """fromSensor is True for singleton (sensor-backed) regions, False otherwise."""
    plain_region = _region('roi-1', 'Plain ROI', singleton_type=None)
    sensor_region = _region('roi-2', 'Sensor ROI', singleton_type='environmental')
    state_store = AnalyticsStateStore()
    mock_publish = MagicMock()
    scene = _scene({'objects': [('roi-1', plain_region), ('roi-2', sensor_region)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    assert mock_publish.call_count == 2
    payloads = [orjson.loads(call.args[1]) for call in mock_publish.call_args_list]
    by_id = {p['region_id']: p for p in payloads}
    assert by_id['roi-1']['metadata']['fromSensor'] is False
    assert by_id['roi-2']['metadata']['fromSensor'] is True

  def test_tripwire_event_published_only_when_objects_present(self):
    """Tripwire events with zero crossing objects are not published."""
    tripwire = _tripwire()
    state_store = AnalyticsStateStore()
    mock_publish = MagicMock()
    scene = _scene({'objects': [('tw-1', tripwire)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    mock_publish.assert_not_called()

  def test_tripwire_event_published_when_objects_present(self):
    tripwire = _tripwire()
    state_store = AnalyticsStateStore()
    state_store.tripwire('tw-1').objects['person'] = [
      TripwireEvent(_analytics_object(), 'forward'),
    ]
    mock_publish = MagicMock()
    scene = _scene({'objects': [('tw-1', tripwire)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    assert mock_publish.call_count == 1
    topic = mock_publish.call_args.args[0]
    assert 'tripwire' in topic

  def test_entered_objects_reused_from_detections_dict(self):
    """Entered objects already present in the region's current objects reuse detections_dict."""
    region = _region()
    obj = _analytics_object('obj-1')
    state_store = AnalyticsStateStore()
    rstate = state_store.region('roi-1')
    rstate.objects['person'] = [obj]
    rstate.entered['person'] = [obj]
    mock_publish = MagicMock()
    scene = _scene({'objects': [('roi-1', region)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    payload = orjson.loads(mock_publish.call_args.args[1])
    assert [e['id'] for e in payload['entered']] == ['obj-1']

  def test_entered_objects_built_when_missing_from_detections_dict(self):
    """Entered objects not present in the region's tracked objects (sensor-only) are built separately."""
    region = _region(singleton_type='environmental')
    obj = _analytics_object('sensor-obj')
    state_store = AnalyticsStateStore()
    rstate = state_store.region('roi-1')
    # obj is "entered" but not part of the currently tracked region objects
    rstate.entered['person'] = [obj]
    mock_publish = MagicMock()
    scene = _scene({'objects': [('roi-1', region)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    payload = orjson.loads(mock_publish.call_args.args[1])
    assert [e['id'] for e in payload['entered']] == ['sensor-obj']

  def test_exited_objects_include_dwell_time(self):
    region = _region()
    obj = _analytics_object('obj-1')
    state_store = AnalyticsStateStore()
    rstate = state_store.region('roi-1')
    rstate.exited['person'] = [(obj, 12.5)]
    mock_publish = MagicMock()
    scene = _scene({'objects': [('roi-1', region)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    payload = orjson.loads(mock_publish.call_args.args[1])
    assert payload['exited'][0]['object']['id'] == 'obj-1'
    assert payload['exited'][0]['dwell'] == 12.5

  def test_clear_frame_state_only_applied_to_regions_not_tripwires(self):
    """_clear_sensor_values_on_exit must not touch Tripwire state (no clear_frame_state on it)."""
    region = _region()
    tripwire = _tripwire()
    state_store = AnalyticsStateStore()
    rstate = state_store.region('roi-1')
    rstate.entered['person'] = [_analytics_object('obj-1')]
    state_store.tripwire('tw-1').objects['person'] = [
      TripwireEvent(_analytics_object('obj-2'), 'forward'),
    ]
    mock_publish = MagicMock()
    scene = _scene({'objects': [('roi-1', region), ('tw-1', tripwire)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    assert rstate.entered == {}
    assert rstate.exited == {}
    # Tripwire state has no clear_frame_state; objects dict remains untouched.
    assert state_store.tripwire('tw-1').objects['person'] != []

  def test_pops_objects_and_count_keys_after_publish(self):
    region = _region()
    state_store = AnalyticsStateStore()
    mock_publish = MagicMock()
    scene = _scene({'objects': [('roi-1', region)], 'count': [('roi-1', region)]}, state_store)

    publish_events(scene, '2026-01-01T00:00:01.000Z', mock_publish)

    assert 'objects' not in scene.events
    assert 'count' not in scene.events
