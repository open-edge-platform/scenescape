# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stateful application-schema migration operations."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

try:
  from .backup import compose_base
except ImportError:
  from backup import compose_base


def migration_command(compose_files, profiles, project_name, operation):
  """Build a manager command that uses committed Django migrations only."""
  return compose_base(compose_files, profiles, project_name) + [
    "exec", "-T", "web", "./manage.py", *operation]


def read_applied_migrations(compose_files, profiles, project_name,
                            runner=subprocess.run):
  """Read applied manager migrations without changing the database."""
  command = migration_command(compose_files, profiles, project_name, [
    "shell", "-c",
    "import json; from django.db.migrations.recorder import MigrationRecorder; "
    "print(json.dumps(sorted(n for a,n in MigrationRecorder.Migration.objects."
    "filter(app='manager').values_list('app','name'))))",
  ])
  result = runner(command, check=True, capture_output=True, text=True)
  return json.loads(result.stdout.strip().splitlines()[-1])


def migration_plan(transition, applied):
  """Return pending committed migrations for an authorized transition."""
  if transition["postgres"]["engine_upgrade"]:
    raise ValueError("PostgreSQL engine upgrades are not implemented")
  expected = transition.get("django_migrations", [])
  return {
    "expected": expected,
    "applied": [name for name in expected if name in applied],
    "pending": [name for name in expected if name not in applied],
  }


def write_state(operation_dir, source, target, phase, plan):
  """Persist resumable, non-secret migration state."""
  operation_dir = Path(operation_dir)
  operation_dir.mkdir(parents=True, exist_ok=True)
  state = {
    "schema_version": 1,
    "source_version": source,
    "target_version": target,
    "phase": phase,
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "migration_plan": plan,
  }
  (operation_dir / "migration-state.json").write_text(
    json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return state


def apply_migrations(compose_files, profiles, project_name, transition,
                     operation_dir, runner=subprocess.run):
  """Apply and verify committed Django migrations for one transition."""
  applied = read_applied_migrations(
    compose_files, profiles, project_name, runner=runner)
  plan = migration_plan(transition, applied)
  write_state(operation_dir, transition["source"], transition["target"],
              "planned", plan)
  if plan["pending"]:
    runner(migration_command(compose_files, profiles, project_name,
                             ["migrate", "--noinput"]), check=True)
  applied = read_applied_migrations(
    compose_files, profiles, project_name, runner=runner)
  verified = migration_plan(transition, applied)
  if verified["pending"]:
    write_state(operation_dir, transition["source"], transition["target"],
                "failed", verified)
    raise ValueError("required Django migrations remain pending")
  return write_state(operation_dir, transition["source"], transition["target"],
                     "verified", verified)
