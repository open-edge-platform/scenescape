#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the SceneDataIngestion adapter (Phase 4)."""

import pytest
from types import SimpleNamespace

from scene_common.geometry import Point

from scene_common.ingestion import SceneDataIngestion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person(obj_id='obj-1', **extra):
  return {'id': obj_id, 'type': 'person', 'translation': [1.0, 2.0, 0.0], **extra}


def _vehicle(obj_id='v-1', **extra):
  return {'id': obj_id, 'type': 'vehicle', 'translation': [3.0, 4.0, 0.0], **extra}


# ---------------------------------------------------------------------------
# Basic deserialization
# ---------------------------------------------------------------------------

def test_ingest_empty_list_produces_no_objects():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [], {})
  assert ingestion.get_objects('person') == []


def test_ingest_single_object_sets_core_fields():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  objs = ingestion.get_objects('person')
  assert len(objs) == 1
  obj = objs[0]
  assert obj.gid == 'obj-1'
  assert obj.category == 'person'
  assert obj.sceneLoc == Point(1.0, 2.0, 0.0)


def test_ingest_omitted_visibility_is_none():
  """Omitted visibility must stay None so Analytics can FOV-fill."""
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  assert ingestion._objects['obj-1'].visibility is None


def test_ingest_explicit_visibility_is_preserved():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(visibility=['cam1'])], {})
  assert ingestion._objects['obj-1'].visibility == ['cam1']


def test_ingest_explicit_empty_visibility_is_preserved():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(visibility=[])], {})
  assert ingestion._objects['obj-1'].visibility == []


def test_ingest_preserves_identity_across_frames():
  """ChainData is preserved when the same object id reappears."""
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  first_ref = ingestion._objects['obj-1']
  first_ref.chain_data.publishedLocations.append(Point(0.0, 0.0, 0.0))

  ingestion.ingest('person', [_person(translation=[5.0, 6.0, 0.0])], {})
  second_ref = ingestion._objects['obj-1']

  assert second_ref is first_ref
  assert second_ref.chain_data.publishedLocations[0] == Point(0.0, 0.0, 0.0)


def test_ingest_evicts_stale_objects_for_detection_type():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person('p1'), _person('p2')], {})
  assert 'p1' in ingestion._objects
  assert 'p2' in ingestion._objects

  ingestion.ingest('person', [_person('p1')], {})
  assert 'p1' in ingestion._objects
  assert 'p2' not in ingestion._objects


def test_ingest_evicts_stale_history():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person('p1')], {})
  assert 'p1' in ingestion._history

  ingestion.ingest('person', [], {})
  assert 'p1' not in ingestion._history


def test_ingest_does_not_evict_other_detection_types():
  """Objects of a different type are not affected by ingesting type 'vehicle'."""
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  ingestion.ingest('vehicle', [_vehicle()], {})
  ingestion.ingest('vehicle', [], {})

  assert 'obj-1' in ingestion._objects  # person survives
  assert 'v-1' not in ingestion._objects  # vehicle was evicted


def test_get_objects_filters_by_detection_type():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  ingestion.ingest('vehicle', [_vehicle()], {})

  persons = ingestion.get_objects('person')
  vehicles = ingestion.get_objects('vehicle')
  assert [o.gid for o in persons] == ['obj-1']
  assert [o.gid for o in vehicles] == ['v-1']


# ---------------------------------------------------------------------------
# Timestamp resolution
# ---------------------------------------------------------------------------

def test_first_seen_from_mqtt_payload_takes_priority():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(first_seen='2026-01-01T00:00:00.000Z')], {})
  obj = ingestion._objects['obj-1']
  assert obj.first_seen is not None
  assert obj.when == obj.first_seen


def test_first_seen_from_history_used_when_not_in_payload():
  ingestion = SceneDataIngestion()
  ingestion._history['obj-1'] = {'first_seen': 99.9}
  ingestion.ingest('person', [_person()], {})
  obj = ingestion._objects['obj-1']
  assert obj.first_seen == 99.9
  assert obj.when == 99.9


