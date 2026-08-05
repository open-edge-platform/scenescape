# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for tests/sscape_tests/analytics unit tests."""

import pytest

from analytics.analytics_models import AnalyticsObject
from scene_common.chain_data import ChainData
from scene_common.geometry import Point, Region, Tripwire


@pytest.fixture
def make_chain_data():
  """Factory for a fresh ChainData instance."""
  def _make(regions=None, publishedLocations=None, persist=None, **kwargs):
    return ChainData(
      regions=regions if regions is not None else {},
      publishedLocations=publishedLocations if publishedLocations is not None else [],
      persist=persist if persist is not None else {},
      **kwargs,
    )
  return _make


@pytest.fixture
def make_analytics_object(make_chain_data):
  """Factory for an AnalyticsObject with sensible defaults."""
  def _make(gid='obj-1', category='person', frameCount=5,
             sceneLoc=None, chain_data=None, **kwargs):
    return AnalyticsObject(
      gid=gid,
      category=category,
      frameCount=frameCount,
      sceneLoc=sceneLoc if sceneLoc is not None else Point(0.0, 0.0, 0.0),
      chain_data=chain_data if chain_data is not None else make_chain_data(),
      **kwargs,
    )
  return _make


@pytest.fixture
def make_region():
  """Factory for a scene_common.geometry.Region built from a points list."""
  def _make(uid='region-1', name='Region 1', points=None, **info_overrides):
    info = {'points': points if points is not None else [
      [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0],
    ]}
    info.update(info_overrides)
    return Region(uid, name, info)
  return _make


@pytest.fixture
def make_tripwire():
  """Factory for a scene_common.geometry.Tripwire built from a two-point line."""
  def _make(uid='tripwire-1', name='Tripwire 1', points=None, **info_overrides):
    info = {'points': points if points is not None else [[0.0, 0.0], [10.0, 0.0]]}
    info.update(info_overrides)
    return Tripwire(uid, name, info)
  return _make
