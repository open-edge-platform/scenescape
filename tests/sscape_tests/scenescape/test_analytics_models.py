# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from controller.analytics.analytics_models import AnalyticsEvent, AnalyticsFrame, AnalyticsObject
from controller.moving_object import ChainData
from scene_common.geometry import Point


def _chain_data():
  return ChainData(regions={}, publishedLocations=[], persist={})


def _analytics_object(**kwargs):
  defaults = dict(
    gid='obj-1',
    category='person',
    frameCount=5,
    sceneLoc=Point(1.0, 2.0, 0.0),
    chain_data=_chain_data(),
  )
  defaults.update(kwargs)
  return AnalyticsObject(**defaults)


class TestAnalyticsObject:
  def test_construction_sets_required_fields(self):
    loc = Point(1.0, 2.0, 0.0)
    cd = _chain_data()

    obj = AnalyticsObject(
      gid='g-1',
      category='vehicle',
      frameCount=3,
      sceneLoc=loc,
      chain_data=cd,
    )

    assert obj.gid == 'g-1'
    assert obj.category == 'vehicle'
    assert obj.frameCount == 3
    assert obj.sceneLoc is loc
    assert obj.chain_data is cd

  def test_optional_fields_default_to_none(self):
    obj = _analytics_object()

    assert obj.mesh is None
    assert obj.bbMeters is None
    assert obj.size is None

  def test_optional_fields_accept_arbitrary_values(self):
    sentinel = object()

    obj = _analytics_object(mesh=sentinel, bbMeters={'width': 1.0}, size=[1.0, 0.5, 1.8])

    assert obj.mesh is sentinel
    assert obj.bbMeters == {'width': 1.0}
    assert obj.size == [1.0, 0.5, 1.8]

  def test_chain_data_is_shared_reference(self):
    cd = _chain_data()
    obj = _analytics_object(chain_data=cd)

    obj.chain_data.regions['zone-a'] = {'entered': '2026-01-01T00:00:00Z'}

    assert 'zone-a' in cd.regions

  def test_missing_required_field_raises_type_error(self):
    with pytest.raises(TypeError):
      AnalyticsObject(
        gid='g-1',
        category='person',
        frameCount=1,
        # sceneLoc omitted
        chain_data=_chain_data(),
      )


class TestAnalyticsFrame:
  def test_construction_sets_fields(self):
    obj = _analytics_object()

    frame = AnalyticsFrame(
      detection_type='person',
      timestamp=1234567890.0,
      objects=[obj],
    )

    assert frame.detection_type == 'person'
    assert frame.timestamp == 1234567890.0
    assert frame.objects == [obj]

  def test_objects_defaults_to_empty_list(self):
    frame = AnalyticsFrame(detection_type='vehicle', timestamp=0.0)

    assert frame.objects == []

  def test_objects_lists_are_independent_between_instances(self):
    frame_a = AnalyticsFrame(detection_type='person', timestamp=0.0)
    frame_b = AnalyticsFrame(detection_type='person', timestamp=0.0)

    frame_a.objects.append(_analytics_object())

    assert frame_b.objects == []

  def test_missing_required_field_raises_type_error(self):
    with pytest.raises(TypeError):
      AnalyticsFrame(detection_type='person')


class TestAnalyticsEvent:
  def test_construction_sets_all_fields(self):
    event = AnalyticsEvent(
      event_type='region_enter',
      key='zone-a',
      timestamp=1234567890.0,
    )

    assert event.event_type == 'region_enter'
    assert event.key == 'zone-a'
    assert event.timestamp == 1234567890.0

  def test_missing_required_field_raises_type_error(self):
    with pytest.raises(TypeError):
      AnalyticsEvent(event_type='tripwire_cross', key='wire-1')
