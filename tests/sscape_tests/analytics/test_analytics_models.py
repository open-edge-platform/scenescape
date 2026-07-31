# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from analytics.analytics_models import (
  AnalyticsObject,
  moving_object_to_analytics_object,
)
from scene_common.chain_data import ChainData
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
    assert obj.velocity is None
    assert obj.info is None
    assert obj.rotation is None
    assert obj.metadata is None
    assert obj.reid is None
    assert obj.visibility is None

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


class TestMovingObjectToAnalyticsObject:
  def _source_object(self, **kwargs):
    defaults = dict(
      gid='src-1',
      category='person',
      frameCount=4,
      sceneLoc=Point(3.0, 4.0, 0.0),
      chain_data=ChainData(regions={}, publishedLocations=[], persist={}),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)

  def test_maps_required_fields(self):
    src = self._source_object()

    ao = moving_object_to_analytics_object(src)

    assert ao.gid == 'src-1'
    assert ao.category == 'person'
    assert ao.frameCount == 4
    assert ao.sceneLoc is src.sceneLoc

  def test_shares_chain_data_reference(self):
    src = self._source_object()

    ao = moving_object_to_analytics_object(src)
    ao.chain_data.regions['z'] = {'entered': '2026-01-01T00:00:00Z'}

    assert 'z' in src.chain_data.regions

  def test_optional_fields_default_to_none_when_absent(self):
    src = self._source_object()

    ao = moving_object_to_analytics_object(src)

    assert ao.mesh is None
    assert ao.bbMeters is None
    assert ao.size is None
    assert ao.velocity is None
    assert ao.info is None
    assert ao.rotation is None
    assert ao.metadata is None
    assert ao.reid is None
    assert ao.visibility is None

  def test_publishing_fields_carried_through_when_present(self):
    src = self._source_object(
      velocity=Point(1.0, 0.0, 0.0),
      info={'category': 'person', 'confidence': 0.9},
      rotation=[0.0, 0.0, 0.0, 1.0],
      metadata={'age': 'adult'},
      reid={'embedding_vector': [0.1, 0.2]},
      visibility=['cam1', 'cam2'],
    )

    ao = moving_object_to_analytics_object(src)

    assert ao.velocity is src.velocity
    assert ao.info == {'category': 'person', 'confidence': 0.9}
    assert ao.rotation == [0.0, 0.0, 0.0, 1.0]
    assert ao.metadata == {'age': 'adult'}
    assert ao.reid == {'embedding_vector': [0.1, 0.2]}
    assert ao.visibility == ['cam1', 'cam2']

  def test_optional_fields_carried_through_when_present(self):
    sentinel = object()
    src = self._source_object(mesh=sentinel, bbMeters={'width': 0.5}, size=[0.5, 0.5, 1.8])

    ao = moving_object_to_analytics_object(src)

    assert ao.mesh is sentinel
    assert ao.bbMeters == {'width': 0.5}
    assert ao.size == [0.5, 0.5, 1.8]

  def test_returns_analytics_object_instance(self):
    ao = moving_object_to_analytics_object(self._source_object())

    assert isinstance(ao, AnalyticsObject)
