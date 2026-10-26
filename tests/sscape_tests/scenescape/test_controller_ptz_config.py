#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import json

import pytest

from scene_common.positioning_assignments import load_assignments, parse_assignments
from scene_common.positioning_config import PositioningConfigError
from controller.ptz.config import (
  DEFAULT_SHADOW_RUN_ID, DEFAULT_SHADOW_SAMPLE_EVERY_N, MODE_ENFORCE, MODE_SHADOW,
  PTZ_ENABLED_ENV_VAR, PTZ_SHADOW_ENV_VAR, PTZConfigError, add_ptz_arguments, env_flag,
  load_ptz_settings, ptz_settings_from_args)

VALID_VALUES = {
  "max_pose_age_s": 0.5,
  "max_clock_offset_s": 0.05,
  "max_detection_pipeline_latency_s": 1.0,
  "max_detection_timestamp_uncertainty_s": 0.05,
}


@pytest.fixture
def files(tmp_path):
  def write(values=None, manifest=None):
    config = tmp_path / "ptz.json"
    config.write_text(json.dumps(VALID_VALUES if values is None else values))
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps(
      {"$comment": "x", "cam-1": "resolver-a"} if manifest is None else manifest))
    return str(config), str(assignments)
  return write


def _load(files_, enabled=True, shadow=False, rewrite_all=False, rewrite_bad=False,
          ntp="ntp", values=None, manifest=None):
  config, assignments = files_(values, manifest)
  return load_ptz_settings(enabled, shadow, config, assignments, rewrite_all, rewrite_bad, ntp)


class TestFlags:
  @pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
  def test_env_flag_true_values(self, monkeypatch, value):
    monkeypatch.setenv(PTZ_ENABLED_ENV_VAR, value)
    assert env_flag(PTZ_ENABLED_ENV_VAR) is True

  @pytest.mark.parametrize("value", [None, "", "0", "false", "off", "maybe"])
  def test_env_flag_is_off_by_default_and_for_other_values(self, monkeypatch, value):
    monkeypatch.delenv(PTZ_ENABLED_ENV_VAR, raising=False)
    if value is not None:
      monkeypatch.setenv(PTZ_ENABLED_ENV_VAR, value)
    assert env_flag(PTZ_ENABLED_ENV_VAR) is False

  def test_both_flags_off_needs_no_files(self):
    assert load_ptz_settings(False, False, None, None, True, True, None) is None


class TestLoadSettings:
  def test_enforce_settings(self, files):
    settings = _load(files)
    assert settings.mode == MODE_ENFORCE and settings.enforcing and not settings.shadow
    assert settings.consumer.max_pose_age_s == 0.5
    assert settings.assignments == {"cam-1": "resolver-a"}
    assert settings.run_id == DEFAULT_SHADOW_RUN_ID
    assert settings.shadow_sample_every_n == DEFAULT_SHADOW_SAMPLE_EVERY_N

  def test_shadow_settings_with_run_id_and_sampling(self, files):
    values = dict(VALID_VALUES, shadow={"run_id": "run-1.a_b", "sample_every_n": 3})
    settings = _load(files, enabled=False, shadow=True, values=values)
    assert settings.mode == MODE_SHADOW and settings.shadow and not settings.enforcing
    assert (settings.run_id, settings.shadow_sample_every_n) == ("run-1.a_b", 3)

  def test_both_flags_are_an_error(self, files):
    with pytest.raises(PTZConfigError, match="mutually exclusive"):
      _load(files, enabled=True, shadow=True)

  @pytest.mark.parametrize("rewrite_all,rewrite_bad", [(True, False), (False, True), (True, True)])
  @pytest.mark.parametrize("shadow", [False, True])
  def test_timestamp_rewrite_is_an_error(self, files, rewrite_all, rewrite_bad, shadow):
    with pytest.raises(PTZConfigError, match="rewrite"):
      _load(files, enabled=not shadow, shadow=shadow, rewrite_all=rewrite_all,
            rewrite_bad=rewrite_bad)

  def test_rewrite_is_allowed_when_ptz_is_off(self, files):
    config, assignments = files()
    assert load_ptz_settings(False, False, config, assignments, True, True, None) is None

  def test_missing_ntp_is_an_error(self, files):
    with pytest.raises(PTZConfigError, match="NTP"):
      _load(files, ntp=None)

  @pytest.mark.parametrize("config,assignments,message", [
    (None, "a.json", "--ptz_config_file"),
    ("c.json", None, "--positioning_assignments_file"),
  ])
  def test_missing_file_arguments_are_errors(self, config, assignments, message):
    with pytest.raises(PTZConfigError, match=message):
      load_ptz_settings(True, False, config, assignments, False, False, "ntp")

  def test_unreadable_config_file(self, tmp_path):
    with pytest.raises(PTZConfigError, match="Cannot read"):
      load_ptz_settings(True, False, str(tmp_path / "missing.json"), "x", False, False, "ntp")

  def test_config_file_must_be_a_json_object(self, tmp_path, files):
    _, assignments = files()
    bad = tmp_path / "list.json"
    bad.write_text("[1]")
    with pytest.raises(PTZConfigError, match="JSON object"):
      load_ptz_settings(True, False, str(bad), assignments, False, False, "ntp")

  def test_config_file_must_be_valid_json(self, tmp_path, files):
    _, assignments = files()
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    with pytest.raises(PTZConfigError, match="Cannot read"):
      load_ptz_settings(True, False, str(bad), assignments, False, False, "ntp")

  @pytest.mark.parametrize("key", list(VALID_VALUES))
  def test_every_consumer_value_is_required(self, files, key):
    values = {k: v for k, v in VALID_VALUES.items() if k != key}
    with pytest.raises(PTZConfigError, match=key):
      _load(files, values=values)

  @pytest.mark.parametrize("key,value", [
    ("max_pose_age_s", 0), ("max_pose_age_s", -1), ("max_clock_offset_s", float("inf")),
    ("max_detection_pipeline_latency_s", True),
    ("max_detection_timestamp_uncertainty_s", -0.1),
    ("max_detection_timestamp_uncertainty_s", "0.1"),
  ])
  def test_invalid_consumer_values(self, files, key, value):
    with pytest.raises(PTZConfigError, match=key):
      _load(files, values=dict(VALID_VALUES, **{key: value}))

  @pytest.mark.parametrize("shadow", [
    "text", {"run_id": ""}, {"run_id": "a/b"}, {"run_id": "x" * 129}, {"run_id": 5},
    {"sample_every_n": 0}, {"sample_every_n": 1.5}, {"sample_every_n": True},
  ])
  def test_invalid_shadow_section(self, files, shadow):
    with pytest.raises(PTZConfigError, match="shadow"):
      _load(files, values=dict(VALID_VALUES, shadow=shadow))

  def test_zero_uncertainty_is_allowed(self, files):
    values = dict(VALID_VALUES, max_detection_timestamp_uncertainty_s=0)
    assert _load(files, values=values).consumer.max_detection_timestamp_uncertainty_s == 0.0

  def test_invalid_manifest_is_an_error(self, files):
    with pytest.raises(PositioningConfigError):
      _load(files, manifest={"cam/1": "resolver-a"})


