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
  """Tests for dataset -> config-set routing (configs_for / --dataset)."""

  def test_default_is_unity(self):
    assert rbbe.DEFAULT_DATASET == "unity"
    assert rbbe.configs_for() == rbbe.configs_for("unity")

  @pytest.mark.parametrize("dataset,folder", [
    ("unity", "black_box_unity"),
    ("wildtrack", "black_box_wildtrack"),
  ])
  def test_valid_keys_resolve_to_existing_files(self, dataset, folder):
    paths = rbbe.configs_for(dataset)
    assert [p.name for p in paths] == rbbe._CONFIG_FILES
    assert all(p.parent.name == folder for p in paths)
    assert all(p.exists() for p in paths)

  def test_invalid_key_raises_valueerror(self):
    with pytest.raises(ValueError) as exc:
      rbbe.configs_for("bogus")
    msg = str(exc.value)
    assert "bogus" in msg
    assert "unity" in msg and "wildtrack" in msg
