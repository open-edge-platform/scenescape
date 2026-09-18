# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SceneScape backup primitives. NEX-T20001"""

import json
from pathlib import Path

import pytest

from tools.upgrade.backup import compose_base
from tools.upgrade.backup import restore_backup
from tools.upgrade.backup import sha256
from tools.upgrade.backup import verify_backup


def write_backup(tmp_path, content=b"data"):
  artifact = tmp_path / "volumes" / "vol-db.tar.gz"
  artifact.parent.mkdir()
  artifact.write_bytes(content)
  manifest = {
    "schema_version": 1,
    "operation_id": "test-operation",
    "artifacts": [{
      "path": "volumes/vol-db.tar.gz",
      "type": "docker_volume",
      "volume_name": "custom_vol-db",
      "sha256": sha256(artifact),
    }],
  }
  (tmp_path / "manifest.json").write_text(
    json.dumps(manifest), encoding="utf-8")
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


def test_restore_uses_manifest_volume_name(tmp_path, monkeypatch):
  artifact = write_backup(tmp_path)
  calls = []

  def fake_restore(volume_name, archive, overwrite=False, runner=None):
    calls.append((volume_name, archive, overwrite, runner))

  monkeypatch.setattr("tools.upgrade.backup.restore_volume", fake_restore)

  restored = restore_backup(tmp_path, overwrite=True)

  assert restored == ["custom_vol-db"]
  assert calls[0][:3] == ("custom_vol-db", artifact, True)
