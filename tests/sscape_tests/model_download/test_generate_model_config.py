#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for model_download/src/generate_model_config.py.

Emphasis is on validating and parsing models.json since it is the single
source of truth for both the downloader and the generated model_config.json.
"""

import copy
import json

import pytest

import generate_model_config as gmc


class TestValidateRelativeJsonPath:

  def test_valid_relative_path(self):
    assert gmc._validate_relative_json_path("a/b/c.json", "ctx") == "a/b/c.json"

  def test_rejects_non_string(self):
    with pytest.raises(ValueError, match="non-empty string"):
      gmc._validate_relative_json_path(123, "ctx")

  def test_rejects_empty_string(self):
    with pytest.raises(ValueError, match="non-empty string"):
      gmc._validate_relative_json_path("", "ctx")

  def test_rejects_absolute_path(self):
    with pytest.raises(ValueError, match="relative path"):
      gmc._validate_relative_json_path("/etc/passwd.json", "ctx")

  def test_rejects_parent_traversal(self):
    with pytest.raises(ValueError, match="relative path"):
      gmc._validate_relative_json_path("../escape.json", "ctx")

  def test_rejects_non_json_suffix(self):
    with pytest.raises(ValueError, match=r"end with \.json"):
      gmc._validate_relative_json_path("a/b/c.txt", "ctx")


class TestResolveModelProc:

  def test_returns_none_when_absent(self, minimal_model_entry):
    assert gmc._resolve_model_proc(minimal_model_entry["scenescape"], "model") is None

  def test_extracts_path_and_content(self, model_entry_with_model_proc):
    scenescape = model_entry_with_model_proc["scenescape"]
    result = gmc._resolve_model_proc(scenescape, "model")
    assert result is not None
    path, content = result
    assert path == "object_detection/person/person-detection-retail-0013.json"
    assert content["json_schema_version"] == "2.0.0"

  def test_rejects_non_dict_model_proc(self, minimal_model_entry):
    scenescape = copy.deepcopy(minimal_model_entry["scenescape"])
    scenescape["model_proc"] = "not-a-dict"
    with pytest.raises(ValueError, match="must be an object"):
      gmc._resolve_model_proc(scenescape, "model")

  def test_rejects_non_dict_content(self, minimal_model_entry):
    scenescape = copy.deepcopy(minimal_model_entry["scenescape"])
    scenescape["model_proc"] = {"path": "a.json", "content": "nope"}
    with pytest.raises(ValueError, match="content.*must be an object"):
      gmc._resolve_model_proc(scenescape, "model")


class TestGetDownloaderModels:

  def test_extracts_by_name(self, valid_models_config):
    by_name = gmc._get_downloader_models(valid_models_config)
    assert "person-detection-retail-0013" in by_name

  def test_rejects_missing_models_key(self):
    with pytest.raises(ValueError, match="non-empty JSON array"):
      gmc._get_downloader_models({})

  def test_rejects_empty_models_list(self):
    with pytest.raises(ValueError, match="non-empty JSON array"):
      gmc._get_downloader_models({"models": []})

  def test_rejects_non_dict_entry(self):
    with pytest.raises(ValueError, match=r"models\[0\] must be an object"):
      gmc._get_downloader_models({"models": ["not-a-dict"]})

  def test_rejects_missing_model_downloader(self):
    with pytest.raises(ValueError, match="model_downloader must be an object"):
      gmc._get_downloader_models({"models": [{}]})

  def test_rejects_missing_name(self):
    with pytest.raises(ValueError, match="name must be a non-empty string"):
      gmc._get_downloader_models({"models": [{"model_downloader": {"hub": "omz"}}]})

  def test_rejects_duplicate_name(self):
    entry = {"model_downloader": {"name": "dup", "hub": "omz"}}
    with pytest.raises(ValueError, match="must be unique"):
      gmc._get_downloader_models({"models": [entry, copy.deepcopy(entry)]})


class TestGetModelConfigSection:

  def test_returns_empty_dict_when_absent(self):
    assert gmc._get_model_config_section({}) == {}

  def test_returns_section_when_present(self):
    section = {"output_file": "out.json"}
    assert gmc._get_model_config_section({"model_config": section}) == section

  def test_rejects_non_dict_section(self):
    with pytest.raises(ValueError, match="must be an object"):
      gmc._get_model_config_section({"model_config": "nope"})


class TestGetModelConfigEntries:

  def test_extracts_entries_with_scenescape(self, minimal_model_entry):
    entries = gmc._get_model_config_entries([minimal_model_entry])
    assert entries == [minimal_model_entry]

  def test_skips_entries_without_scenescape(self, minimal_model_entry):
    downloader_only = {"model_downloader": {"name": "no-scenescape", "hub": "omz"}}
    entries = gmc._get_model_config_entries([minimal_model_entry, downloader_only])
    assert entries == [minimal_model_entry]

  def test_rejects_non_list_models(self):
    with pytest.raises(ValueError, match="JSON array"):
      gmc._get_model_config_entries("not-a-list")

  def test_rejects_non_dict_entry(self):
    with pytest.raises(ValueError, match=r"models\[0\] must be an object"):
      gmc._get_model_config_entries(["not-a-dict"])

  def test_rejects_non_dict_scenescape(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    entry["scenescape"] = "nope"
    with pytest.raises(ValueError, match="scenescape must be an object"):
      gmc._get_model_config_entries([entry])

  def test_rejects_missing_name(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    del entry["scenescape"]["name"]
    with pytest.raises(ValueError, match="scenescape.name and scenescape.config"):
      gmc._get_model_config_entries([entry])

  def test_rejects_missing_config(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    del entry["scenescape"]["config"]
    with pytest.raises(ValueError, match="scenescape.name and scenescape.config"):
      gmc._get_model_config_entries([entry])

  def test_rejects_when_no_entries_have_scenescape(self):
    downloader_only = {"model_downloader": {"name": "no-scenescape", "hub": "omz"}}
    with pytest.raises(ValueError, match="No models include Scenescape config metadata"):
      gmc._get_model_config_entries([downloader_only])


class TestResolveOutputFile:

  def test_uses_explicit_override(self):
    assert gmc._resolve_output_file({"output_file": "a.json"}, "b.json") == "b.json"

  def test_uses_section_value(self):
    assert gmc._resolve_output_file({"output_file": "a.json"}, None) == "a.json"

  def test_falls_back_to_default(self):
    assert gmc._resolve_output_file({}, None) == gmc._DEFAULT_OUTPUT_FILE

  def test_rejects_non_string_section_value(self):
    with pytest.raises(ValueError, match="non-empty string"):
      gmc._resolve_output_file({"output_file": 123}, None)

  def test_rejects_empty_section_value(self):
    with pytest.raises(ValueError, match="non-empty string"):
      gmc._resolve_output_file({"output_file": ""}, None)


class TestBuildConfigEntry:

  def test_builds_expected_entry(self, minimal_model_entry):
    downloader_models = {"person-detection-retail-0013": minimal_model_entry["model_downloader"]}
    name, config, model_proc = gmc._build_config_entry(minimal_model_entry, downloader_models)
    assert name == "retail"
    assert config["params"]["model"].endswith(".xml")
    assert model_proc is None

  def test_adds_model_proc_path_to_params(self, model_entry_with_model_proc):
    downloader_models = {
      "person-detection-retail-0013": model_entry_with_model_proc["model_downloader"],
    }
    _, config, model_proc = gmc._build_config_entry(model_entry_with_model_proc, downloader_models)
    assert config["params"]["model_proc"] == "object_detection/person/person-detection-retail-0013.json"
    assert model_proc is not None

  def test_rejects_missing_model_downloader(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    del entry["model_downloader"]
    with pytest.raises(ValueError, match="model_downloader object"):
      gmc._build_config_entry(entry, {})

  def test_rejects_empty_model_name(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    entry["model_downloader"]["name"] = ""
    with pytest.raises(ValueError, match="non-empty name"):
      gmc._build_config_entry(entry, {})

  def test_rejects_missing_scenescape(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    del entry["scenescape"]
    with pytest.raises(ValueError, match="must include scenescape object"):
      gmc._build_config_entry(entry, {"person-detection-retail-0013": entry["model_downloader"]})

  def test_rejects_empty_scenescape_name(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    entry["scenescape"]["name"] = ""
    downloader_models = {"person-detection-retail-0013": entry["model_downloader"]}
    with pytest.raises(ValueError, match="scenescape.name must be a non-empty string"):
      gmc._build_config_entry(entry, downloader_models)

  def test_rejects_unknown_model_name_reference(self, minimal_model_entry):
    with pytest.raises(ValueError, match="unknown model name"):
      gmc._build_config_entry(minimal_model_entry, {})

  def test_rejects_non_dict_config(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    entry["scenescape"]["config"] = "nope"
    downloader_models = {"person-detection-retail-0013": entry["model_downloader"]}
    with pytest.raises(ValueError, match="scenescape.config must be an object"):
      gmc._build_config_entry(entry, downloader_models)

  def test_rejects_non_dict_adapter_params(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    entry["scenescape"]["config"]["adapter-params"] = "nope"
    downloader_models = {"person-detection-retail-0013": entry["model_downloader"]}
    with pytest.raises(ValueError, match="adapter-params must be an object"):
      gmc._build_config_entry(entry, downloader_models)

  def test_rejects_missing_model_path(self, minimal_model_entry):
    entry = copy.deepcopy(minimal_model_entry)
    del entry["scenescape"]["config"]["params"]["model"]
    downloader_models = {"person-detection-retail-0013": entry["model_downloader"]}
    with pytest.raises(ValueError, match=r"config\.params\.model must be a non-empty string"):
      gmc._build_config_entry(entry, downloader_models)


class TestGenerateModelConfigFromModels:

  def test_happy_path_writes_config(self, valid_models_config, write_json, models_output_dir):
    config_file = write_json(valid_models_config)
    config = gmc.generate_model_config_from_models(str(models_output_dir), config_file)
    assert config["retail"]["params"]["model"].endswith(".xml")

    output_path = models_output_dir / "model_configs" / "model_config.json"
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == config

  def test_writes_model_proc_file(self, model_entry_with_model_proc, write_json, models_output_dir):
    data = {"models": [model_entry_with_model_proc]}
    config_file = write_json(data)
    gmc.generate_model_config_from_models(str(models_output_dir), config_file)

    model_proc_path = models_output_dir / "object_detection" / "person" / "person-detection-retail-0013.json"
    assert model_proc_path.exists()
    content = json.loads(model_proc_path.read_text(encoding="utf-8"))
    assert content["json_schema_version"] == "2.0.0"

  def test_rejects_nonexistent_models_path(self, valid_models_config, write_json, tmp_path):
    config_file = write_json(valid_models_config)
    with pytest.raises(ValueError, match="does not exist"):
      gmc.generate_model_config_from_models(str(tmp_path / "missing"), config_file)

  def test_rejects_duplicate_scenescape_name(self, minimal_model_entry, write_json, models_output_dir):
    other = copy.deepcopy(minimal_model_entry)
    other["model_downloader"]["name"] = "other-model"
    data = {"models": [minimal_model_entry, other]}
    config_file = write_json(data)
    with pytest.raises(ValueError, match="Duplicate scenescape_name"):
      gmc.generate_model_config_from_models(str(models_output_dir), config_file)

  def test_rejects_duplicate_model_proc_path_different_content(
      self, model_entry_with_model_proc, write_json, models_output_dir,
  ):
    other = copy.deepcopy(model_entry_with_model_proc)
    other["model_downloader"]["name"] = "other-model"
    other["scenescape"]["name"] = "other"
    other["scenescape"]["model_proc"]["content"]["json_schema_version"] = "3.0.0"

    data = {"models": [model_entry_with_model_proc, other]}
    config_file = write_json(data)
    with pytest.raises(ValueError, match="Duplicate model_proc path"):
      gmc.generate_model_config_from_models(str(models_output_dir), config_file)

  def test_allows_same_model_proc_path_with_identical_content(
      self, model_entry_with_model_proc, write_json, models_output_dir,
  ):
    other = copy.deepcopy(model_entry_with_model_proc)
    other["model_downloader"]["name"] = "other-model"
    other["scenescape"]["name"] = "other"

    data = {"models": [model_entry_with_model_proc, other]}
    config_file = write_json(data)
    config = gmc.generate_model_config_from_models(str(models_output_dir), config_file)
    assert set(config.keys()) == {"retail", "other"}


class TestRealModelsJsonRegression:
  """Regression test: the shared models.json shipped in the repo must always
  parse successfully and produce a non-empty generated configuration."""

  def test_real_models_json_generates_config(self, real_models_json_path, models_output_dir):
    config = gmc.generate_model_config_from_models(str(models_output_dir), real_models_json_path)
    assert config
    for name, entry in config.items():
      assert entry["params"]["model"], f"Model {name} missing params.model"

