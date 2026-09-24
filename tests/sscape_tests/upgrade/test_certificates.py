# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for safe SceneScape certificate renewal. NEX-T20003"""

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tools.upgrade.certificates import CERTIFICATE_FILES
from tools.upgrade.certificates import PRIVATE_KEY_FILES
from tools.upgrade.certificates import certificate_status
from tools.upgrade.certificates import replace_trust_set


def test_certificate_status_reports_expiring_and_missing_files(tmp_path):
  certs_dir = tmp_path / "certs"
  certs_dir.mkdir()
  for filename in CERTIFICATE_FILES[:-1]:
    (certs_dir / filename).write_text("certificate", encoding="utf-8")
  for filename in PRIVATE_KEY_FILES:
    (certs_dir / filename).write_text("key", encoding="utf-8")
  (tmp_path / "ca").mkdir()
  (tmp_path / "ca" / "scenescape-ca.key").write_text("ca", encoding="utf-8")

  def fake_run(command, **_kwargs):
    return CompletedProcess(command, 1 if command[-1].endswith("web.crt") else 0)

  report = certificate_status(tmp_path, minimum_valid_days=14, runner=fake_run)

  statuses = {item["name"]: item["status"] for item in report["certificates"]}
  assert report["status"] == "action_required"
  assert statuses["scenescape-web.crt"] == "renewal_required"
  assert statuses["scenescape-mapping.crt"] == "missing"


def test_certificate_status_requires_private_keys(tmp_path):
  certs_dir = tmp_path / "certs"
  certs_dir.mkdir()
  for filename in CERTIFICATE_FILES:
    (certs_dir / filename).write_text("certificate", encoding="utf-8")
  (tmp_path / "ca").mkdir()
  (tmp_path / "ca" / "scenescape-ca.key").write_text("ca", encoding="utf-8")

  def fake_run(command, **_kwargs):
    return CompletedProcess(command, 0)

  report = certificate_status(tmp_path, runner=fake_run)

  statuses = {item["name"]: item["status"] for item in report["certificates"]}
  assert report["status"] == "action_required"
  assert statuses["scenescape-web.key"] == "missing"
  assert statuses["ca/scenescape-ca.key"] == "valid"


def test_replace_trust_set_preserves_non_tls_secrets(tmp_path):
  secrets_dir = tmp_path / "secrets"
  staged_dir = tmp_path / "staged"
  backup_dir = tmp_path / "backup"
  for root, value in ((secrets_dir, "old"), (staged_dir, "new")):
    (root / "certs").mkdir(parents=True)
    (root / "ca").mkdir()
    (root / "certs" / "certificate").write_text(value, encoding="utf-8")
    (root / "ca" / "key").write_text(value, encoding="utf-8")
  (secrets_dir / "controller.auth").write_text("unchanged", encoding="utf-8")
  (secrets_dir / "django").mkdir()
  (secrets_dir / "django" / "secrets.py").write_text("unchanged", encoding="utf-8")

  replace_trust_set(secrets_dir, staged_dir, backup_dir)

  assert (secrets_dir / "certs" / "certificate").read_text() == "new"
  assert (backup_dir / "certs" / "certificate").read_text() == "old"
  assert (secrets_dir / "controller.auth").read_text() == "unchanged"
  assert (secrets_dir / "django" / "secrets.py").read_text() == "unchanged"


def test_replace_trust_set_rolls_back_if_installation_fails(tmp_path):
  secrets_dir = tmp_path / "secrets"
  staged_dir = tmp_path / "staged"
  for name in ("certs", "ca"):
    (secrets_dir / name).mkdir(parents=True)
    (secrets_dir / name / "value").write_text("old", encoding="utf-8")
  (staged_dir / "certs").mkdir(parents=True)
  (staged_dir / "certs" / "value").write_text("new", encoding="utf-8")

  with pytest.raises(FileNotFoundError):
    replace_trust_set(secrets_dir, staged_dir, tmp_path / "backup")

  assert (secrets_dir / "certs" / "value").read_text() == "old"
  assert (secrets_dir / "ca" / "value").read_text() == "old"


def test_certificate_status_rejects_negative_threshold(tmp_path):
  with pytest.raises(ValueError, match="cannot be negative"):
    certificate_status(tmp_path, minimum_valid_days=-1)
