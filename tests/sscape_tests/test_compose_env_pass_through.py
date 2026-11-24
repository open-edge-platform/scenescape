#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for compose process-env vs env-file precedence (SUPASS, DBROOT)."""

import json
import os
import subprocess
from pathlib import Path

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


@pytest.mark.parametrize(('port', 'expected'), [(None, '1883'), ('11883', '11883')])
def test_mlops_demo_broker_is_only_published_on_loopback(tmp_path, port, expected):
  root = Path(__file__).resolve().parents[2]
  env = {**os.environ, 'SECRETSDIR': str(tmp_path)}
  env.pop('BROKER_PORT', None)
  if port is not None:
    env['BROKER_PORT'] = port
  result = subprocess.run(
    ['docker', 'compose', '--env-file', '/dev/null',
     '-f', 'sample_data/compose/compose.dl-streamer-example.yml',
     '-f', 'sample_data/mlops_flow/compose.scenescape-override.yml',
     'config', '--format', 'json'],
    cwd=root, env=env, capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  ports = json.loads(result.stdout)['services']['broker']['ports']
  assert {(entry.get('host_ip'), entry['published'], entry['target']) for entry in ports} == {
    ('127.0.0.1', expected, 1883)
  }


@pytest.mark.parametrize("mount_type", ["volume", "bind"])
def test_mlops_dlsps_mounts_vippet_models_read_only(tmp_path, mount_type):
  root = Path(__file__).resolve().parents[2]
  secret_dir = tmp_path / "secrets"
  (secret_dir / "certs").mkdir(parents=True)
  (secret_dir / "certs" / "scenescape-ca.pem").touch()
  env = {
    **os.environ,
    "SECRETSDIR": str(secret_dir),
  }
  overlay = f"compose.dlsps2-models-{mount_type}.yml"
  if mount_type == "volume":
    env["VIPPET_MODELS_VOLUME"] = "vippet-models-test"
    expected_source = "vippet-models"
  else:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    env["VIPPET_MODELS_DIR"] = str(models_dir)
    expected_source = str(models_dir)
  result = subprocess.run(
    ["docker", "compose", "--env-file", "/dev/null",
     "-f", "sample_data/mlops_flow/compose.dlsps2.yml",
     "-f", f"sample_data/mlops_flow/{overlay}", "config", "--format", "json"],
    cwd=root, env=env, capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  config = json.loads(result.stdout)
  service = config["services"]["dlstreamer-pipeline-server"]
  model_mount = next(volume for volume in service["volumes"] if volume["target"] == "/models")
  assert model_mount["type"] == mount_type
  assert model_mount["source"] == expected_source
  assert model_mount["read_only"] is True
  assert service.get("ports", []) == []
  if mount_type == "volume":
    assert config["volumes"]["vippet-models"]["external"] is True
    assert config["volumes"]["vippet-models"]["name"] == "vippet-models-test"
  else:
    assert "volumes" not in config


@pytest.mark.parametrize("existing", ["", "localhost,mediamtx,.example.test"])
def test_mlops_vippet_proxy_override_preserves_exclusions(tmp_path, existing):
  root = Path(__file__).resolve().parents[2]
  base = tmp_path / "compose.yml"
  base.write_text("""
services:
  vippet:
    image: busybox
    environment:
      http_proxy: http://proxy.example.test:8080
      KEEP_SETTING: unchanged
  dlstreamer-pipeline-server:
    image: busybox
    environment:
      http_proxy: http://proxy.example.test:8080
""")
  result = subprocess.run(
    ["docker", "compose", "--env-file", "/dev/null", "-f", str(base),
     "-f", str(root / "sample_data/mlops_flow/compose.vippet-proxy-override.yml"),
     "config", "--format", "json"],
    env={**os.environ, "VIPPET_NO_PROXY": existing, "VIPPET_DLSPS_NO_PROXY": "localhost"},
    capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  services = json.loads(result.stdout)["services"]
  for service, previous in [("vippet", existing), ("dlstreamer-pipeline-server", "localhost")]:
    environment = services[service]["environment"]
    expected = f"{previous},mediaserver" if previous else "mediaserver"
    assert environment["no_proxy"] == expected
    assert environment["NO_PROXY"] == expected
    assert environment["http_proxy"] == "http://proxy.example.test:8080"
  assert services["vippet"]["environment"]["KEEP_SETTING"] == "unchanged"


@pytest.fixture
def mlops_docker_stub(tmp_path):
  docker = tmp_path / "docker"
  docker.write_text("""#!/bin/bash
printf '%s\\n' "$*" >> "$DOCKER_CALLS"
case "$1" in
  network) echo "vippet dlstreamer-pipeline-server" ;;
  inspect)
    case "$3" in
      *State.Running*) if [ "$4" = "$STOPPED_CONTAINER" ]; then echo false; else echo true; fi ;;
      *working_dir*) echo "$FAKE_PROJECT_DIR" ;;
      *config_files*) echo "$FAKE_PROJECT_DIR/compose.yml" ;;
      *project*) echo vippet-project ;;
      *Config.Image*) echo example/image:tag ;;
      *) exit 1 ;;
    esac ;;
  exec)
    if [ "$2" = "ui-id" ]; then
      [ "$RELOAD_FAIL" != 1 ] || exit 1
    elif [ "$3" = "sh" ]; then
      echo "localhost,mediamtx"
    fi ;;
  compose) ;;
  ps) if [ "$UI_RUNNING" = 1 ]; then echo ui-id; fi ;;
  *) exit 1 ;;
esac
""")
  docker.chmod(0o755)
  return docker


def _run_mlops_configure(tmp_path, **settings):
  root = Path(__file__).resolve().parents[2]
  log = tmp_path / "docker-calls"
  env = {
    **os.environ,
    "PATH": f"{tmp_path}:{os.environ['PATH']}",
    "DOCKER_CALLS": str(log),
    "FAKE_PROJECT_DIR": str(tmp_path),
    "UI_RUNNING": "1",
    **settings,
  }
  result = subprocess.run(
    ["make", "-C", str(root), "configure-mlops-vippet",
     f"VIPPET_MODELS_DIR={tmp_path}", "VIPPET_MODELS_VOLUME="],
    env=env, capture_output=True, text=True, check=False,
  )
  return result, log.read_text().splitlines()


@pytest.mark.parametrize("ui_running,reload_fail,success", [
  ("1", "0", True),
  ("0", "0", True),
  ("1", "1", False),
])
def test_mlops_configure_refreshes_running_ui(tmp_path, mlops_docker_stub,
                                             ui_running, reload_fail, success):
  result, calls = _run_mlops_configure(tmp_path, UI_RUNNING=ui_running, RELOAD_FAIL=reload_fail)
  assert (result.returncode == 0) is success
  reloads = [index for index, call in enumerate(calls) if call == "exec ui-id nginx -s reload"]
  assert bool(reloads) is (ui_running == "1")
  if reloads:
    compose = next(index for index, call in enumerate(calls) if call.startswith("compose "))
    assert compose < reloads[0]
  else:
    assert "UI container is not running" in result.stdout


def test_mlops_configure_reports_stopped_server(tmp_path, mlops_docker_stub):
  result, calls = _run_mlops_configure(tmp_path, STOPPED_CONTAINER="dlstreamer-pipeline-server")
  assert result.returncode != 0
  assert "docker start dlstreamer-pipeline-server" in result.stdout
  assert not any(call.startswith("compose ") for call in calls)
