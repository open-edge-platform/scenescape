# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for resumable adjacent-release orchestration. NEX-T20004"""

import json

import pytest

from tools.upgrade.orchestrator import compose_health
from tools.upgrade.orchestrator import begin_upgrade
from tools.upgrade.orchestrator import plan_upgrade
from tools.upgrade.orchestrator import read_operation_state
from tools.upgrade.orchestrator import resume_upgrade
from tools.upgrade.orchestrator import rollback_upgrade
from tools.upgrade.orchestrator import verify_upgrade
from tools.upgrade.orchestrator import write_operation_state


def test_state_is_resumable_and_events_are_append_only(tmp_path):
  base = {"schema_version": 1, "status": "action_required", "phase": "backup"}
  write_operation_state(tmp_path, base)
  write_operation_state(tmp_path, {**base, "phase": "awaiting_database_cutover"})

  assert read_operation_state(tmp_path)["phase"] == "awaiting_database_cutover"
  events = (tmp_path / "upgrade-events.jsonl").read_text().splitlines()
  assert [json.loads(line)["phase"] for line in events] == [
    "backup", "awaiting_database_cutover"]


@pytest.mark.parametrize(
  "target_volumes, expected_status, expected_blocker",
  [
    ({"vol-db": {"name": "factory_db"},
      "vol-media": {"name": "factory_media"}}, "action_required", None),
    ({"vol-db": {"name": "renamed_db"}}, "unsupported",
     "persistent_volume_migration_required"),
  ])
def test_plan_reports_compose_persistence_changes(
    tmp_path, target_volumes, expected_status, expected_blocker):
  responses = iter([
    type("Result", (), {"stdout": "source-revision\n"})(),
    type("Result", (), {"stdout": ""})(),
    type("Result", (), {"stdout": "target-revision\n"})(),
    type("Result", (), {"stdout": ""})(),
  ])

  report = plan_upgrade(
    "2026.1.0", "2026.2.0", "tools/upgrade/compatibility.json",
    {"name": "factory", "services": {"web": {}},
     "volumes": {"vol-db": {"name": "factory_db"}}},
    {"name": "factory", "services": {"web": {}, "analytics": {}},
     "volumes": target_volumes},
    tmp_path / "source", tmp_path / "target", [tmp_path / "source.yml"],
    [tmp_path / "target.yml"], [], [], "factory",
    runner=lambda *_args, **_kwargs: next(responses))

  assert report["status"] == expected_status
  assert report["compose_changes"]["services_added"] == ["analytics"]
  blocker_codes = [item["code"] for item in report["blockers"]]
  if expected_blocker:
    assert expected_blocker in blocker_codes
  else:
    assert blocker_codes == []


def test_compose_health_rejects_unhealthy_service():
  class Result:
    stdout = json.dumps([{"Service": "web", "State": "running",
                          "Health": "unhealthy"}])

  with pytest.raises(ValueError, match="web"):
    compose_health(["docker", "compose"], expected_services=["web"],
                   runner=lambda *_args, **_kwargs: Result())


def test_compose_health_requires_expected_services():
  with pytest.raises(ValueError, match="required for health verification"):
    compose_health(["docker", "compose"], expected_services=[],
                   runner=lambda *_a, **_k: None)


def test_compose_health_includes_stopped_and_expected_services():
  commands = []

  class Result:
    stdout = json.dumps([{"Service": "web", "State": "running", "Health": "healthy"}])

  def runner(command, **_kwargs):
    commands.append(command)
    return Result()

  with pytest.raises(ValueError, match="pgserver"):
    compose_health(["docker", "compose"], expected_services=["web", "pgserver"],
                   runner=runner)

  assert "--all" in commands[0]


def test_compose_health_ignores_non_expected_exited_containers():
  class Result:
    stdout = json.dumps([
      {"Service": "web", "State": "running", "Health": "healthy"},
      {"Service": "legacy", "State": "exited"},
    ])

  services = compose_health(
    ["docker", "compose"], expected_services=["web"],
    runner=lambda *_a, **_k: Result())

  assert len(services) == 2


