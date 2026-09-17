# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for resumable adjacent-release orchestration. NEX-T20004"""

import json

import pytest

from tools.upgrade.orchestrator import compose_health
from tools.upgrade.orchestrator import begin_upgrade
from tools.upgrade.orchestrator import read_operation_state
from tools.upgrade.orchestrator import resume_upgrade
from tools.upgrade.orchestrator import rollback_upgrade
from tools.upgrade.orchestrator import write_operation_state


def test_state_is_resumable_and_events_are_append_only(tmp_path):
  base = {"schema_version": 1, "status": "action_required", "phase": "backup"}
  write_operation_state(tmp_path, base)
  write_operation_state(tmp_path, {**base, "phase": "awaiting_database_cutover"})

  assert read_operation_state(tmp_path)["phase"] == "awaiting_database_cutover"
  events = (tmp_path / "upgrade-events.jsonl").read_text().splitlines()
  assert [json.loads(line)["phase"] for line in events] == [
    "backup", "awaiting_database_cutover"]


def test_compose_health_rejects_unhealthy_service():
  class Result:
    stdout = json.dumps([{"Service": "web", "State": "running",
                          "Health": "unhealthy"}])

  with pytest.raises(ValueError, match="web"):
    compose_health(["docker", "compose"], runner=lambda *_args, **_kwargs: Result())


def test_resume_runs_only_safe_target_commands(tmp_path):
  state = {
    "schema_version": 1, "source_version": "2026.1.0",
    "target_version": "2026.2.0", "status": "action_required",
    "phase": "awaiting_database_cutover", "backup_dir": "/backup",
    "rollback_available": True,
    "deployment": {"project_name": "custom", "compose_files": ["custom.yml"],
                   "profiles": ["controller"]},
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
  assert commands[1][-3:] == ["up", "-d", "--force-recreate"]
  assert commands[2][-3:] == ["ps", "--format", "json"]
  assert all("down" not in command and "-v" not in command for command in commands)


def test_begin_requires_verified_backup_before_cutover(tmp_path):
  plan = {
    "status": "ready", "source_version": "2026.1.0", "target_version": "2026.2.0",
    "deployment": {"project_name": "custom", "root": str(tmp_path),
                   "compose_files": ["custom.yml"], "profiles": [], "volumes": []},
  }
  backup_dir = tmp_path / "backup"

  def backup(*_args, **_kwargs):
    return backup_dir, {}

  def reject_backup(_path):
    raise ValueError("checksum mismatch")

  with pytest.raises(ValueError, match="checksum mismatch"):
    begin_upgrade(plan, tmp_path / "state", tmp_path / "secrets", tmp_path,
                  backup=backup, verifier=reject_backup)

  assert not (tmp_path / "state" / "upgrade-state.json").exists()


def test_rollback_uses_verified_backup_path(tmp_path):
  write_operation_state(tmp_path, {
    "schema_version": 1, "phase": "failed", "status": "failed",
    "backup_dir": "/verified/backup", "rollback_available": True,
  })
  calls = []

  def restorer(path, overwrite=False):
    calls.append((path, overwrite))
    return ["custom_vol-db"]

  state = rollback_upgrade(tmp_path, overwrite=True, restorer=restorer)

  assert calls == [("/verified/backup", True)]
  assert state["phase"] == "data_restored"
