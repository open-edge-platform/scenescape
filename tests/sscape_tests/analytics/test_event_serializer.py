# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from analytics.event_serializer import build_objects_dict, build_objects_list, serialize_for_event
from analytics.tripwire import TripwireEvent
from scene_common.chain_data import ChainData
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

  def test_build_objects_dict_last_write_wins_on_duplicate_gid(self):
    """Duplicate gids collapse to the last serialised entry."""
    a = _make_obj()
    b = _make_obj()
    b.category = 'vehicle'

    detections = build_objects_dict([a, b])

    assert len(detections) == 1
    assert detections['obj-1']['type'] == 'vehicle'

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

  def test_rotation_included_when_present(self):
    """rotation is only added to the payload when set on the source object."""
    obj = _make_obj()
    obj.rotation = [0.0, 0.0, 0.0, 1.0]

    result = serialize_for_event(obj)

    assert result['rotation'] == [0.0, 0.0, 0.0, 1.0]

  def test_rotation_absent_when_none(self):
    obj = _make_obj()
    obj.rotation = None

    result = serialize_for_event(obj)

    assert 'rotation' not in result

  def test_metadata_merged_excluding_reid_key(self):
    """metadata dict is merged in, but a 'reid' entry within it is dropped."""
    obj = _make_obj()
    obj.metadata = {'age': 'adult', 'gender': 'unknown', 'reid': 'should-be-excluded'}

    result = serialize_for_event(obj)

    assert result['metadata']['age'] == 'adult'
    assert result['metadata']['gender'] == 'unknown'
    assert 'reid' not in result['metadata']

  def test_reid_embedding_serialised_as_list_with_dimensions(self):
    """reid embedding_vector is converted to a plain float list plus dimensions."""
    obj = _make_obj()
    obj.reid = {'embedding_vector': [0.1, 0.2, 0.3], 'model_name': 'facenet'}

    result = serialize_for_event(obj)

    assert result['metadata']['reid']['embedding_vector'] == pytest.approx([0.1, 0.2, 0.3])
    assert result['metadata']['reid']['embedding_dimensions'] == 3
    assert result['metadata']['reid']['model_name'] == 'facenet'

  def test_reid_absent_when_no_embedding_vector(self):
    obj = _make_obj()
    obj.reid = {}

    result = serialize_for_event(obj)

    assert 'metadata' not in result or 'reid' not in result.get('metadata', {})

  def test_reid_absent_when_embedding_vector_is_none(self):
    obj = _make_obj()
    obj.reid = {'embedding_vector': None}

    result = serialize_for_event(obj)

    assert 'metadata' not in result or 'reid' not in result.get('metadata', {})

  def test_prev_translation_present_when_multiple_locations(self):
    obj = _make_obj()
    obj.chain_data.publishedLocations = [Point(1.0, 1.0, 0.0), Point(0.0, 0.0, 0.0)]

    result = serialize_for_event(obj)

    assert 'prev_translation' in result

  def test_prev_translation_absent_with_single_location(self):
    obj = _make_obj()
    obj.chain_data.publishedLocations = [Point(1.0, 1.0, 0.0)]

    result = serialize_for_event(obj)

    assert 'prev_translation' not in result

  def test_region_dwell_computed_when_include_region_dwell_true(self):
    obj = _make_obj()
    obj.chain_data.regions = {'zone-a': {'entered': '2026-01-01T00:00:00.000Z'}}

    result = serialize_for_event(obj, include_region_dwell=True, current_time=10.0)

    assert 'dwell' in result['regions']['zone-a']

  def test_regions_passed_through_raw_when_dwell_disabled(self):
    obj = _make_obj()
    obj.chain_data.regions = {'zone-a': {'entered': '2026-01-01T00:00:00.000Z'}}

    result = serialize_for_event(obj, include_region_dwell=False)

    assert 'dwell' not in result['regions']['zone-a']

  def test_sensors_output_merges_environmental_and_attribute(self):
    obj = _make_obj()
    obj.chain_data.env_sensor_state = {'temp-1': {'readings': [('t0', 21.5)]}}
    obj.chain_data.attr_sensor_events = {'badge-1': [('t0', 'authorized')]}

    result = serialize_for_event(obj, include_sensors=True)

    assert result['sensors']['temp-1']['values'] == [('t0', 21.5)]
    assert result['sensors']['badge-1']['values'] == [('t0', 'authorized')]

  def test_empty_environmental_sensor_readings_still_emit_key(self):
    obj = _make_obj()
    obj.chain_data.env_sensor_state = {'temp-1': {'readings': []}}

    result = serialize_for_event(obj, include_sensors=True)

    assert result['sensors']['temp-1']['values'] == []

  def test_visibility_included_when_present(self):
    obj = _make_obj()
    obj.visibility = ['cam1', 'cam2']

    result = serialize_for_event(obj)

    assert result['visibility'] == ['cam1', 'cam2']

  def test_visibility_included_when_empty_list(self):
    obj = _make_obj()
    obj.visibility = []

    result = serialize_for_event(obj)

    assert result['visibility'] == []

  def test_visibility_absent_when_attribute_missing(self):
    obj = _make_obj()
    del obj.visibility

    result = serialize_for_event(obj)

    assert 'visibility' not in result

  def test_persistent_data_included_when_present(self):
    obj = _make_obj()
    obj.chain_data.persist = {'visit_count': 3}

    result = serialize_for_event(obj)

    assert result['persistent_data'] == {'visit_count': 3}

  def test_persistent_data_absent_when_empty(self):
    obj = _make_obj()
    obj.chain_data.persist = {}

    result = serialize_for_event(obj)

    assert 'persistent_data' not in result

  def test_similarity_and_first_seen_included_only_when_present(self):
    obj = _make_obj()
    obj.similarity = 0.87
    obj.first_seen = 0.0

    result = serialize_for_event(obj)

    assert result['similarity'] == 0.87
    assert 'first_seen' in result

  def test_similarity_absent_when_attribute_missing(self):
    obj = _make_obj()

    result = serialize_for_event(obj)

    assert 'similarity' not in result
    assert 'first_seen' not in result
