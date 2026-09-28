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
  from .migration import prepare_migrations, upgrade_postgres_engine
  from .preflight import build_report, classify_volumes, compose_inventory_changes
  from .preflight import find_transition
  from .preflight import git_inventory, load_compatibility, resolve_compose_paths
  from .preflight import service_inventory
except ImportError:
  from backup import compose_base, create_backup, restore_backup, verify_backup
  from migration import apply_migrations
  from migration import prepare_migrations, upgrade_postgres_engine
  from preflight import build_report, classify_volumes, compose_inventory_changes
  from preflight import find_transition
  from preflight import git_inventory, load_compatibility, resolve_compose_paths
  from preflight import service_inventory


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


def plan_upgrade(source, target, manifest_path, source_compose_config,
                 target_compose_config, source_deployment_root,
                 target_deployment_root, source_compose_files,
                 target_compose_files, source_profiles, target_profiles,
                 project_name, runner=subprocess.run):
  """Build the canonical read-only plan for one adjacent transition."""
  source_compose_files = resolve_compose_paths(
    source_compose_files, source_deployment_root)
  target_compose_files = resolve_compose_paths(
    target_compose_files, target_deployment_root)
  transition = find_transition(load_compatibility(manifest_path), source, target)
  report = build_report(
    source, target, transition, target_compose_config, target_deployment_root,
    target_compose_files, target_profiles, project_name, runner=runner)
  target_deployment = report.pop("deployment")
  source_deployment = {
    "type": "compose",
    "root": str(Path(source_deployment_root).resolve()),
    "project_name": project_name or source_compose_config.get("name"),
    "compose_files": [str(path) for path in source_compose_files],
    "profiles": source_profiles,
    "git": git_inventory(source_deployment_root, runner=runner),
    "services": service_inventory(source_compose_config),
    "volumes": classify_volumes(source_compose_config),
  }
  source_unclassified = [
    volume["name"] for volume in source_deployment["volumes"]
    if volume["classification"] == "unclassified"
  ]
  if source_unclassified:
    report["warnings"].append({
      "code": "unclassified_source_volumes",
      "message": "Some source volumes require an explicit backup policy",
      "volumes": source_unclassified,
    })
    if report["status"] == "ready":
      report["status"] = "action_required"
  report["source_deployment"] = source_deployment
  report["target_deployment"] = target_deployment
  report["compose_changes"] = compose_inventory_changes(
    source_compose_config, target_compose_config)
  if any(report["compose_changes"].values()):
    report["warnings"].append({
      "code": "compose_definition_changed",
      "message": "Source and target Compose service or volume definitions differ",
    })
    if report["status"] == "ready":
      report["status"] = "action_required"
  if (report["compose_changes"]["volumes_removed"] or
      report["compose_changes"]["volumes_renamed"]):
    report["blockers"].append({
      "code": "persistent_volume_migration_required",
      "message": "Persistent volume removal or rename requires an explicit migration",
    })
    report["status"] = "unsupported"
  return report


def begin_upgrade(plan, operation_dir, secrets_dir, output_dir,
                  backup=create_backup, verifier=verify_backup):
  """Create and verify the mandatory backup, then pause before cutover."""
  if plan["status"] == "unsupported":
    raise ValueError("cannot apply an unsupported transition")
  source_deployment = plan["source_deployment"]
  volumes = {}
  for item in source_deployment["volumes"]:
    definition = {"name": item["name"]}
    if item["classification"] == "disposable_cache":
      definition["driver_opts"] = {"type": "tmpfs"}
    volumes[item["logical_name"]] = definition
  backup_dir, _manifest = backup(
    {"name": source_deployment["project_name"],
     "volumes": volumes},
    source_deployment["root"],
    [Path(path) for path in source_deployment["compose_files"]],
    source_deployment["profiles"], secrets_dir, output_dir)
  verifier(backup_dir)
  return write_operation_state(operation_dir, {
    "schema_version": 1,
    "source_version": plan["source_version"],
    "target_version": plan["target_version"],
    "source_deployment": source_deployment,
    "target_deployment": plan["target_deployment"],
    "backup_dir": str(backup_dir),
    "phase": "awaiting_database_cutover",
    "status": "action_required",
    "rollback_available": True,
  })



def compose_health(compose, expected_services, runner=subprocess.run):
  """Require every expected Compose service to be running and not unhealthy."""
  if not expected_services:
    raise ValueError("expected Compose services are required for health verification")
  result = runner(compose + ["ps", "--all", "--format", "json"], check=True,
                  capture_output=True, text=True)
  raw = result.stdout.strip()
  if not raw:
    raise ValueError("Compose reported no services")
  try:
    services = json.loads(raw)
    if isinstance(services, dict):
      services = [services]
  except json.JSONDecodeError:
    services = [json.loads(line) for line in raw.splitlines()]
  by_service = {}
  for item in services:
    name = item.get("Service")
    if name:
      by_service[name] = item
  missing = sorted(set(expected_services) - set(by_service))
  if missing:
    raise ValueError(
      f"Compose services are missing from status: {', '.join(missing)}")
  failures = [
    name for name in expected_services
    if by_service[name].get("State") != "running"
    or by_service[name].get("Health") == "unhealthy"
  ]
  if failures:
    raise ValueError(f"Compose services are not healthy: {', '.join(failures)}")
  return services


