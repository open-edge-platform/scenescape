# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for run_black_box_evaluation config-set routing."""

import sys
from pathlib import Path

import pytest
import yaml

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


class TestObservationProcessorSwitch:
  """The service is disabled in shipped configs and enabled only on request."""

  @pytest.mark.parametrize("dataset", ["unity", "wildtrack"])
  def test_disabled_in_every_shipped_config(self, dataset):
    for path in rbbe.configs_for(dataset):
      cfg = yaml.safe_load(path.read_text())
      block = cfg["harness"]["config"]["observation_processor"]
      assert block["enabled"] is False, path.name
      assert block["image"], path.name

  def test_enable_sets_flag_and_suffixes_run_name(self):
    cfg = yaml.safe_load(rbbe.configs_for()[0].read_text())
    name = cfg["pipeline"]["run_name"]
    rbbe._enable_observation_processor(cfg)
    assert cfg["harness"]["config"]["observation_processor"]["enabled"] is True
    assert cfg["pipeline"]["run_name"] == name + rbbe.OBSERVATION_PROCESSOR_RUN_SUFFIX

  def test_enable_without_block_raises(self):
    cfg = {"pipeline": {"run_name": "X"}, "harness": {"config": {}}}
    with pytest.raises(ValueError, match="observation_processor"):
      rbbe._enable_observation_processor(cfg)

  def test_cli_flag_reaches_run_all(self, monkeypatch):
    seen = {}
    monkeypatch.setattr(rbbe, "run_all", lambda **kw: seen.update(kw) or [])
    monkeypatch.setattr(sys, "argv", ["prog", "--observation-processor"])
    assert rbbe.main() == 0
    assert seen["observation_processor"] is True

  def test_cli_default_is_disabled(self, monkeypatch):
    seen = {}
    monkeypatch.setattr(rbbe, "run_all", lambda **kw: seen.update(kw) or [])
    monkeypatch.setattr(sys, "argv", ["prog"])
    rbbe.main()
    assert seen["observation_processor"] is False
