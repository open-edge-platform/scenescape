# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for authorized database migrations. NEX-T20002"""

import json

import pytest

from tools.upgrade.migration import migration_plan
from tools.upgrade.migration import write_state
from tools.upgrade.preflight import find_transition
from tools.upgrade.preflight import load_compatibility


TRANSITION = {
  "source": "2026.1.0",
  "target": "2026.2.0",
  "postgres": {"source": "17.6", "target": "17.6", "engine_upgrade": False},
  "django_migrations": ["0002_fields", "0003_cache"],
}


def test_plan_reports_only_missing_committed_migrations():
  plan = migration_plan(TRANSITION, ["0001_initial", "0002_fields"])

  assert plan["applied"] == ["0002_fields"]
  assert plan["pending"] == ["0003_cache"]


def test_plan_rejects_unimplemented_engine_upgrade():
  transition = dict(TRANSITION)
  transition["postgres"] = {"engine_upgrade": True}

  with pytest.raises(ValueError, match="engine upgrades are not implemented"):
    migration_plan(transition, [])


def test_state_is_resumable_and_contains_no_credentials(tmp_path):
  state = write_state(tmp_path, "2026.1.0", "2026.2.0", "planned",
                      migration_plan(TRANSITION, []))
  persisted = json.loads((tmp_path / "migration-state.json").read_text())

  assert persisted == state
  assert persisted["phase"] == "planned"
  assert "password" not in json.dumps(persisted).lower()


def test_repository_manifest_authorizes_only_adjacent_release():
  manifest = load_compatibility(
    "tools/upgrade/compatibility.json")

  assert find_transition(manifest, "2026.1.0", "2026.2.0") is not None
  assert find_transition(manifest, "2026.0.0", "2026.2.0") is None