def expected_service_names(deployment):
  """Return the required service names for a saved deployment inventory."""
  names = [item["name"] for item in deployment.get("services", []) if item.get("name")]
  if not names:
    raise ValueError(
      "deployment inventory is missing services required for health verification")
  return names


def resume_upgrade(operation_dir, manifest_path, image_action="pull",
                   runner=subprocess.run, migrator=apply_migrations,
                   migration_preparer=prepare_migrations,
                   postgres_upgrader=upgrade_postgres_engine):
  """Prepare target images, recreate services, migrate, and verify health."""
  state = read_operation_state(operation_dir)
  if state["phase"] not in ("awaiting_database_cutover", "failed"):
    raise ValueError(f"upgrade cannot resume from phase {state['phase']}")
  transition = find_transition(load_compatibility(manifest_path),
                               state["source_version"], state["target_version"])
  if transition is None:
    raise ValueError("saved transition is no longer authorized")
  deployment = state["target_deployment"]
  source_deployment = state["source_deployment"]
  compose = compose_base(
    deployment["compose_files"], deployment["profiles"],
    deployment["project_name"], deployment["root"])
  expected_services = expected_service_names(deployment)
  try:
    if image_action != "none":
      runner(compose + [image_action], check=True)
    source_compose = compose_base(
      source_deployment["compose_files"], source_deployment["profiles"],
      source_deployment["project_name"], source_deployment["root"])
    runner(source_compose + ["down", "--remove-orphans"], check=True)
    postgres_upgrader(
      source_deployment, deployment, transition, state["backup_dir"], runner=runner)
    if not transition["postgres"]["engine_upgrade"]:
      runner(compose + ["up", "-d", "pgserver"], check=True)
    migration_preparer(
      deployment["compose_files"], deployment["profiles"],
      deployment["project_name"], transition, deployment["root"], runner=runner)
    runner(compose + ["up", "-d", "--force-recreate", "--remove-orphans"],
           check=True)
    migrator(
      deployment["compose_files"], deployment["profiles"],
      deployment["project_name"], transition, operation_dir, deployment["root"],
      runner=runner)
    compose_health(compose, expected_services=expected_services, runner=runner)
  except (OSError, ValueError, subprocess.CalledProcessError):
    write_operation_state(operation_dir, {**state, "phase": "failed", "status": "failed"})
    raise
  return write_operation_state(operation_dir, {
    **state, "phase": "verified", "status": "ready",
  })


def verify_upgrade(operation_dir, manifest_path, runner=subprocess.run,
                   migrator=apply_migrations):
  """Reverify migration state and Compose service health after cutover."""
  state = read_operation_state(operation_dir)
  if state["phase"] != "verified":
    raise ValueError(
      "release-verify requires a post-cutover verified phase; "
      "use release-resume for pending cutover operations")
  transition = find_transition(load_compatibility(manifest_path),
                               state["source_version"], state["target_version"])
  if transition is None:
    raise ValueError("saved transition is no longer authorized")
  deployment = state["target_deployment"]
  migrator(
    deployment["compose_files"], deployment["profiles"],
    deployment["project_name"], transition, operation_dir, deployment["root"],
    runner=runner)
  compose_health(compose_base(
    deployment["compose_files"], deployment["profiles"],
    deployment["project_name"], deployment["root"]),
    expected_services=expected_service_names(deployment), runner=runner)
  return write_operation_state(operation_dir, {
    **state, "phase": "verified", "status": "ready",
  })


def _deployment_stack(deployment):
  if not deployment or not deployment.get("compose_files"):
    return None
  return {
    "compose_files": deployment["compose_files"],
    "profiles": deployment.get("profiles") or [],
    "project_name": deployment.get("project_name"),
    "root": deployment.get("root"),
  }


def rollback_upgrade(operation_dir, overwrite=False, restorer=restore_backup):
  """Restore backed-up data after explicit destructive confirmation."""
  state = read_operation_state(operation_dir)
  if not state.get("rollback_available"):
    raise ValueError("this operation has no verified rollback backup")
  source = state.get("source_deployment", {})
  target = state.get("target_deployment", {})
  stacks = [stack for stack in (_deployment_stack(target), _deployment_stack(source))
            if stack]
  project_name = (target.get("project_name") or source.get("project_name"))
  restored = restorer(
    state["backup_dir"], overwrite=overwrite,
    compose_stacks=stacks, project_name=project_name)
  return write_operation_state(operation_dir, {
    **state, "phase": "data_restored", "status": "action_required",
    "restored_volumes": restored,
    "next_action": "start the source release with its saved deployment configuration",
  })
