# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from analytics.analytics_models import AnalyticsObject
from analytics.sensors import (
  update_attribute_sensor_events,
  update_environmental_sensor_readings,
)
from scene_common.chain_data import ChainData
from scene_common.geometry import Point


def _chain_data():
  return ChainData(regions={}, publishedLocations=[], persist={})


def _obj(gid='obj-1'):
  return AnalyticsObject(
    gid=gid,
    category='person',
    frameCount=5,
    sceneLoc=Point(0.0, 0.0, 0.0),
    chain_data=_chain_data(),
  )


class TestUpdateEnvironmentalSensorReadings:
  def test_first_reading_initialises_state(self):
    obj = _obj()

    result = update_environmental_sensor_readings([obj], 'temp-1', 21.5, '2026-01-01T00:00:00Z')

    assert result is True
    assert obj.chain_data.env_sensor_state['temp-1']['readings'] == [('2026-01-01T00:00:00Z', 21.5)]

  def test_changed_value_appends_new_reading(self):
    obj = _obj()
    obj.chain_data.env_sensor_state['temp-1'] = {'readings': [('t0', 20.0)]}

    update_environmental_sensor_readings([obj], 'temp-1', 25.0, 't1')

    assert obj.chain_data.env_sensor_state['temp-1']['readings'] == [('t0', 20.0), ('t1', 25.0)]

  def test_unchanged_value_updates_timestamp_only(self):
    obj = _obj()
    obj.chain_data.env_sensor_state['temp-1'] = {'readings': [('t0', 21.5)]}

    update_environmental_sensor_readings([obj], 'temp-1', 21.5, 't1')

    readings = obj.chain_data.env_sensor_state['temp-1']['readings']
    assert len(readings) == 1
    assert readings[0] == ('t1', 21.5)

  def test_invalid_value_returns_false(self):
    obj = _obj()

    result = update_environmental_sensor_readings([obj], 'temp-1', 'not-a-number', 't0')

    assert result is False
    assert 'temp-1' not in obj.chain_data.env_sensor_state

  def test_multiple_objects_all_updated(self):
    objs = [_obj('a'), _obj('b')]

    update_environmental_sensor_readings(objs, 'temp-1', 30.0, 't0')

    for obj in objs:
      assert 'temp-1' in obj.chain_data.env_sensor_state


class TestUpdateAttributeSensorEvents:
  def test_first_event_initialises_list(self):
    obj = _obj()

    update_attribute_sensor_events([obj], 'badge-1', 'authorized', '2026-01-01T00:00:00Z')

    assert obj.chain_data.attr_sensor_events['badge-1'] == [('2026-01-01T00:00:00Z', 'authorized')]

  def test_changed_value_appends(self):
    obj = _obj()
    obj.chain_data.attr_sensor_events['badge-1'] = [('t0', 'authorized')]

    update_attribute_sensor_events([obj], 'badge-1', 'denied', 't1')

    assert obj.chain_data.attr_sensor_events['badge-1'] == [('t0', 'authorized'), ('t1', 'denied')]

  def test_unchanged_value_updates_timestamp_only(self):
    obj = _obj()
    obj.chain_data.attr_sensor_events['badge-1'] = [('t0', 'authorized')]

    update_attribute_sensor_events([obj], 'badge-1', 'authorized', 't1')

    events = obj.chain_data.attr_sensor_events['badge-1']
    assert len(events) == 1
    assert events[0] == ('t1', 'authorized')

  def test_non_string_value_coerced_to_string(self):
    obj = _obj()

    update_attribute_sensor_events([obj], 'badge-1', 42, 't0')

    assert obj.chain_data.attr_sensor_events['badge-1'] == [('t0', '42')]

  def test_multiple_objects_all_updated(self):
    objs = [_obj('a'), _obj('b')]

    update_attribute_sensor_events(objs, 'badge-1', 'authorized', 't0')

    for obj in objs:
      assert 'badge-1' in obj.chain_data.attr_sensor_events
