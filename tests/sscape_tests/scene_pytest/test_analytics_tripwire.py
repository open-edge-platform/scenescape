# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from controller.analytics.analytics_models import AnalyticsObject
from controller.analytics.tripwire import (
  DEBOUNCE_DELAY,
  TripwireEvent,
  update_tripwire_events,
)
from controller.moving_object import ChainData
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


def _tripwire(when=0.0):
  return SimpleNamespace(
    objects={},
    when=when,
    lineCrosses=lambda line: 0,
  )


class TestUpdateTripwireEventsReliabilityGate:
  def test_object_below_min_frames_skipped_when_tracker_enabled(self):
    tripwire = _tripwire()
    obj = _obj(frame_count=1)
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[obj], events=events, use_tracker=True)

    assert 'objects' not in events

  def test_object_with_single_location_skipped(self):
    tripwire = _tripwire()
    obj = _obj(locations=[Point(1.0, 1.0, 0.0)])
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[obj], events=events, use_tracker=False)

    assert 'objects' not in events

  def test_all_objects_eligible_when_tracker_disabled(self):
    tripwire = _tripwire()
    # frame_count=1 would be excluded with use_tracker=True
    obj = _obj(frame_count=1)
    events = {}

    # No crossing expected — just verify no frameCount gate exception is raised
    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[obj], events=events, use_tracker=False)


class TestUpdateTripwireEventsDebounce:
  def test_no_event_emitted_within_debounce_window(self):
    tripwire = _tripwire(when=1.9)
    tripwire.objects['person'] = [SimpleNamespace()]  # previous state differs
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, use_tracker=True)

    assert 'objects' not in events

  def test_event_emitted_after_debounce_window(self):
    tripwire = _tripwire(when=0.0)
    tripwire.objects['person'] = [SimpleNamespace()]  # previous: 1 object
    events = {}

    # cur_objects is empty → crossed_objects will be [] → count differs
    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, use_tracker=True)

    assert 'objects' in events
    assert events['objects'][0][0] == 'tw'

  def test_no_event_when_count_unchanged(self):
    tripwire = _tripwire(when=0.0)
    tripwire.objects['person'] = []  # already empty
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, use_tracker=True)

    assert 'objects' not in events


class TestTripwireEvent:
  def test_stores_object_and_direction(self):
    obj = _obj()
    ev = TripwireEvent(obj, 'forward')

    assert ev.object is obj
    assert ev.direction == 'forward'


class TestUpdateTripwireEventsEmptyInputs:
  def test_empty_tripwires_produces_no_events(self):
    events = {}
    update_tripwire_events('person', {}, now=1.0, cur_objects=[_obj()], events=events, use_tracker=True)
    assert events == {}

  def test_empty_objects_with_previous_state_emits_exit_event(self):
    tripwire = _tripwire(when=0.0)
    tripwire.objects['person'] = [SimpleNamespace()]
    events = {}

    update_tripwire_events('person', {'tw': tripwire}, now=2.0, cur_objects=[], events=events, use_tracker=True)

    assert 'objects' in events
