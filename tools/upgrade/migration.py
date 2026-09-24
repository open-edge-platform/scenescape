# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stateful application-schema migration operations."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

try:
  from .backup import compose_base
  from .backup import verify_backup
except ImportError:
  from backup import compose_base
  from backup import verify_backup


def migration_command(compose_files, profiles, project_name, operation,
                      deployment_root=None):
  """Build a manager command that uses committed Django migrations only."""
  return compose_base(compose_files, profiles, project_name, deployment_root) + [
    "exec", "-T", "web", "/home/scenescape/Scenescape/manage.py", *operation]


def read_applied_migrations(compose_files, profiles, project_name,
                            deployment_root=None, runner=subprocess.run):
  """Read applied manager migrations without changing the database."""
  command = migration_command(compose_files, profiles, project_name, [
    "shell", "-c",
    "import json; from django.db.migrations.recorder import MigrationRecorder; "
    "print(json.dumps(sorted(n for a,n in MigrationRecorder.Migration.objects."
    "filter(app='manager').values_list('app','name'))))",
  ], deployment_root)
  result = runner(command, check=True, capture_output=True, text=True)
  return json.loads(result.stdout.strip().splitlines()[-1])


def migration_plan(transition, applied):
  """Return pending committed migrations for an authorized transition."""
  strategy = transition.get("django_strategy", "committed")
  expected = transition.get("django_migrations", [])
  return {
    "strategy": strategy,
    "expected": expected,
    "applied": [name for name in expected if name in applied],
    "pending": [name for name in expected if name not in applied],
  }


def run_legacy_migrations(compose_files, profiles, project_name,
                          deployment_root, runner=subprocess.run):
  """Run and verify the target release's historical migration workflow."""
  compose = compose_base(
    compose_files, profiles, project_name, deployment_root)
  tools_dir = Path(deployment_root).resolve() / "manager" / "tools"
  runner(compose + [
    "run", "--rm", "--no-deps",
    "--volume", f"{tools_dir}:/workspace/manager/tools:ro",
    "web", "--shell", "webserver", "--dbhost", "pgserver",
    "--dbtype", "postgres", "--dbport", "5432", "--nointerface",
    "bash", "/workspace/manager/tools/migration",
  ], check=True)


def verify_no_model_changes(compose_files, profiles, project_name,
                            deployment_root, runner=subprocess.run):
  """Require the running target model state to match its database schema."""
  runner(migration_command(
    compose_files, profiles, project_name,
    ["makemigrations", "--check", "--dry-run"], deployment_root), check=True)


def prestart_migration_command(compose, operation):
  """Build a manager command without triggering entrypoint migrations."""
  bootstrap = (
    "cp /run/secrets/django/secrets.py "
    "/home/scenescape/SceneScape/manager/secrets.py; "
    "exec /home/scenescape/SceneScape/manage.py \"$@\"")
  return compose + [
    "run", "--rm", "--no-deps", "--entrypoint", "sh", "web",
    "-ec", bootstrap, "manage.py", *operation,
  ]


def fake_initial_migration(compose_files, profiles, project_name,
                           deployment_root, runner=subprocess.run):
  """Validate the legacy schema before recording the committed initial migration."""
  compose = compose_base(
    compose_files, profiles, project_name, deployment_root)
  validate_schema = (
    "from django.apps import apps; from django.db import connection; "
    "tables=set(connection.introspection.table_names()); missing=[]; "
    "[(missing.extend([f'{m._meta.db_table}.{f.column}' for f in m._meta.local_fields "
    "if f.column not in {c.name for c in connection.introspection.get_table_description("
    "connection.cursor(), m._meta.db_table)}]) if m._meta.db_table in tables else "
    "missing.append(m._meta.db_table)) for m in apps.get_app_config('manager').get_models()]; "
    "assert not missing, 'legacy schema does not match initial migration: '+','.join(missing)")
  runner(prestart_migration_command(
    compose, ["shell", "-c", validate_schema]), check=True)
  runner(prestart_migration_command(
    compose, ["migrate", "manager", "0001_initial", "--fake-initial",
              "--noinput"]), check=True)


