# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for controller.analytics.shadow — compare_states and compare_events."""

from types import SimpleNamespace

import pytest

from controller.analytics.shadow import compare_events, compare_states
from controller.analytics.state import (
  AnalyticsStateStore,
  RegionAnalyticsState,
  TripwireAnalyticsState,
)
from controller.moving_object import ChainData
from controller.analytics.tripwire import TripwireEvent
from controller.analytics.analytics_models import AnalyticsObject
from scene_common.geometry import Point


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ao(gid, *, loc=(1.0, 0.0, 0.0)):
  """Create a minimal AnalyticsObject for use in state comparisons."""
  return AnalyticsObject(
    gid=gid,
    category='person',
    frameCount=5,
    sceneLoc=Point(*loc),
    chain_data=ChainData(regions={}, publishedLocations=[], persist={}),
  )


def _make_region_state(
  objects=None,
  entered=None,
  exited=None,
):
  """Build a RegionAnalyticsState from convenience inputs.

  All values are keyed by 'person' detection type.
  objects:  list of AnalyticsObject
  entered:  list of AnalyticsObject
  exited:   list of (AnalyticsObject, dwell_seconds)
  """
  rs = RegionAnalyticsState()
  if objects:
    rs.objects['person'] = list(objects)
  if entered:
    rs.entered['person'] = list(entered)
  if exited:
    rs.exited['person'] = list(exited)
  return rs


def _tripwire_event(gid, direction='AB'):
  te = TripwireEvent(_ao(gid), direction)
  return te


def _make_tripwire_state(crossings=None):
  """Build a TripwireAnalyticsState from a list of TripwireEvent objects."""
  ts = TripwireAnalyticsState()
  if crossings:
    ts.objects['person'] = list(crossings)
  return ts


def _event_data(
  counts=None,
  entered=None,
  exited=None,
):
  """Build a minimal event_data dict for compare_events."""
  return {
    'counts': counts or {},
    'entered': [{'id': gid} for gid in (entered or [])],
    'exited': [
      {'object': {'id': gid}, 'dwell': dwell}
      for gid, dwell in (exited or [])
    ],
  }


# ---------------------------------------------------------------------------
# compare_states — region tests
# ---------------------------------------------------------------------------

class TestCompareStatesRegions:
  def test_empty_stores_no_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    assert compare_states(primary, shadow, 'scene-1', 'person') == 0

  def test_matching_objects_no_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    for store in (primary, shadow):
      store._regions['r1'] = _make_region_state(objects=[_ao('obj-1'), _ao('obj-2')])
    assert compare_states(primary, shadow, 'scene-1', 'person') == 0

  def test_different_current_objects_not_divergence(self):
    # rstate.objects is a debounce-gated snapshot updated only when an event fires.
    # The two paths may differ during the debounce window (≤0.5s) after one path
    # fires first — this is timing noise, not a logic error.  Genuine divergences
    # are caught via entered/exited comparisons and compare_events instead.
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    primary._regions['r1'] = _make_region_state(objects=[_ao('obj-1')])
    shadow._regions['r1'] = _make_region_state(objects=[_ao('obj-2')])
    assert compare_states(primary, shadow, 'scene-1', 'person') == 0

  def test_different_entered_is_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    primary._regions['r1'] = _make_region_state(entered=[_ao('obj-1')])
    shadow._regions['r1'] = _make_region_state(entered=[_ao('obj-2')])
    assert compare_states(primary, shadow, 'scene-1', 'person') >= 1

  def test_different_exited_is_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    primary._regions['r1'] = _make_region_state(exited=[(_ao('obj-1'), 5.0)])
    shadow._regions['r1'] = _make_region_state(exited=[(_ao('obj-2'), 5.0)])
    assert compare_states(primary, shadow, 'scene-1', 'person') >= 1

  def test_region_objects_in_primary_only_not_divergence(self):
    # rstate.objects differences are not compared — see comment in
    # test_different_current_objects_not_divergence above.
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    primary._regions['r1'] = _make_region_state(objects=[_ao('obj-1')])
    # shadow has no 'r1' at all — objects-only difference is not flagged
    assert compare_states(primary, shadow, 'scene-1', 'person') == 0