class TestArguments:
  def _parse(self, argv, monkeypatch, env=None):
    for name in (PTZ_ENABLED_ENV_VAR, PTZ_SHADOW_ENV_VAR):
      monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
      monkeypatch.setenv(name, value)
    parser = argparse.ArgumentParser()
    parser.add_argument("--rewriteAllTime", action="store_true")
    parser.add_argument("--rewriteBadTime", action="store_true")
    parser.add_argument("--ntp")
    add_ptz_arguments(parser, "/opt/controller")
    return parser.parse_args(argv)

  def test_defaults_are_off(self, monkeypatch):
    args = self._parse([], monkeypatch)
    assert (args.ptz, args.ptz_shadow) == (False, False)
    assert args.ptz_config_file == "/opt/controller/ptz-consumer-config.json"
    assert args.positioning_assignments_file == "/opt/controller/positioning-assignments.json"
    assert ptz_settings_from_args(args) is None

  def test_environment_enables_modes(self, monkeypatch):
    args = self._parse([], monkeypatch, {PTZ_SHADOW_ENV_VAR: "true"})
    assert (args.ptz, args.ptz_shadow) == (False, True)

  def test_command_line_overrides_environment(self, monkeypatch):
    args = self._parse(["--no-ptz-shadow", "--ptz"], monkeypatch, {PTZ_SHADOW_ENV_VAR: "true"})
    assert (args.ptz, args.ptz_shadow) == (True, False)

  def test_settings_from_args(self, monkeypatch, files):
    config, assignments = files()
    args = self._parse(["--ptz", "--ntp", "ntp", "--ptz_config_file", config,
                        "--positioning_assignments_file", assignments], monkeypatch)
    assert ptz_settings_from_args(args).mode == MODE_ENFORCE

  def test_settings_from_args_rejects_rewrite(self, monkeypatch, files):
    config, assignments = files()
    args = self._parse(["--ptz", "--rewriteAllTime", "--ntp", "ntp", "--ptz_config_file", config,
                        "--positioning_assignments_file", assignments], monkeypatch)
    with pytest.raises(PTZConfigError):
      ptz_settings_from_args(args)


class TestAssignments:
  def test_comment_keys_are_ignored(self):
    assert parse_assignments({"$comment": "x", "cam": "res"}) == {"cam": "res"}

  @pytest.mark.parametrize("manifest", [
    [], "text", {"": "res"}, {"cam": ""}, {"cam": 5}, {"a/b": "res"}, {"cam": "a+b"},
    {"cam": "a#"}, {"cam": "x" * 257}, {"cam": "a\x00b"},
  ])
  def test_invalid_manifests(self, manifest):
    with pytest.raises(PositioningConfigError):
      parse_assignments(manifest)

  def test_load_reports_unreadable_and_invalid_files(self, tmp_path):
    with pytest.raises(PositioningConfigError, match="Cannot read"):
      load_assignments(str(tmp_path / "missing.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    with pytest.raises(PositioningConfigError, match="Cannot read"):
      load_assignments(str(bad))

  def test_load_reads_file(self, tmp_path):
    path = tmp_path / "m.json"
    path.write_text('{"cam": "res"}')
    assert load_assignments(str(path)) == {"cam": "res"}
