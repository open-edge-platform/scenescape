#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for manager.osm_query tag normalization and feature cap."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from manager import osm_query
from manager.osm_query import _feature_type, _normalize_tags


def test_normalize_tags_converts_list_of_pairs_to_dict():
  """Pandas/pyarrow decode the parquet 'tags' Map column as a list of [key, value] pairs."""
  raw_tags = [["highway", "secondary"], ["lanes", "3"], ["width", "10.5"]]

  result = _normalize_tags(raw_tags)

  assert result == {"highway": "secondary", "lanes": "3", "width": "10.5"}


def test_normalize_tags_passes_through_existing_dict():
  """Already-normalized dicts (e.g. from cached preview data) must be returned unchanged."""
  raw_tags = {"highway": "footway", "footway": "sidewalk"}

  assert _normalize_tags(raw_tags) is raw_tags


def test_normalize_tags_handles_none():
  """Missing tags must not raise; downstream width/type lookups expect a dict."""
  assert _normalize_tags(None) == {}


def test_normalize_tags_handles_unparseable_input():
  """Unexpected shapes (e.g. a flat list of scalars) must degrade to an empty dict, not raise."""
  assert _normalize_tags(["highway", "secondary"]) == {}


def test_feature_type_reads_highway_tag_after_normalization():
  """Regression: before normalization, list-shaped tags made every way report type 'way'."""
  tags = _normalize_tags([["highway", "residential"]])

  assert _feature_type(tags) == "residential"


@pytest.mark.parametrize("raw, expected", [
  (None, osm_query.DEFAULT_MAX_ROI_FEATURES),
  ("", osm_query.DEFAULT_MAX_ROI_FEATURES),
  ("50", 50),
  (str(osm_query.MAX_ROI_FEATURES_LIMIT), osm_query.MAX_ROI_FEATURES_LIMIT),
  ("0", osm_query.DEFAULT_MAX_ROI_FEATURES),
  ("-5", osm_query.DEFAULT_MAX_ROI_FEATURES),
  (str(osm_query.MAX_ROI_FEATURES_LIMIT + 1), osm_query.DEFAULT_MAX_ROI_FEATURES),
  ("abc", osm_query.DEFAULT_MAX_ROI_FEATURES),
])
def test_get_max_roi_features(monkeypatch, raw, expected):
  """Cap defaults to 200 and only accepts integers within [1, MAX_ROI_FEATURES_LIMIT]."""
  if raw is None:
    monkeypatch.delenv(osm_query.MAX_ROI_FEATURES_ENV_VAR, raising=False)
  else:
    monkeypatch.setenv(osm_query.MAX_ROI_FEATURES_ENV_VAR, raw)

  assert osm_query.get_max_roi_features() == expected


def test_query_over_feature_cap_fails_without_retrying(monkeypatch):
  """Exceeding the cap is deterministic, so it must not burn extra upstream requests on retries."""
  monkeypatch.setenv(osm_query.API_KEY_ENV_VAR, "test-key")
  monkeypatch.setenv(osm_query.MAX_ROI_FEATURES_ENV_VAR, "2")
  ways = pd.DataFrame({"osm_type": ["way"] * 3, "tags": [None] * 3, "geom": [None] * 3})

  with patch.object(osm_query, "_throttle"), \
       patch.object(osm_query, "_read_bounded", return_value=b""), \
       patch.object(osm_query.pd, "read_parquet", return_value=ways), \
       patch.object(osm_query.requests, "post", return_value=MagicMock()) as mock_post:
    with pytest.raises(osm_query.FeatureLimitError):
      osm_query.query_osm_ways_geometry(37.0, -122.0, 37.01, -121.99)

  mock_post.assert_called_once()