# ---------------------------------------------------------------------------
# compare_states — tripwire tests
# ---------------------------------------------------------------------------

class TestCompareStatesTripwires:
  def test_matching_crossings_no_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    for store in (primary, shadow):
      store._tripwires['tw1'] = _make_tripwire_state(
        crossings=[_tripwire_event('obj-1', 'AB')]
      )
    assert compare_states(primary, shadow, 'scene-1', 'person') == 0

  def test_different_crossings_is_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    primary._tripwires['tw1'] = _make_tripwire_state(
      crossings=[_tripwire_event('obj-1', 'AB')]
    )
    shadow._tripwires['tw1'] = _make_tripwire_state(
      crossings=[_tripwire_event('obj-2', 'AB')]
    )
    assert compare_states(primary, shadow, 'scene-1', 'person') >= 1

  def test_direction_mismatch_is_divergence(self):
    primary = AnalyticsStateStore()
    shadow = AnalyticsStateStore()
    primary._tripwires['tw1'] = _make_tripwire_state(
      crossings=[_tripwire_event('obj-1', 'AB')]
    )
    shadow._tripwires['tw1'] = _make_tripwire_state(
      crossings=[_tripwire_event('obj-1', 'BA')]
    )
    assert compare_states(primary, shadow, 'scene-1', 'person') >= 1


# ---------------------------------------------------------------------------
# compare_events
# ---------------------------------------------------------------------------

class TestCompareEvents:
  def test_empty_events_no_divergence(self):
    assert compare_events({}, {}, 'scene-1') == 0

  def test_matching_events_no_divergence(self):
    key = ('r1', 'objects')
    data = _event_data(
      counts={'person': 2},
      entered=['obj-1'],
      exited=[('obj-2', 10.0)],
    )
    assert compare_events({key: data}, {key: data}, 'scene-1') == 0

  def test_count_mismatch_is_divergence(self):
    key = ('r1', 'objects')
    p = _event_data(counts={'person': 2})
    s = _event_data(counts={'person': 3})
    assert compare_events({key: p}, {key: s}, 'scene-1') >= 1

  def test_entered_mismatch_is_divergence(self):
    key = ('r1', 'objects')
    p = _event_data(entered=['obj-1'])
    s = _event_data(entered=['obj-2'])
    assert compare_events({key: p}, {key: s}, 'scene-1') >= 1

  def test_exited_id_mismatch_is_divergence(self):
    key = ('r1', 'objects')
    p = _event_data(exited=[('obj-1', 5.0)])
    s = _event_data(exited=[('obj-2', 5.0)])
    assert compare_events({key: p}, {key: s}, 'scene-1') >= 1

  def test_dwell_within_tolerance_no_divergence(self):
    key = ('r1', 'objects')
    p = _event_data(exited=[('obj-1', 10.0)])
    s = _event_data(exited=[('obj-1', 10.5)])  # 0.5 s < 1.0 s tolerance
    assert compare_events({key: p}, {key: s}, 'scene-1') == 0

  def test_dwell_outside_tolerance_is_divergence(self):
    key = ('r1', 'objects')
    p = _event_data(exited=[('obj-1', 10.0)])
    s = _event_data(exited=[('obj-1', 12.0)])  # 2.0 s > 1.0 s tolerance
    assert compare_events({key: p}, {key: s}, 'scene-1') >= 1

  def test_event_in_shadow_only_is_divergence(self):
    key = ('r1', 'objects')
    s = _event_data()
    assert compare_events({}, {key: s}, 'scene-1') >= 1

  def test_event_in_primary_only_is_divergence(self):
    key = ('r1', 'objects')
    p = _event_data()
    assert compare_events({key: p}, {}, 'scene-1') >= 1
