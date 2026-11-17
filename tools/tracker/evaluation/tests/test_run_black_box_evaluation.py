# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for run_black_box_evaluation config-set routing."""

import sys
from pathlib import Path

import pytest

# Add the evaluation package root to path.
sys.path.insert(0, str(Path(__file__).parent.parent))

import run_black_box_evaluation as rbbe


class TestConfigsFor:
  """Tests for dataset / association -> config-set routing."""

  def test_default_is_unity_euclidean(self):
    assert rbbe.DEFAULT_DATASET == "unity"
    assert rbbe.DEFAULT_ASSOCIATION == "euclidean"
    assert rbbe.configs_for() == rbbe.configs_for("unity", association="euclidean")

  @pytest.mark.parametrize("dataset,folder", [
    ("unity", "black_box_unity"),
    ("wildtrack", "black_box_wildtrack"),
  ])
  def test_euclidean_keys_resolve_to_existing_files(self, dataset, folder):
    paths = rbbe.configs_for(dataset, association="euclidean")
    assert [p.name for p in paths] == rbbe._CONFIG_FILES
    assert all(p.parent.name == folder for p in paths)
    assert all(p.exists() for p in paths)

  @pytest.mark.parametrize("dataset,folder", [
    ("unity", "black_box_unity"),
    ("wildtrack", "black_box_wildtrack"),
  ])
  def test_mahalanobis_keys_resolve_to_existing_files(self, dataset, folder):
    paths = rbbe.configs_for(dataset, association="mahalanobis")
    expected = rbbe._config_file_names("mahalanobis")
    assert [p.name for p in paths] == expected
    assert all(p.parent.name == folder for p in paths)
    assert all(p.exists() for p in paths)
    assert all("_mahalanobis" in p.name for p in paths)

  def test_both_returns_euclidean_then_mahalanobis(self):
    paths = rbbe.configs_for("unity", association="both")
    assert [p.name for p in paths] == (
      rbbe._config_file_names("euclidean") + rbbe._config_file_names("mahalanobis"))
    assert all(p.exists() for p in paths)

  def test_invalid_dataset_raises_valueerror(self):
    with pytest.raises(ValueError) as exc:
      rbbe.configs_for("bogus")
    msg = str(exc.value)
    assert "bogus" in msg
    assert "unity" in msg and "wildtrack" in msg

  def test_invalid_association_raises_valueerror(self):
    with pytest.raises(ValueError) as exc:
      rbbe.configs_for("unity", association="cosine")
    msg = str(exc.value)
    assert "cosine" in msg
    assert "euclidean" in msg and "mahalanobis" in msg
