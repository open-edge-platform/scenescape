# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from analytics.analytics_models import AnalyticsObject
from analytics.region import update_region_events
from analytics.state import AnalyticsStateStore, DEBOUNCE_DELAY
from scene_common.chain_data import ChainData
from scene_common.geometry import Point
from scene_common.timestamp import get_iso_time


INSIDE = Point(5.0, 5.0, 0.0)
OUTSIDE = Point(50.0, 50.0, 0.0)


def _iso(epoch):
  return get_iso_time(epoch)


def _obj(gid='obj-1', loc=INSIDE):
  return AnalyticsObject(
    gid=gid,
    category='person',
    frameCount=5,
    sceneLoc=loc,
    chain_data=ChainData(regions={}, publishedLocations=[], persist={}),
  )


class TestUpdateRegionEventsEntry:

  def test_object_entering_region_gets_entered_timestamp(self, make_region):
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    events = {}

    updated = update_region_events('person', {'roi': region}, 10.0, '2026-01-01T00:00:10Z',
                                    [obj], events, state_store)

    assert 'roi' in updated
    assert obj.chain_data.regions['roi'] == {'entered': '2026-01-01T00:00:10Z'}

  def test_first_entry_emits_objects_and_count_events(self, make_region):
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    events = {}

    update_region_events('person', {'roi': region}, 10.0, '2026-01-01T00:00:10Z',
                          [obj], events, state_store)

    assert events['objects'] == [('roi', region)]
    assert events['count'] == [('roi', region)]

  def test_object_outside_region_not_added(self, make_region):
    region = make_region()
    obj = _obj(loc=OUTSIDE)
    state_store = AnalyticsStateStore()
    events = {}

    update_region_events('person', {'roi': region}, 10.0, '2026-01-01T00:00:10Z',
                          [obj], events, state_store)

    assert obj.chain_data.regions == {}
    assert 'objects' not in events

  def test_steady_state_object_produces_no_new_event(self, make_region):
    """Once entered (and debounce satisfied), staying in the region with no
    membership change should not re-emit or re-initialise state."""
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    events1 = {}
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], events1, state_store)

    events2 = {}
    update_region_events('person', {'roi': region}, 12.0, _iso(12.0), [obj], events2, state_store)

    assert 'objects' not in events2
    assert obj.chain_data.regions['roi'] == {'entered': _iso(10.0)}


class TestUpdateRegionEventsExit:

  def test_object_exit_computes_dwell_and_removes_region_state(self, make_region):
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    events = {}
    update_region_events('person', {'roi': region}, 15.0, _iso(15.0), [], events, state_store)

    rstate = state_store.region('roi')
    exited = rstate.exited['person']
    assert len(exited) == 1
    exited_obj, dwell = exited[0]
    assert exited_obj is obj
    assert dwell == pytest.approx(5.0, abs=1.0)
    assert 'roi' not in obj.chain_data.regions

  def test_exit_only_removed_after_event_emission(self, make_region):
    """chain_data.regions entry must still be present while computing dwell."""
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)
    # Force debounce so the exit event is suppressed this frame.
    state_store.region('roi').when = 14.99

    events = {}
    update_region_events('person', {'roi': region}, 15.0, _iso(15.0), [], events, state_store)

    # Event suppressed by debounce -> state (and chain_data.regions) untouched.
    assert 'objects' not in events
    assert 'roi' in obj.chain_data.regions


class TestUpdateRegionEventsDebounce:

  def test_no_event_within_debounce_window(self, make_region):
    """Entry initialisation still happens, but no objects/count event fires."""
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    state_store.region('roi').when = 9.7
    events = {}

    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], events, state_store)

    assert 'objects' not in events
    assert 'roi' in obj.chain_data.regions

  def test_event_emitted_once_debounce_elapsed(self, make_region):
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()
    state_store.region('roi').when = 9.0
    now = 10.0 + DEBOUNCE_DELAY + 0.01
    events = {}

    update_region_events(
      'person', {'roi': region}, now, _iso(now), [obj], events, state_store,
    )

    assert 'objects' in events


class TestUpdateRegionEventsCountEvent:

  def test_count_event_only_when_membership_size_changes(self, make_region):
    region = make_region()
    obj_a = _obj('a')
    obj_b = _obj('b')
    state_store = AnalyticsStateStore()
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj_a], {}, state_store)

    # Replace obj_a with obj_b -- same count (1 -> 1), no count event, but
    # membership change (obj_a leaves, obj_b joins) still triggers an object event.
    events = {}
    update_region_events('person', {'roi': region}, 12.0, _iso(12.0), [obj_b], events, state_store)

    assert 'objects' in events
    assert 'count' not in events


