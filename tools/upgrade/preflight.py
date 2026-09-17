# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read-only discovery for SceneScape upgrade operations."""

import json
from pathlib import Path
import re
import subprocess


STATUS_EXIT_CODES = {
  "ready": 0,
  "failed": 1,
  "action_required": 2,
  "unsupported": 3,
}
SENSITIVE_KEY_PATTERN = re.compile(
  r"(?:auth|credential|password|private|secret|token)", re.IGNORECASE)
DATA_VOLUME_HINTS = (
  "dataset", "db", "media", "migration", "model", "netvlad", "reid", "video")


def redact(value):
  """Recursively redact values stored under sensitive keys."""
  if isinstance(value, dict):
    return {
      key: "<redacted>" if SENSITIVE_KEY_PATTERN.search(key) else redact(item)
      for key, item in value.items()
    }
  if isinstance(value, list):
    return [redact(item) for item in value]
  return value


def load_compatibility(path):
  """Load and minimally validate the upgrade compatibility manifest."""
  manifest = json.loads(Path(path).read_text(encoding="utf-8"))
  if manifest.get("schema_version") != 1:
    raise ValueError("unsupported compatibility manifest schema")
  if not isinstance(manifest.get("transitions"), list):
    raise ValueError("compatibility manifest transitions must be a list")
  return manifest


def find_transition(manifest, source_version, target_version):
  """Return the explicitly supported adjacent-version transition, if any."""
  for transition in manifest["transitions"]:
    if (transition.get("source") == source_version and
        transition.get("target") == target_version):
      return transition
  return None


def compose_command(compose_files, profiles):
  """Build the read-only Compose resolution command."""
  command = ["docker", "compose"]
  for compose_file in compose_files:
    command.extend(["-f", str(compose_file)])
  for profile in profiles:
    command.extend(["--profile", profile])
  command.extend(["config", "--format", "json"])
  return command


def resolve_compose(compose_files, profiles, project_name=None, runner=subprocess.run):
  """Resolve Compose configuration without changing deployment state."""
  environment = None
  if project_name:
    import os
    environment = os.environ.copy()
    environment["COMPOSE_PROJECT_NAME"] = project_name
  result = runner(
    compose_command(compose_files, profiles), check=True, capture_output=True,
    env=environment, text=True)
  return json.loads(result.stdout)


def classify_volumes(compose_config):
  """Classify resolved volumes as data-bearing or disposable cache volumes."""
  volumes = []
  for logical_name, definition in sorted(compose_config.get("volumes", {}).items()):
    driver_options = definition.get("driver_opts", {})
    is_tmpfs = driver_options.get("type") == "tmpfs"
    is_data = any(hint in logical_name.lower() for hint in DATA_VOLUME_HINTS)
    volumes.append({
      "logical_name": logical_name,
      "name": definition.get("name", logical_name),
      "classification": "disposable_cache" if is_tmpfs else (
        "data" if is_data else "unclassified"),
    })
  return volumes


def service_inventory(compose_config):
  """Return a stable, redacted service and image inventory."""
  return [
    {"name": name, "image": service.get("image")}
    for name, service in sorted(compose_config.get("services", {}).items())
  ]


def git_inventory(deployment_root, runner=subprocess.run):
  """Read the deployment checkout revision and worktree state."""
  revision = runner(
    ["git", "-C", str(deployment_root), "rev-parse", "HEAD"], check=True,
    capture_output=True, text=True).stdout.strip()
  status = runner(
    ["git", "-C", str(deployment_root), "status", "--porcelain"], check=True,
    capture_output=True, text=True).stdout.splitlines()
  return {"revision": revision, "dirty": bool(status), "changed_path_count": len(status)}


def build_report(source_version, target_version, transition, compose_config,
                 deployment_root, compose_files, profiles, project_name=None,
                 runner=subprocess.run):
  """Build the stable preflight output contract."""
  blockers = []
  warnings = []
  if transition is None:
    blockers.append({
      "code": "unsupported_transition",
      "message": f"No adjacent upgrade path from {source_version} to {target_version}",
    })
  git = git_inventory(deployment_root, runner=runner)
  if git["dirty"]:
    warnings.append({
      "code": "dirty_worktree",
      "message": "Deployment checkout contains uncommitted changes",
    })
  volumes = classify_volumes(compose_config)
  unclassified = [volume["name"] for volume in volumes
                  if volume["classification"] == "unclassified"]
  if unclassified:
    warnings.append({
      "code": "unclassified_volumes",
      "message": "Some volumes require an explicit backup policy",
      "volumes": unclassified,
    })
  status = "unsupported" if transition is None else (
    "action_required" if warnings else "ready")
  return redact({
    "schema_version": 1,
    "operation": "upgrade_preflight",
    "status": status,
    "source_version": source_version,
    "target_version": target_version,
    "transition": transition,
    "deployment": {
      "type": "compose",
      "root": str(Path(deployment_root).resolve()),
      "project_name": project_name or compose_config.get("name"),
      "compose_files": [str(path) for path in compose_files],
      "profiles": profiles,
      "git": git,
      "services": service_inventory(compose_config),
      "volumes": volumes,
    },
    "blockers": blockers,
    "warnings": warnings,
  })
