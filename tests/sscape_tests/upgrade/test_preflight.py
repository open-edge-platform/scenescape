# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SceneScape upgrade preflight. NEX-T20000"""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tools.upgrade.preflight import build_report
from tools.upgrade.preflight import classify_volumes
from tools.upgrade.preflight import compose_command
from tools.upgrade.preflight import find_transition
from tools.upgrade.preflight import load_compatibility
from tools.upgrade.preflight import redact


def test_load_and_find_explicit_transition(tmp_path):
  manifest_path = tmp_path / "compatibility.json"
  manifest_path.write_text(json.dumps({
    "schema_version": 1,
    "transitions": [{"source": "1.0", "target": "1.1"}],
  }), encoding="utf-8")

  manifest = load_compatibility(manifest_path)

  assert find_transition(manifest, "1.0", "1.1") == {
    "source": "1.0", "target": "1.1"}
  assert find_transition(manifest, "1.0", "2.0") is None


def test_rejects_unknown_manifest_schema(tmp_path):
  manifest_path = tmp_path / "compatibility.json"
  manifest_path.write_text(
    '{"schema_version": 2, "transitions": []}', encoding="utf-8")

  with pytest.raises(ValueError, match="unsupported compatibility"):
    load_compatibility(manifest_path)


def test_compose_command_preserves_files_and_profiles():
  assert compose_command([Path("base.yml"), Path("reid.yml")], ["controller"]) == [
    "docker", "compose", "-f", "base.yml", "-f", "reid.yml",
    "--profile", "controller", "config", "--format", "json"]


def test_classifies_data_and_tmpfs_volumes():
  volumes = classify_volumes({"volumes": {
    "vol-db": {"name": "custom_vol-db"},
    "scratch": {"name": "custom_scratch"},
    "vol-model-cache": {
      "name": "custom_cache", "driver_opts": {"type": "tmpfs"}},
  }})

  assert volumes == [
    {"logical_name": "scratch", "name": "custom_scratch",
     "classification": "unclassified"},
    {"logical_name": "vol-db", "name": "custom_vol-db", "classification": "data"},
    {"logical_name": "vol-model-cache", "name": "custom_cache",
     "classification": "disposable_cache"},
  ]


def test_redacts_nested_sensitive_values():
  value = {
    "password": "visible-no-more",
    "environment": {"API_TOKEN": "token", "MODE": "safe"},
    "items": [{"client_auth": "credential"}],
  }

  assert redact(value) == {
    "password": "<redacted>",
    "environment": {"API_TOKEN": "<redacted>", "MODE": "safe"},
    "items": [{"client_auth": "<redacted>"}],
  }


def test_report_fails_closed_for_unsupported_transition(tmp_path):
  responses = iter([
    CompletedProcess([], 0, stdout="abc123\n", stderr=""),
    CompletedProcess([], 0, stdout=" M local-change\n", stderr=""),
  ])

  def runner(*_args, **_kwargs):
    return next(responses)

  report = build_report(
    "1.0", "2.0", None,
    {"name": "custom", "services": {}, "volumes": {"vol-db": {}}},
    tmp_path, [tmp_path / "compose.yml"], ["controller"], runner=runner)

  assert report["status"] == "unsupported"
  assert report["blockers"][0]["code"] == "unsupported_transition"
  assert report["deployment"]["git"]["dirty"] is True
