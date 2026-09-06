# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from analytics.state import (
  AnalyticsStateStore,
  RegionAnalyticsState,
  TripwireAnalyticsState,
)


class TestAnalyticsStateStoreRegion:

  def test_region_creates_state_lazily(self):
    store = AnalyticsStateStore()

    rstate = store.region('roi-1')

    assert isinstance(rstate, RegionAnalyticsState)

  def test_region_returns_same_instance_on_repeat_access(self):
    store = AnalyticsStateStore()

    first = store.region('roi-1')
    second = store.region('roi-1')

    assert first is second

  def test_different_keys_get_independent_state(self):
    store = AnalyticsStateStore()

    a = store.region('roi-a')
    b = store.region('roi-b')

    assert a is not b
    a.objects['person'] = ['x']
    assert b.objects == {}

  def test_remove_region_drops_existing_key(self):
    store = AnalyticsStateStore()
    store.region('roi-1')

    store.remove_region('roi-1')

    # A fresh instance is created on next access since the old one was dropped.
    new_instance = store.region('roi-1')
    assert new_instance.objects == {}

  def test_remove_region_missing_key_is_noop(self):
    store = AnalyticsStateStore()

    store.remove_region('does-not-exist')  # must not raise


class TestAnalyticsStateStoreTripwire:

  def test_tripwire_creates_state_lazily(self):
    store = AnalyticsStateStore()

    tstate = store.tripwire('tw-1')

    assert isinstance(tstate, TripwireAnalyticsState)

  def test_tripwire_returns_same_instance_on_repeat_access(self):
    store = AnalyticsStateStore()

    first = store.tripwire('tw-1')
    second = store.tripwire('tw-1')

    assert first is second

  def test_remove_tripwire_drops_existing_key(self):
    store = AnalyticsStateStore()
    tstate = store.tripwire('tw-1')
    tstate.objects['person'] = ['x']

    store.remove_tripwire('tw-1')

    new_instance = store.tripwire('tw-1')
    assert new_instance.objects == {}

  def test_remove_tripwire_missing_key_is_noop(self):
    store = AnalyticsStateStore()

    store.remove_tripwire('does-not-exist')  # must not raise


class TestRegionAnalyticsStateClearFrameState:

  def test_clear_frame_state_resets_entered_and_exited(self):
    rstate = RegionAnalyticsState()
    rstate.entered['person'] = ['a']
    rstate.exited['person'] = [('a', 1.0)]

    rstate.clear_frame_state()

    assert rstate.entered == {}
    assert rstate.exited == {}

  def test_clear_frame_state_preserves_objects_and_when(self):
    rstate = RegionAnalyticsState()
    rstate.objects['person'] = ['a']
    rstate.when = 42.0

    rstate.clear_frame_state()

    assert rstate.objects == {'person': ['a']}
    assert rstate.when == 42.0


class TestDataclassDefaultIsolation:

  def test_region_analytics_state_instances_do_not_share_mutable_defaults(self):
    a = RegionAnalyticsState()
    b = RegionAnalyticsState()

    a.objects['person'] = ['x']
    a.entered['person'] = ['x']
    a.exited['person'] = [('x', 1.0)]

    assert b.objects == {}
    assert b.entered == {}
    assert b.exited == {}

  def test_tripwire_analytics_state_instances_do_not_share_mutable_defaults(self):
    a = TripwireAnalyticsState()
    b = TripwireAnalyticsState()

    a.objects['person'] = ['x']

    assert b.objects == {}

  def test_default_when_is_zero(self):
    assert RegionAnalyticsState().when == 0.0
    assert TripwireAnalyticsState().when == 0.0