class TestUpdateRegionEventsSingletonSensors:

  def test_environmental_sensor_seeds_reading_from_region_value(self, make_region):
    region = make_region(singleton_type='environmental')
    region.value = 21.5
    region.lastWhen = 5.0
    obj = _obj()
    state_store = AnalyticsStateStore()

    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    assert obj.chain_data.env_sensor_state['roi']['readings'] == [(_iso(region.lastWhen), 21.5)]

  def test_environmental_sensor_defaults_to_empty_readings_without_value(self, make_region):
    region = make_region(singleton_type='environmental')
    obj = _obj()
    state_store = AnalyticsStateStore()

    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    assert obj.chain_data.env_sensor_state['roi']['readings'] == []

  def test_attribute_sensor_initialises_empty_event_list(self, make_region):
    region = make_region(singleton_type='attribute')
    obj = _obj()
    state_store = AnalyticsStateStore()

    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    assert obj.chain_data.attr_sensor_events['roi'] == []

  def test_entry_adds_to_active_sensors_for_singleton_regions(self, make_region):
    region = make_region(singleton_type='attribute')
    obj = _obj()
    state_store = AnalyticsStateStore()

    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    assert 'roi' in obj.chain_data.active_sensors

  def test_exit_discards_active_sensor(self, make_region):
    region = make_region(singleton_type='environmental')
    obj = _obj()
    state_store = AnalyticsStateStore()
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    update_region_events('person', {'roi': region}, 15.0, _iso(15.0), [], {}, state_store)

    assert 'roi' not in obj.chain_data.active_sensors

  def test_exit_preserves_environmental_state_until_serialisation(self, make_region):
    """env_sensor_state is intentionally NOT cleared by update_region_events.
    It must survive until event_publisher._clear_sensor_values_on_exit has
    serialised the exited object, after which it pops the key.  Clearing it
    here would cause exit-event payloads to carry empty sensor readings."""
    region = make_region(singleton_type='environmental')
    obj = _obj()
    state_store = AnalyticsStateStore()
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)

    update_region_events('person', {'roi': region}, 15.0, _iso(15.0), [], {}, state_store)

    assert 'roi' in obj.chain_data.env_sensor_state

  def test_exit_preserves_attribute_sensor_event_history(self, make_region):
    region = make_region(singleton_type='attribute')
    obj = _obj()
    state_store = AnalyticsStateStore()
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)
    obj.chain_data.attr_sensor_events['roi'].append(('t1', 'authorized'))

    update_region_events('person', {'roi': region}, 15.0, _iso(15.0), [], {}, state_store)

    assert obj.chain_data.attr_sensor_events['roi'] == [('t1', 'authorized')]


class TestUpdateRegionEventsIntersectionFallback:

  def test_is_intersecting_fn_includes_objects_outside_point_containment(self, make_region):
    region = make_region()
    obj = _obj(loc=OUTSIDE)
    state_store = AnalyticsStateStore()
    always_intersects = MagicMock(return_value=True)

    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store,
                          is_intersecting_fn=always_intersects)

    assert 'roi' in obj.chain_data.regions

  def test_is_intersecting_fn_not_called_when_none(self, make_region):
    region = make_region()
    obj = _obj()
    state_store = AnalyticsStateStore()

    # Should not raise even though no is_intersecting_fn is supplied.
    update_region_events('person', {'roi': region}, 10.0, _iso(10.0), [obj], {}, state_store)


class TestUpdateRegionEventsMultipleRegions:

  def test_regions_tracked_independently(self, make_region):
    roi_a = make_region('roi-a', 'A')
    roi_b = make_region('roi-b', 'B', points=[[100.0, 100.0], [110.0, 100.0], [110.0, 110.0], [100.0, 110.0]])
    obj = _obj()
    state_store = AnalyticsStateStore()
    events = {}

    update_region_events('person', {'roi-a': roi_a, 'roi-b': roi_b}, 10.0, _iso(10.0), [obj], events, state_store)

    assert 'roi-a' in obj.chain_data.regions
    assert 'roi-b' not in obj.chain_data.regions

  def test_empty_regions_dict_returns_empty_set(self):
    state_store = AnalyticsStateStore()
    updated = update_region_events('person', {}, 10.0, _iso(10.0), [_obj()], {}, state_store)

    assert updated == set()