def prepare_migrations(compose_files, profiles, project_name, transition,
                       deployment_root=None, runner=subprocess.run):
  """Run migration work that must finish before the target web service starts."""
  strategy = transition.get("django_strategy", "committed")
  if strategy == "legacy_runtime":
    run_legacy_migrations(
      compose_files, profiles, project_name, deployment_root, runner=runner)
  elif strategy == "fake_initial":
    fake_initial_migration(
      compose_files, profiles, project_name, deployment_root, runner=runner)


def database_volume(deployment):
  """Return the physical PostgreSQL volume from a deployment inventory."""
  matches = [item["name"] for item in deployment["volumes"]
             if item["logical_name"] == "vol-db"]
  if len(matches) != 1:
    raise ValueError("expected exactly one vol-db persistent volume")
  return matches[0]


def upgrade_postgres_engine(source_deployment, target_deployment, transition,
                            backup_dir, runner=subprocess.run):
  """Replace an incompatible PostgreSQL volume and restore its verified dump."""
  postgres = transition["postgres"]
  if not postgres.get("engine_upgrade"):
    return
  manifest = verify_backup(backup_dir)
  dumps = [item for item in manifest["artifacts"]
           if item["type"] == "postgres_logical_dump"]
  if len(dumps) != 1:
    raise ValueError("verified backup must contain one PostgreSQL logical dump")
  source_volume = database_volume(source_deployment)
  target_volume = database_volume(target_deployment)
  if source_volume != target_volume:
    raise ValueError("PostgreSQL engine upgrade requires stable volume identity")
  compose = compose_base(
    target_deployment["compose_files"], target_deployment["profiles"],
    target_deployment["project_name"], target_deployment["root"])
  runner(compose + ["down", "--remove-orphans"], check=True)
  runner(["docker", "volume", "rm", source_volume], check=True)
  runner(compose + ["up", "-d", "pgserver"], check=True)
  runner(compose + ["exec", "-T", "pgserver", "sh", "-c",
                    "until pg_isready -U scenescape -d scenescape; do sleep 1; done"],
         check=True)
  dump_path = Path(backup_dir) / dumps[0]["path"]
  with dump_path.open("rb") as dump:
    runner(compose + ["exec", "-T", "pgserver", "psql", "-v",
                      "ON_ERROR_STOP=1", "-U", "scenescape", "-d", "scenescape"],
           check=True, stdin=dump)


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
                     operation_dir, deployment_root=None, runner=subprocess.run):
  """Apply and verify the authorized Django migration strategy."""
  applied = read_applied_migrations(
    compose_files, profiles, project_name, deployment_root, runner=runner)
  plan = migration_plan(transition, applied)
  write_state(operation_dir, transition["source"], transition["target"],
              "planned", plan)
  if plan["strategy"] == "legacy_runtime":
    verify_no_model_changes(
      compose_files, profiles, project_name, deployment_root, runner=runner)
  elif plan["strategy"] == "committed" and plan["pending"]:
    if not plan["expected"]:
      raise ValueError("committed strategy requires authorized target migrations")
    target_migration = plan["expected"][-1]
    runner(migration_command(
      compose_files, profiles, project_name,
      ["migrate", "manager", target_migration, "--noinput"], deployment_root),
           check=True)
  elif plan["strategy"] not in ("committed", "fake_initial"):
    raise ValueError(f"unsupported Django migration strategy: {plan['strategy']}")
  applied = read_applied_migrations(
    compose_files, profiles, project_name, deployment_root, runner=runner)
  verified = migration_plan(transition, applied)
  if verified["strategy"] == "legacy_runtime":
    verified["verified_no_model_changes"] = True
  if verified["pending"]:
    write_state(operation_dir, transition["source"], transition["target"],
                "failed", verified)
    raise ValueError("required Django migrations remain pending")
  return write_state(operation_dir, transition["source"], transition["target"],
                     "verified", verified)
