# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SceneScape backup primitives. NEX-T20001"""

import json
from pathlib import Path

import pytest

from tools.upgrade.backup import compose_base
from tools.upgrade.backup import restore_backup
from tools.upgrade.backup import restore_volume
from tools.upgrade.backup import sha256
from tools.upgrade.backup import verify_backup


def write_backup(tmp_path, content=b"data", artifacts=None):
  artifact = tmp_path / "volumes" / "vol-db.tar.gz"
  artifact.parent.mkdir(parents=True, exist_ok=True)
  artifact.write_bytes(content)
  if artifacts is None:
    artifacts = [{
      "path": "volumes/vol-db.tar.gz",
      "type": "docker_volume",
      "volume_name": "custom_vol-db",
      "sha256": sha256(artifact),
    }]
  manifest = {
    "schema_version": 1,
    "operation_id": "test-operation",
    "deployment_root": str(tmp_path),
    "project_name": "custom",
    "compose_files": [str(tmp_path / "compose.yml")],
    "profiles": [],
    "artifacts": artifacts,
  }
  (tmp_path / "manifest.json").write_text(
    json.dumps(manifest), encoding="utf-8")
  (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
  return artifact


def test_compose_base_preserves_custom_inputs():
  assert compose_base(
    [Path("custom.yml")], ["controller", "mapping"], "custom") == [
      "docker", "compose", "--project-name", "custom", "-f", "custom.yml",
      "--profile", "controller", "--profile", "mapping"]


def test_verify_backup_accepts_matching_checksum(tmp_path):
  write_backup(tmp_path)

  manifest = verify_backup(tmp_path)

  assert manifest["operation_id"] == "test-operation"


def test_verify_backup_rejects_checksum_mismatch(tmp_path):
  artifact = write_backup(tmp_path)
  artifact.write_bytes(b"changed")

  with pytest.raises(ValueError, match="checksum mismatch"):
    verify_backup(tmp_path)


def test_verify_backup_rejects_missing_artifact(tmp_path):
  artifact = write_backup(tmp_path)
  artifact.unlink()

  with pytest.raises(ValueError, match="artifact is missing"):
    verify_backup(tmp_path)


def test_verify_backup_rejects_empty_artifact_list(tmp_path):
  write_backup(tmp_path, artifacts=[])

  with pytest.raises(ValueError, match="no artifacts"):
    verify_backup(tmp_path)


def test_verify_backup_rejects_structurally_invalid_artifact(tmp_path):
  write_backup(tmp_path, artifacts=[{"path": "volumes/vol-db.tar.gz"}])

  with pytest.raises(ValueError, match="missing required fields"):
    verify_backup(tmp_path)


def test_verify_backup_rejects_path_traversal(tmp_path):
  outside = tmp_path.parent / "outside.tar.gz"
  outside.write_bytes(b"data")
  write_backup(tmp_path, artifacts=[{
    "path": f"../{outside.name}",
    "type": "deployment_file",
    "sha256": sha256(outside),
  }])

  with pytest.raises(ValueError, match="escapes backup directory"):
    verify_backup(tmp_path)


def test_restore_volume_mounts_archive_at_fixed_path(tmp_path, monkeypatch):
  archive = tmp_path / "evil; rm -rf root.tar.gz"
  archive.write_bytes(b"data")
  commands = []

  def runner(command, **_kwargs):
    commands.append(command)
    return type("Result", (), {"returncode": 0})()

  monkeypatch.setattr("tools.upgrade.backup.volume_is_empty", lambda *_a, **_k: True)
  restore_volume("custom_vol-db", archive, overwrite=True, runner=runner)

  docker_run = commands[-1]
  assert f"{archive}:/backup/archive.tar.gz:ro" in docker_run
  shell_command = docker_run[docker_run.index("-c") + 1]
  assert shell_command.endswith("tar xzpf /backup/archive.tar.gz -C /volume")
  assert "evil" not in shell_command


def test_restore_stops_all_project_containers(tmp_path, monkeypatch):
  artifact = write_backup(tmp_path)
  calls = []

  def fake_restore(volume_name, archive, overwrite=False, runner=None):
    calls.append(("restore", volume_name, archive, overwrite))

  def runner(command, **_kwargs):
    calls.append(("run", command))
    if command[:2] == ["docker", "ps"]:
      return type("Result", (), {"returncode": 0, "stdout": "abc\ndef\n"})()
    return type("Result", (), {"returncode": 0, "stdout": ""})()

  monkeypatch.setattr("tools.upgrade.backup.restore_volume", fake_restore)

  restored = restore_backup(
    tmp_path, overwrite=True, runner=runner,
    compose_stacks=[
      {"compose_files": [str(tmp_path / "target.yml")], "profiles": [],
       "project_name": "custom", "root": str(tmp_path)},
      {"compose_files": [str(tmp_path / "compose.yml")], "profiles": [],
       "project_name": "custom", "root": str(tmp_path)},
    ],
    project_name="custom")

  assert restored == ["custom_vol-db"]
  run_commands = [command for kind, *rest in calls if kind == "run"
                  for command in rest[:1]]
  downs = [command for command in run_commands
           if command[-2:] == ["down", "--remove-orphans"]]
  assert len(downs) == 2
  assert any(command[:2] == ["docker", "ps"] for command in run_commands)
  assert ["docker", "stop", "--time", "30", "abc", "def"] in run_commands
  assert calls[-1][:3] == ("restore", "custom_vol-db", artifact)
