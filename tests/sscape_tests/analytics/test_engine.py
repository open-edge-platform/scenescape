# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest

from analytics.analytics_models import AnalyticsObject
from analytics.engine import MIN_FRAMES_FOR_RELIABLE_TRACK, process_frame
from analytics.state import AnalyticsStateStore
from scene_common.chain_data import ChainData
from scene_common.geometry import Point


def _obj(gid='obj-1', num_prior_locations=0):
  cd = ChainData(
    regions={},
    publishedLocations=[Point(float(i), 0.0, 0.0) for i in range(num_prior_locations)],
    persist={},
  )
  return AnalyticsObject(
    gid=gid,
    category='person',
    frameCount=1,
    sceneLoc=Point(9.0, 9.0, 0.0),
    chain_data=cd,
  )


class TestProcessFrameReliabilityGate:

  @patch('analytics.engine.update_tripwire_events')
  @patch('analytics.engine.update_region_events')
  def test_object_below_threshold_excluded_from_region_and_tripwire_calls(
    self, mock_region_events, mock_tripwire_events,
  ):
    obj = _obj(num_prior_locations=0)  # publishedLocations will have exactly 1 after insert
    events = {}
    state_store = AnalyticsStateStore()

    process_frame('person', 10.0, [obj], {}, {}, {}, events, state_store)

    region_call_objects = mock_region_events.call_args_list[0].args[4]
    assert region_call_objects == []

  @patch('analytics.engine.update_tripwire_events')
  @patch('analytics.engine.update_region_events')
  def test_object_above_threshold_included(self, mock_region_events, mock_tripwire_events):
    obj = _obj(num_prior_locations=MIN_FRAMES_FOR_RELIABLE_TRACK + 1)
    events = {}
    state_store = AnalyticsStateStore()

    process_frame('person', 10.0, [obj], {}, {}, {}, events, state_store)

    region_call_objects = mock_region_events.call_args_list[0].args[4]
    assert region_call_objects == [obj]

  @patch('analytics.engine.update_tripwire_events')
  @patch('analytics.engine.update_region_events')
  def test_scene_loc_inserted_for_all_objects_regardless_of_reliability(
    self, mock_region_events, mock_tripwire_events,
  ):
    obj = _obj(num_prior_locations=0)
    original_loc = obj.sceneLoc

    process_frame('person', 10.0, [obj], {}, {}, {}, {}, AnalyticsStateStore())

    assert obj.chain_data.publishedLocations[0] is original_loc


class TestProcessFrameDispatch:

  @patch('analytics.engine.update_tripwire_events')
  @patch('analytics.engine.update_region_events')
  def test_update_region_events_called_for_regions_and_sensors(
    self, mock_region_events, mock_tripwire_events,
  ):
    regions = {'r1': object()}
    sensors = {'s1': object()}
    tripwires = {'t1': object()}
    events = {}
    state_store = AnalyticsStateStore()
    obj = _obj(num_prior_locations=MIN_FRAMES_FOR_RELIABLE_TRACK + 1)

    process_frame('person', 10.0, [obj], regions, sensors, tripwires, events, state_store)

    assert mock_region_events.call_count == 2
    first_call, second_call = mock_region_events.call_args_list
    assert first_call.args[1] is regions
    assert second_call.args[1] is sensors
    mock_tripwire_events.assert_called_once()
    assert mock_tripwire_events.call_args.args[1] is tripwires

  @patch('analytics.engine.update_tripwire_events')
  @patch('analytics.engine.update_region_events')
  def test_is_intersecting_fn_forwarded_to_region_events(
    self, mock_region_events, mock_tripwire_events,
  ):
    fn = MagicMock()
    obj = _obj(num_prior_locations=MIN_FRAMES_FOR_RELIABLE_TRACK + 1)

    process_frame('person', 10.0, [obj], {}, {}, {}, {}, AnalyticsStateStore(), is_intersecting_fn=fn)

    for call in mock_region_events.call_args_list:
      assert call.args[-1] is fn

  def test_empty_objects_and_registries_no_errors(self):
    process_frame('person', 10.0, [], {}, {}, {}, {}, AnalyticsStateStore())
