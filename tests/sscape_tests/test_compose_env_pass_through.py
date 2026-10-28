#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for compose process-env vs env-file precedence (SUPASS, DBROOT)."""

import json
import os
import subprocess

import pytest

from tests.utils.compose_env import override_compose_env, sync_supass_for_compose

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


_DBROOT_COMPOSE_YAML = """
services:
  scene:
    image: busybox
    volumes:
      - ${DBROOT}/media:/workspace/media
  child1:
    image: busybox
    volumes:
      - ${DBROOT}/child1/media:/workspace/media
"""


@pytest.fixture
def dbroot_probe(tmp_path):
  compose = tmp_path / "docker-compose.yml"
  compose.write_text(_DBROOT_COMPOSE_YAML)
  db_root = tmp_path / "db"
  env_file = tmp_path / ".env"
  env_file.write_text(f"DBROOT={db_root}\n")
  return tmp_path, env_file, db_root


def _compose_config(project_dir, env_file, process_env):
  return subprocess.run(
    ["docker", "compose", "--env-file", str(env_file), "config", "--format", "json"],
    cwd=project_dir,
    env=process_env,
    capture_output=True,
    text=True,
    check=False,
  )


def _media_bind_sources(project_dir, env_file, process_env):
  result = _compose_config(project_dir, env_file, process_env)
  assert result.returncode == 0, result.stderr
  services = json.loads(result.stdout)["services"]
  return {
    name: os.path.normpath(service["volumes"][0]["source"])
    for name, service in services.items()
  }


# "./"-prefixed so every Compose version resolves it as a bind path against the
# project directory (bare relative paths may be rejected as named volumes).
_STALE_RELATIVE_DBROOT = "./test_data/scene_perf_full"


def test_relative_process_dbroot_overrides_env_file_without_override(dbroot_probe):
  """Documents the compose behaviour: a relative shell DBROOT beats the env-file."""
  project_dir, env_file, db_root = dbroot_probe
  process_env = {**os.environ, "DBROOT": _STALE_RELATIVE_DBROOT}
  sources = _media_bind_sources(project_dir, env_file, process_env)
  stale_root = project_dir.resolve() / "test_data" / "scene_perf_full"
  assert sources == {
    "scene": str(stale_root / "media"),
    "child1": str(stale_root / "child1" / "media"),
  }
  assert not any(src.startswith(str(db_root)) for src in sources.values())


@pytest.mark.parametrize("previous", [None, _STALE_RELATIVE_DBROOT])
def test_override_compose_env_scopes_dbroot_and_restores(dbroot_probe, previous):
  """Scoped DBROOT yields absolute bind mounts; the previous value is restored."""
  project_dir, env_file, db_root = dbroot_probe
  saved = os.environ.get("DBROOT")
  try:
    if previous is None:
      os.environ.pop("DBROOT", None)
    else:
      os.environ["DBROOT"] = previous

    restore = override_compose_env("DBROOT", str(db_root))
    try:
      sources = _media_bind_sources(project_dir, env_file, os.environ.copy())
      assert sources == {
        "scene": str(db_root / "media"),
        "child1": str(db_root / "child1" / "media"),
      }
    finally:
      restore()

    assert os.environ.get("DBROOT") == previous
  finally:
    if saved is None:
      os.environ.pop("DBROOT", None)
    else:
      os.environ["DBROOT"] = saved
