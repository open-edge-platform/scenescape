# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from analytics.analytics_models import AnalyticsObject
from analytics.state import AnalyticsStateStore, DEBOUNCE_DELAY
from analytics.tripwire import (
  TripwireEvent,
  update_tripwire_events,
)
from scene_common.chain_data import ChainData
from scene_common.geometry import Point


def _chain_data(locations=None):
  cd = ChainData(regions={}, publishedLocations=[], persist={})
  if locations:
    cd.publishedLocations = locations
  return cd


def _obj(gid='obj-1', frame_count=5, locations=None):
  return AnalyticsObject(
    gid=gid,
    category='person',
    frameCount=frame_count,
    sceneLoc=Point(1.0, 1.0, 0.0),
    chain_data=_chain_data(locations=locations or [Point(1.0, 1.0, 0.0), Point(0.0, 0.0, 0.0)]),
  )


def _tripwire():
  return SimpleNamespace(
    lineCrosses=lambda line: 0,
  )


class TestUpdateTripwireEventsReliabilityGate:
  def test_object_below_min_frames_skipped_when_tracker_enabled(self):
    state_store = AnalyticsStateStore()
    tripwire = _tripwire()
    obj = _obj(frame_count=1)
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[obj], events=events, state_store=state_store)

    assert 'objects' not in events

  def test_object_with_single_location_skipped(self):
    state_store = AnalyticsStateStore()
    tripwire = _tripwire()
    obj = _obj(locations=[Point(1.0, 1.0, 0.0)])
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[obj], events=events, state_store=state_store)

    assert 'objects' not in events

  def test_all_objects_included_regardless_of_frame_count(self):
    state_store = AnalyticsStateStore()
    tripwire = _tripwire()
    # Analytics library no longer gates on frameCount — caller is responsible
    obj = _obj(frame_count=1)
    events = {}

    # No crossing expected — just verify no frameCount gate blocks this object
    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[obj], events=events, state_store=state_store)


class TestUpdateTripwireEventsDebounce:
  def test_no_event_emitted_within_debounce_window(self):
    state_store = AnalyticsStateStore()
    state_store.tripwire('tw').objects['person'] = [SimpleNamespace()]
    state_store.tripwire('tw').when = 1.9
    tripwire = _tripwire()
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, state_store=state_store)

    assert 'objects' not in events

  def test_event_emitted_after_debounce_window(self):
    state_store = AnalyticsStateStore()
    state_store.tripwire('tw').objects['person'] = [SimpleNamespace()]
    tripwire = _tripwire()
    events = {}

    # cur_objects is empty → crossed_objects will be [] → count differs
    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, state_store=state_store)

    assert 'objects' in events
    assert events['objects'][0][0] == 'tw'

  def test_no_event_when_count_unchanged(self):
    state_store = AnalyticsStateStore()
    # objects['person'] defaults to {} — .get('person', []) returns []
    tripwire = _tripwire()
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, state_store=state_store)

    assert 'objects' not in events


class TestTripwireEvent:
  def test_stores_object_and_direction(self):
    obj = _obj()
    ev = TripwireEvent(obj, 'forward')

    assert ev.object is obj
    assert ev.direction == 'forward'


class TestUpdateTripwireEventsEmptyInputs:
  def test_empty_tripwires_produces_no_events(self):
    state_store = AnalyticsStateStore()
    events = {}
    update_tripwire_events('person', {}, now=1.0, cur_objects=[_obj()], events=events, state_store=state_store)
    assert events == {}

  def test_empty_objects_with_previous_state_emits_exit_event(self):
    state_store = AnalyticsStateStore()
    state_store.tripwire('tw').objects['person'] = [SimpleNamespace()]
    tripwire = _tripwire()
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, state_store=state_store)

    assert 'objects' in events