def test_resume_runs_only_safe_target_commands(tmp_path):
  state = {
    "schema_version": 1, "source_version": "2026.1.0",
    "target_version": "2026.2.0", "status": "action_required",
    "phase": "awaiting_database_cutover", "backup_dir": "/backup",
    "rollback_available": True,
    "source_deployment": {
      "root": "2026.1", "project_name": "custom",
      "compose_files": ["2026.1/compose.yml"],
      "profiles": ["controller"],
    },
    "target_deployment": {
      "root": "2026.2", "project_name": "custom",
      "compose_files": ["2026.2/compose.yml"],
      "profiles": ["controller"],
      "services": [{"name": "web", "image": "web:target"}],
    },
  }
  write_operation_state(tmp_path, state)
  commands = []

  class Result:
    stdout = json.dumps([{"Service": "web", "State": "running", "Health": "healthy"}])

  def runner(command, **_kwargs):
    commands.append(command)
    return Result()

  def migrator(*_args, **_kwargs):
    return None

  resume_upgrade(tmp_path, "tools/upgrade/compatibility.json", runner=runner,
                 migrator=migrator)

  assert commands[0][-1] == "pull"
  assert commands[1][-2:] == ["down", "--remove-orphans"]
  assert commands[2][-3:] == ["up", "-d", "pgserver"]
  assert commands[3][-4:] == ["up", "-d", "--force-recreate", "--remove-orphans"]
  assert commands[4][-4:] == ["ps", "--all", "--format", "json"]
  assert "2026.1/compose.yml" in commands[1]
  assert all("2026.2/compose.yml" in command
             for command in (commands[0], *commands[2:]))
  assert all("-v" not in command for command in commands)


def test_verify_rejects_pre_cutover_phase(tmp_path):
  write_operation_state(tmp_path, {
    "schema_version": 1, "source_version": "2026.1.0",
    "target_version": "2026.2.0", "phase": "awaiting_database_cutover",
    "status": "action_required",
    "target_deployment": {
      "root": "2026.2", "project_name": "custom",
      "compose_files": ["2026.2/compose.yml"], "profiles": [],
      "services": [{"name": "web"}],
    },
  })

  with pytest.raises(ValueError, match="release-resume"):
    verify_upgrade(tmp_path, "tools/upgrade/compatibility.json",
                   migrator=lambda *_a, **_k: None)


def test_begin_requires_verified_backup_before_cutover(tmp_path):
  plan = {
    "status": "ready", "source_version": "2026.1.0", "target_version": "2026.2.0",
    "source_deployment": {"project_name": "custom", "root": str(tmp_path),
                          "compose_files": [str(tmp_path / "2026.1/compose.yml")],
                          "profiles": [], "volumes": []},
    "target_deployment": {"project_name": "custom", "root": str(tmp_path),
                          "compose_files": ["2026.2/compose.yml"],
                          "profiles": []},
  }
  backup_dir = tmp_path / "backup"
  backup_calls = []

  def backup(*args, **_kwargs):
    backup_calls.append((args, _kwargs))
    return backup_dir, {}

  def reject_backup(_path):
    raise ValueError("checksum mismatch")

  with pytest.raises(ValueError, match="checksum mismatch"):
    begin_upgrade(plan, tmp_path / "state", tmp_path / "secrets", tmp_path,
                  backup=backup, verifier=reject_backup)

  assert backup_calls[0][0][1] == str(tmp_path)
  assert backup_calls[0][0][2] == [tmp_path / "2026.1/compose.yml"]
  assert not (tmp_path / "state" / "upgrade-state.json").exists()


def test_rollback_stops_source_and_target_stacks(tmp_path):
  write_operation_state(tmp_path, {
    "schema_version": 1, "phase": "failed", "status": "failed",
    "backup_dir": "/verified/backup", "rollback_available": True,
    "source_deployment": {
      "root": "/source", "project_name": "custom",
      "compose_files": ["/source/compose.yml"], "profiles": [],
    },
    "target_deployment": {
      "root": "/target", "project_name": "custom",
      "compose_files": ["/target/compose.yml"], "profiles": ["controller"],
    },
  })
  calls = []

  def restorer(path, overwrite=False, **kwargs):
    calls.append((path, overwrite, kwargs))
    return ["custom_vol-db"]

  state = rollback_upgrade(tmp_path, overwrite=True, restorer=restorer)

  assert calls[0][0] == "/verified/backup"
  assert calls[0][1] is True
  stacks = calls[0][2]["compose_stacks"]
  assert calls[0][2]["project_name"] == "custom"
  assert [stack["root"] for stack in stacks] == ["/target", "/source"]
  assert state["phase"] == "data_restored"
