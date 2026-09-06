#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ClusterAnalyticsConfig."""

import json
import pytest


class TestClusterAnalyticsConfig:

  def test_default_eps_loaded(self, config):
    assert config.DEFAULT_DBSCAN_EPS == 1

  def test_default_min_samples_loaded(self, config):
    assert config.DEFAULT_DBSCAN_MIN_SAMPLES == 3

  def test_person_category_eps(self, config):
    params = config.CATEGORY_DBSCAN_PARAMS.get("person")
    assert params is not None
    assert params["eps"] == 2

  def test_person_category_min_samples(self, config):
    params = config.CATEGORY_DBSCAN_PARAMS.get("person")
    assert params is not None
    assert params["min_samples"] == 2

  def test_vehicle_category_eps(self, config):
    params = config.CATEGORY_DBSCAN_PARAMS.get("vehicle")
    assert params is not None
    assert params["eps"] == 4.0

  def test_unknown_category_not_in_category_specific_params(self, config):
    # Unknown categories are absent from CATEGORY_DBSCAN_PARAMS so that
    # get_dbscan_params_for_category falls back to the global defaults.
    params = config.CATEGORY_DBSCAN_PARAMS.get("unknown_category_xyz")
    assert params is None

  def test_missing_config_file_raises(self, tmp_path):
    from cluster_analytics_context import ClusterAnalyticsConfig
    with pytest.raises(FileNotFoundError):
      ClusterAnalyticsConfig(config_path=str(tmp_path / "nonexistent.json"))

  def test_malformed_json_raises(self, tmp_path):
    from cluster_analytics_context import ClusterAnalyticsConfig
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ not valid json }")
    with pytest.raises(json.JSONDecodeError):
      ClusterAnalyticsConfig(config_path=str(bad_file))
