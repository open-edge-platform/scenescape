#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for compose SUPASS process-env vs env-file precedence."""

import os
import subprocess

import pytest

from tests.utils.compose_env import sync_supass_for_compose

TEST_NAME = "NEX-T22101"

_COMPOSE_YAML = """
services:
  probe:
    image: busybox
    environment:
      - SUPASS
"""


@pytest.fixture
def compose_probe(tmp_path):
  compose = tmp_path / "docker-compose.yml"
  compose.write_text(_COMPOSE_YAML)
  env_file = tmp_path / ".env"
  env_file.write_text("SUPASS=from-env-file\n")
  return tmp_path, env_file


def _compose_supass(project_dir, env_file, process_env):
  result = subprocess.run(
    ["docker", "compose", "--env-file", str(env_file), "config"],
    cwd=project_dir,
    env=process_env,
    capture_output=True,
    text=True,
    check=False,
  )
  assert result.returncode == 0, result.stderr
  for line in result.stdout.splitlines():
    if "SUPASS:" in line:
      return line.split(":", 1)[1].strip().strip('"').strip("'")
  raise AssertionError(f"SUPASS not found in compose config:\n{result.stdout}")


def test_empty_process_supass_overrides_env_file_without_sync(compose_probe):
  """Documents the compose bug: empty process SUPASS beats the env-file."""
  project_dir, env_file = compose_probe
  process_env = {**os.environ, "SUPASS": ""}
  assert _compose_supass(project_dir, env_file, process_env) == ""


def test_sync_supass_for_compose_wins_over_empty_process_env(compose_probe):
  """After sync, compose pass-through uses the session password."""
  project_dir, env_file = compose_probe
  previous = os.environ.get("SUPASS")
  try:
    os.environ["SUPASS"] = ""
    sync_supass_for_compose("session-password")
    assert os.environ["SUPASS"] == "session-password"
    assert _compose_supass(project_dir, env_file, os.environ.copy()) == "session-password"
  finally:
    if previous is None:
      os.environ.pop("SUPASS", None)
    else:
      os.environ["SUPASS"] = previous