def test_first_seen_from_current_time_when_no_data(monkeypatch):
  import scene_common.ingestion as m
  monkeypatch.setattr(m, 'get_epoch_time', lambda *a, **kw: 42.0)

  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  obj = ingestion._objects['obj-1']
  assert obj.first_seen == 42.0
  assert ingestion._history['obj-1']['first_seen'] == 42.0


# ---------------------------------------------------------------------------
# Sensor deserialization
# ---------------------------------------------------------------------------

def test_environmental_sensor_goes_to_env_sensor_state():
  sensors = {'temp': SimpleNamespace(singleton_type='environmental')}
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(sensors={'temp': {'values': [('t', 25.0)]}})], sensors)
  obj = ingestion._objects['obj-1']
  assert 'temp' in obj.chain_data.env_sensor_state
  assert obj.chain_data.env_sensor_state['temp']['readings'] == [('t', 25.0)]


def test_attribute_sensor_goes_to_attr_sensor_events():
  sensors = {'status': SimpleNamespace(singleton_type='attribute')}
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(sensors={'status': {'values': [('t', 'active')]}})], sensors)
  obj = ingestion._objects['obj-1']
  assert 'status' in obj.chain_data.attr_sensor_events
  assert obj.chain_data.attr_sensor_events['status'] == [('t', 'active')]


def test_unknown_sensor_defaults_to_environmental():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(sensors={'unknown': {'values': [('t', 1.0)]}})], {})
  obj = ingestion._objects['obj-1']
  assert 'unknown' in obj.chain_data.env_sensor_state


def test_sensor_with_empty_values_is_ignored():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(sensors={'empty': {'values': []}})], {})
  obj = ingestion._objects['obj-1']
  assert 'empty' not in obj.chain_data.env_sensor_state
  assert 'empty' not in obj.chain_data.attr_sensor_events


# ---------------------------------------------------------------------------
# bbMeters reconstruction
# ---------------------------------------------------------------------------

def test_bbmeters_reconstructed_from_size():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person(size=[1.8, 0.5, 0.3])], {})
  obj = ingestion._objects['obj-1']
  assert obj.bbMeters is not None
  assert obj.bbMeters.width == 0.5
  assert obj.bbMeters.height == 0.3


def test_bbmeters_is_none_when_no_size():
  ingestion = SceneDataIngestion()
  ingestion.ingest('person', [_person()], {})
  assert ingestion._objects['obj-1'].bbMeters is None


# ---------------------------------------------------------------------------
# is_environmental_sensor static method
# ---------------------------------------------------------------------------

def test_is_environmental_returns_true_for_environmental_sensor():
  sensors = {'s': SimpleNamespace(singleton_type='environmental')}
  assert SceneDataIngestion._is_environmental_sensor('s', sensors) is True


def test_is_environmental_returns_false_for_attribute_sensor():
  sensors = {'s': SimpleNamespace(singleton_type='attribute')}
  assert SceneDataIngestion._is_environmental_sensor('s', sensors) is False


def test_is_environmental_defaults_to_true_for_unknown():
  assert SceneDataIngestion._is_environmental_sensor('unknown', {}) is True


def test_is_environmental_defaults_to_true_when_singleton_type_none():
  sensors = {'s': SimpleNamespace(singleton_type=None)}
  assert SceneDataIngestion._is_environmental_sensor('s', sensors) is True


# ---------------------------------------------------------------------------
# deserialize backward-compat path
# ---------------------------------------------------------------------------

def test_deserialize_returns_same_list_if_not_dicts():
  ingestion = SceneDataIngestion()
  already_objects = [SimpleNamespace(gid='x')]
  result = ingestion.deserialize(already_objects, {})
  assert result is already_objects


def test_deserialize_returns_empty_for_none():
  ingestion = SceneDataIngestion()
  assert ingestion.deserialize(None, {}) == []


def test_deserialize_builds_objects_and_indexes_by_gid():
  ingestion = SceneDataIngestion()
  result = ingestion.deserialize([_person('p1'), _person('p2')], {})
  assert len(result) == 2
  assert 'p1' in ingestion._objects
  assert 'p2' in ingestion._objects
