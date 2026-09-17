# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Resumable orchestration for authorized adjacent-release upgrades."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

try:
  from .backup import compose_base, create_backup, restore_backup, verify_backup
  from .migration import apply_migrations
  from .preflight import build_report, find_transition, load_compatibility
except ImportError:
  from backup import compose_base, create_backup, restore_backup, verify_backup
  from migration import apply_migrations
  from preflight import build_report, find_transition, load_compatibility


STATE_NAME = "upgrade-state.json"
LOG_NAME = "upgrade-events.jsonl"


def write_operation_state(operation_dir, state):
  """Persist operation state and append a redacted phase event."""
  operation_dir = Path(operation_dir)
  operation_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
  operation_dir.chmod(0o700)
  state = {**state, "updated_at": datetime.now(timezone.utc).isoformat()}
  (operation_dir / STATE_NAME).write_text(
    json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  event = {"timestamp": state["updated_at"], "phase": state["phase"],
           "status": state["status"]}
  with (operation_dir / LOG_NAME).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(event, sort_keys=True) + "\n")
  return state


def read_operation_state(operation_dir):
  """Read and validate an existing orchestrator state file."""
  state = json.loads((Path(operation_dir) / STATE_NAME).read_text(encoding="utf-8"))
  if state.get("schema_version") != 1:
    raise ValueError("unsupported upgrade state schema")
  return state


def plan_upgrade(source, target, manifest_path, compose_config, deployment_root,
                 compose_files, profiles, project_name, runner=subprocess.run):
  """Build the canonical read-only plan for one adjacent transition."""
  transition = find_transition(load_compatibility(manifest_path), source, target)
  return build_report(source, target, transition, compose_config, deployment_root,
                      compose_files, profiles, project_name, runner=runner)


def begin_upgrade(plan, operation_dir, secrets_dir, output_dir,
                  backup=create_backup, verifier=verify_backup):
  """Create and verify the mandatory backup, then pause before cutover."""
  if plan["status"] == "unsupported":
    raise ValueError("cannot apply an unsupported transition")
  deployment = plan["deployment"]
  volumes = {}
  for item in deployment["volumes"]:
    definition = {"name": item["name"]}
    if item["classification"] == "disposable_cache":
      definition["driver_opts"] = {"type": "tmpfs"}
    volumes[item["logical_name"]] = definition
  backup_dir, _manifest = backup(
    {"name": deployment["project_name"],
     "volumes": volumes},
    deployment["root"], [Path(path) for path in deployment["compose_files"]],
    deployment["profiles"], secrets_dir, output_dir)
  verifier(backup_dir)
  return write_operation_state(operation_dir, {
    "schema_version": 1,
    "source_version": plan["source_version"],
    "target_version": plan["target_version"],
    "deployment": deployment,
    "backup_dir": str(backup_dir),
    "phase": "awaiting_database_cutover",
    "status": "action_required",
    "rollback_available": True,
  })


def compose_health(compose, runner=subprocess.run):
  """Require every selected Compose service to be running and not unhealthy."""
  result = runner(compose + ["ps", "--format", "json"], check=True,
                  capture_output=True, text=True)
  raw = result.stdout.strip()
  if not raw:
    raise ValueError("Compose reported no running services")
  try:
    services = json.loads(raw)
    if isinstance(services, dict):
      services = [services]
  except json.JSONDecodeError:
    services = [json.loads(line) for line in raw.splitlines()]
  failures = [item.get("Service", item.get("Name", "unknown")) for item in services
              if item.get("State") != "running" or item.get("Health") == "unhealthy"]
  if failures:
    raise ValueError(f"Compose services are not healthy: {', '.join(failures)}")
  return services


def resume_upgrade(operation_dir, manifest_path, image_action="pull",
                   runner=subprocess.run, migrator=apply_migrations):
  """Prepare target images, recreate services, migrate, and verify health."""
  state = read_operation_state(operation_dir)
  if state["phase"] not in ("awaiting_database_cutover", "failed"):
    raise ValueError(f"upgrade cannot resume from phase {state['phase']}")
  transition = find_transition(load_compatibility(manifest_path),
                               state["source_version"], state["target_version"])
  if transition is None:
    raise ValueError("saved transition is no longer authorized")
  deployment = state["deployment"]
  compose = compose_base(deployment["compose_files"], deployment["profiles"],
                         deployment["project_name"])
  try:
    if image_action != "none":
      runner(compose + [image_action], check=True)
    runner(compose + ["up", "-d", "--force-recreate"], check=True)
    migrator(deployment["compose_files"], deployment["profiles"],
             deployment["project_name"], transition, operation_dir, runner=runner)
    compose_health(compose, runner=runner)
  except (OSError, ValueError, subprocess.CalledProcessError):
    write_operation_state(operation_dir, {**state, "phase": "failed", "status": "failed"})
    raise
  return write_operation_state(operation_dir, {
    **state, "phase": "verified", "status": "ready",
  })


def verify_upgrade(operation_dir, manifest_path, runner=subprocess.run,
                   migrator=apply_migrations):
  """Reverify migration state and Compose service health."""
  state = read_operation_state(operation_dir)
  transition = find_transition(load_compatibility(manifest_path),
                               state["source_version"], state["target_version"])
  if transition is None:
    raise ValueError("saved transition is no longer authorized")
  deployment = state["deployment"]
  migrator(deployment["compose_files"], deployment["profiles"],
           deployment["project_name"], transition, operation_dir, runner=runner)
  compose_health(compose_base(deployment["compose_files"], deployment["profiles"],
                              deployment["project_name"]), runner=runner)
  return write_operation_state(operation_dir, {
    **state, "phase": "verified", "status": "ready",
  })


def rollback_upgrade(operation_dir, overwrite=False, restorer=restore_backup):
  """Restore backed-up data after explicit destructive confirmation."""
  state = read_operation_state(operation_dir)
  if not state.get("rollback_available"):
    raise ValueError("this operation has no verified rollback backup")
  restored = restorer(state["backup_dir"], overwrite=overwrite)
  return write_operation_state(operation_dir, {
    **state, "phase": "data_restored", "status": "action_required",
    "restored_volumes": restored,
    "next_action": "start the source release with its saved deployment configuration",
  })