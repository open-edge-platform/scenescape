# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from controller.analytics.event_serializer import build_objects_dict, build_objects_list, serialize_for_event
from controller.analytics.tripwire import TripwireEvent
from controller.moving_object import ChainData
from scene_common.geometry import Point


def _make_obj(velocity=None):
  obj = SimpleNamespace()
  obj.gid = 'obj-1'
  obj.category = 'person'
  obj.sceneLoc = Point(1.0, 2.0, 0.0)
  obj.velocity = velocity
  obj.size = [1, 0.5, 1.8]
  obj.rotation = None
  obj.metadata = None
  obj.reid = {}
  obj.visibility = []
  obj.confidence = 0.9
  obj.info = {'category': 'person', 'confidence': 0.9}
  obj.chain_data = ChainData(regions={}, publishedLocations=[], persist={})
  return obj


class TestEventSerializer:

  def test_serialize_analytics_object_returns_required_fields(self):
    """serialize_for_event produces id, type, translation, size, velocity."""
    obj = _make_obj(velocity=Point(1.0, 2.0))
    result = serialize_for_event(obj)

    assert result['id'] == 'obj-1'
    assert result['type'] == 'person'
    assert 'translation' in result
    assert 'velocity' in result
    assert 'size' in result

  def test_serialize_defaults_missing_velocity_to_zero(self):
    """Objects with no velocity get a zero velocity vector."""
    obj = _make_obj(velocity=None)
    result = serialize_for_event(obj)

    assert result['velocity'] == [0, 0, 0] or result['velocity'] == [0, 0]

  def test_tripwire_event_direction_included(self):
    """TripwireEvent wraps an object and adds direction to the output."""
    obj = _make_obj(velocity=None)
    event = TripwireEvent(obj, 'entering')

    result = serialize_for_event(event)

    assert result['id'] == 'obj-1'
    assert result['direction'] == 'entering'

  def test_build_objects_dict_keyed_by_gid(self):
    """build_objects_dict returns {gid: dict} for a TripwireEvent list."""
    obj = _make_obj(velocity=None)
    event = TripwireEvent(obj, 'entering')

    detections = build_objects_dict([event])

    assert list(detections.keys()) == ['obj-1']
    assert detections['obj-1']['direction'] == 'entering'
    assert 'sensors' not in detections['obj-1']

  def test_build_objects_list_returns_ordered_list(self):
    """build_objects_list returns serialised dicts in input order."""
    a = _make_obj()
    a.gid = 'a'
    b = _make_obj()
    b.gid = 'b'

    result = build_objects_list([a, b])

    assert [r['id'] for r in result] == ['a', 'b']

  def test_sensors_not_included_by_default(self):
    """Sensor data is absent unless include_sensors=True."""
    obj = _make_obj()
    result = serialize_for_event(obj, include_sensors=False)

    assert 'sensors' not in result
