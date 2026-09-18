# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for authorized database migrations. NEX-T20002"""

import json
from pathlib import Path
import subprocess

import pytest

from tools.upgrade.migration import migration_plan
from tools.upgrade.migration import migration_command
from tools.upgrade.migration import prepare_migrations
from tools.upgrade.migration import upgrade_postgres_engine
from tools.upgrade.migration import write_state
from tools.upgrade.preflight import find_transition
from tools.upgrade.preflight import load_compatibility


TRANSITION = {
  "source": "2026.1.0",
  "target": "2026.2.0",
  "postgres": {"source": "17.6", "target": "17.6", "engine_upgrade": False},
  "django_migrations": ["0002_fields", "0003_cache"],
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_committed_migration_uses_absolute_manager_path():
  command = migration_command(
    ["target.yml"], [], "factory", ["migrate", "--noinput"], "/target")

  assert command[-3:] == [
    "/home/scenescape/Scenescape/manage.py", "migrate", "--noinput"]


def test_plan_reports_only_missing_committed_migrations():
  plan = migration_plan(TRANSITION, ["0001_initial", "0002_fields"])

  assert plan["applied"] == ["0002_fields"]
  assert plan["pending"] == ["0003_cache"]


def test_plan_allows_authorized_engine_upgrade_strategy():
  transition = dict(TRANSITION)
  transition["postgres"] = {"engine_upgrade": True}

  assert migration_plan(transition, [])["strategy"] == "committed"


@pytest.mark.parametrize("strategy, expected_command", [
  ("legacy_runtime", "/workspace/manager/tools/migration"),
  ("fake_initial", "--fake-initial"),
])
def test_prepare_runs_transition_strategy(strategy, expected_command):
  commands = []
  transition = {**TRANSITION, "django_strategy": strategy}

  def runner(command, **_kwargs):
    commands.append(command)

  prepare_migrations(
    ["target.yml"], [], "factory", transition, "/target", runner=runner)

  assert any(expected_command in item for command in commands for item in command)
  if strategy == "legacy_runtime":
    assert "/target/manager/tools:/workspace/manager/tools:ro" in commands[0]
    assert "--entrypoint" not in commands[0]
    assert commands[0][-10:] == [
      "--shell", "webserver", "--dbhost", "pgserver", "--dbtype", "postgres",
      "--dbport", "5432", "--nointerface", "bash",
      "/workspace/manager/tools/migration"][-10:]
  else:
    assert all(any("/run/secrets/django/secrets.py" in item for item in command)
               for command in commands)
    assert all(command[command.index("--entrypoint") + 1] == "sh"
               for command in commands)


def test_engine_upgrade_restores_verified_logical_dump(tmp_path, monkeypatch):
  dump = tmp_path / "scenescape.psql"
  dump.write_bytes(b"database dump")
  monkeypatch.setattr("tools.upgrade.migration.verify_backup", lambda _path: {
    "artifacts": [{"type": "postgres_logical_dump", "path": dump.name}],
  })
  deployment = {
    "root": "/target", "project_name": "factory",
    "compose_files": ["/target/compose.yml"], "profiles": [],
    "volumes": [{"logical_name": "vol-db", "name": "factory_vol-db"}],
  }
  commands = []

  def runner(command, **kwargs):
    commands.append((command, kwargs))

  upgrade_postgres_engine(
    deployment, deployment,
    {"postgres": {"engine_upgrade": True}}, tmp_path, runner=runner)

  assert commands[0][0][-2:] == ["down", "--remove-orphans"]
  assert commands[1][0] == ["docker", "volume", "rm", "factory_vol-db"]
  assert commands[2][0][-3:] == ["up", "-d", "pgserver"]
  assert any("pg_isready" in item for item in commands[3][0])
  assert commands[4][0][-10:] == [
    "exec", "-T", "pgserver", "psql", "-v", "ON_ERROR_STOP=1",
    "-U", "scenescape", "-d", "scenescape"]
  assert commands[4][1]["stdin"].name == str(dump)


def test_engine_upgrade_rejects_changed_database_volume(tmp_path, monkeypatch):
  monkeypatch.setattr("tools.upgrade.migration.verify_backup", lambda _path: {
    "artifacts": [{"type": "postgres_logical_dump", "path": "dump.psql"}],
  })
  source = {"volumes": [{"logical_name": "vol-db", "name": "source_db"}]}
  target = {"volumes": [{"logical_name": "vol-db", "name": "target_db"}]}

  with pytest.raises(ValueError, match="stable volume identity"):
    upgrade_postgres_engine(
      source, target, {"postgres": {"engine_upgrade": True}}, tmp_path)


def test_state_is_resumable_and_contains_no_credentials(tmp_path):
  state = write_state(tmp_path, "2026.1.0", "2026.2.0", "planned",
                      migration_plan(TRANSITION, []))
  persisted = json.loads((tmp_path / "migration-state.json").read_text())

  assert persisted == state
  assert persisted["phase"] == "planned"
  assert "password" not in json.dumps(persisted).lower()


def test_repository_manifest_authorizes_every_adjacent_release():
  manifest = load_compatibility(
    "tools/upgrade/compatibility.json")

  assert find_transition(manifest, "1.4.0", "2025.2") is not None
  assert find_transition(manifest, "2025.2", "2026.0.0") is not None
  assert find_transition(manifest, "2026.0.0", "2026.1.0") is not None
  assert find_transition(manifest, "2026.1.0", "2026.2.0") is not None
  assert find_transition(manifest, "2026.0.0", "2026.2.0") is None


def test_cli_requires_release_workflow_for_postgres_engine_upgrade():
  result = subprocess.run([
    REPOSITORY_ROOT / "tools" / "upgrade" / "scenescape-upgrade",
    "database-migrate", "--source-version", "1.4.0",
    "--target-version", "2025.2",
  ], check=False, capture_output=True, text=True)

  report = json.loads(result.stdout)
  assert result.returncode == 3
  assert report["status"] == "unsupported"
  assert report["blockers"][0]["code"] == "release_workflow_required"
