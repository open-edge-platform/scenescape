#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for manager.osm_query tag normalization."""

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
