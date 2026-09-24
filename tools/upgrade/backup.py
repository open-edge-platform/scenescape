# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Project-aware backup and restore primitives for SceneScape."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

try:
  from .preflight import classify_volumes
  from .preflight import compose_command
except ImportError:
  from preflight import classify_volumes
  from preflight import compose_command


ARCHIVE_IMAGE = "alpine:3.23"
MANIFEST_NAME = "manifest.json"


def sha256(path):
  """Return the SHA-256 checksum for a file."""
  digest = hashlib.sha256()
  with Path(path).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def compose_base(compose_files, profiles, project_name=None, project_directory=None):
  """Return Compose arguments without a terminal operation."""
  command = compose_command(compose_files, profiles, project_directory)[:-3]
  if project_name:
    command[2:2] = ["--project-name", project_name]
  return command


def run_command(command, runner=subprocess.run, **kwargs):
  """Run a checked subprocess command."""
  return runner(command, check=True, **kwargs)


def archive_volume(volume_name, destination, runner=subprocess.run):
  """Create a permission-preserving archive of one Docker volume."""
  destination = Path(destination).resolve()
  destination.parent.mkdir(parents=True, exist_ok=True)
  run_command([
    "docker", "run", "--rm",
    "-v", f"{volume_name}:/source:ro",
    "-v", f"{destination.parent}:/backup",
    ARCHIVE_IMAGE, "tar", "czpf", f"/backup/{destination.name}",
    "-C", "/source", ".",
  ], runner=runner)


def volume_is_empty(volume_name, runner=subprocess.run):
  """Return whether a Docker volume contains no entries."""
  result = runner([
    "docker", "run", "--rm", "-v", f"{volume_name}:/volume:ro",
    ARCHIVE_IMAGE, "sh", "-c", "test -z \"$(find /volume -mindepth 1 -print -quit)\"",
  ], check=False, capture_output=True, text=True)
  return result.returncode == 0


def restore_volume(volume_name, archive, overwrite=False, runner=subprocess.run):
  """Restore one archive into a Docker volume with overwrite protection."""
  run_command(["docker", "volume", "create", volume_name], runner=runner,
              capture_output=True, text=True)
  if not overwrite and not volume_is_empty(volume_name, runner=runner):
    raise ValueError(f"refusing to overwrite non-empty volume {volume_name}")
  archive = Path(archive).resolve()
  command = "rm -rf /volume/* /volume/.[!.]* /volume/..?*; " if overwrite else ""
  command += "tar xzpf /backup/archive.tar.gz -C /volume"
  run_command([
    "docker", "run", "--rm", "-v", f"{volume_name}:/volume",
    "-v", f"{archive}:/backup/archive.tar.gz:ro", ARCHIVE_IMAGE,
    "sh", "-c", command,
  ], runner=runner)


def copy_deployment_files(deployment_root, compose_files, secrets_dir, output_dir):
  """Copy deployment inputs and secrets into the protected backup bundle."""
  config_dir = output_dir / "configuration"
  config_dir.mkdir(parents=True)
  copied = []
  candidates = list(compose_files) + [deployment_root / ".env",
                                     deployment_root / ".scenescape-profile"]
  for source in candidates:
    source = Path(source)
    if source.is_file():
      destination = config_dir / source.name
      shutil.copy2(source, destination)
      copied.append(destination)
  if secrets_dir.is_dir():
    destination = output_dir / "secrets"
    shutil.copytree(secrets_dir, destination, copy_function=shutil.copy2)
    copied.extend(path for path in destination.rglob("*") if path.is_file())
  return copied


def create_backup(compose_config, deployment_root, compose_files, profiles,
                  secrets_dir, output_parent, leave_stopped=False,
                  runner=subprocess.run):
  """Create a logical database dump and cold archives of persistent volumes."""
  operation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  output_dir = Path(output_parent).resolve() / f"scenescape-backup-{operation_id}"
  output_dir.mkdir(parents=True, mode=0o700)
  output_dir.chmod(0o700)
  compose = compose_base(
    compose_files, profiles, compose_config.get("name"), deployment_root)
  logical_dump = output_dir / "scenescape.psql"
  with logical_dump.open("wb") as dump_handle:
    run_command(compose + ["exec", "-T", "pgserver", "pg_dump", "-U",
                           "scenescape", "-d", "scenescape"], runner=runner,
                stdout=dump_handle)
  run_command(compose + ["down", "--remove-orphans"], runner=runner)
  try:
    artifacts = [{"path": logical_dump.name, "type": "postgres_logical_dump"}]
    volumes_dir = output_dir / "volumes"
    volumes_dir.mkdir()
    for volume in classify_volumes(compose_config):
      if volume["classification"] == "disposable_cache":
        continue
      archive = volumes_dir / f"{volume['logical_name']}.tar.gz"
      archive_volume(volume["name"], archive, runner=runner)
      artifacts.append({
        "path": str(archive.relative_to(output_dir)),
        "type": "docker_volume",
        "logical_name": volume["logical_name"],
        "volume_name": volume["name"],
        "classification": volume["classification"],
      })
    copied = copy_deployment_files(
      Path(deployment_root), compose_files, Path(secrets_dir), output_dir)
    artifacts.extend({
      "path": str(path.relative_to(output_dir)), "type": "deployment_file"}
                     for path in copied)
  finally:
    if not leave_stopped:
      run_command(compose + ["up", "-d"], runner=runner)
  for artifact in artifacts:
    artifact["sha256"] = sha256(output_dir / artifact["path"])
  manifest = {
    "schema_version": 1,
    "operation": "scenescape_backup",
    "operation_id": operation_id,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "deployment_root": str(Path(deployment_root).resolve()),
    "project_name": compose_config.get("name"),
    "compose_files": [str(Path(path).resolve()) for path in compose_files],
    "profiles": profiles,
    "artifacts": artifacts,
  }
  (output_dir / MANIFEST_NAME).write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return output_dir, manifest


def artifact_path(backup_dir, relative):
  """Resolve an artifact path and reject traversal outside the backup directory."""
  backup_dir = Path(backup_dir).resolve()
  relative = Path(relative)
  if relative.is_absolute() or ".." in relative.parts:
    raise ValueError(f"backup artifact path escapes backup directory: {relative}")
  path = (backup_dir / relative).resolve()
  try:
    path.relative_to(backup_dir)
  except ValueError as exc:
    raise ValueError(
      f"backup artifact path escapes backup directory: {relative}") from exc
  return path


def verify_backup(backup_dir):
  """Validate a backup manifest and every declared artifact checksum."""
  backup_dir = Path(backup_dir).resolve()
  manifest = json.loads((backup_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
  if manifest.get("schema_version") != 1:
    raise ValueError("unsupported backup manifest schema")
  artifacts = manifest.get("artifacts")
  if not isinstance(artifacts, list) or not artifacts:
    raise ValueError("backup manifest has no artifacts")
  for artifact in artifacts:
    if not isinstance(artifact, dict):
      raise ValueError("backup artifact is structurally invalid")
    if not all(key in artifact for key in ("path", "type", "sha256")):
      raise ValueError("backup artifact is missing required fields")
    if artifact["type"] == "docker_volume" and "volume_name" not in artifact:
      raise ValueError("docker volume artifact is missing volume_name")
    path = artifact_path(backup_dir, artifact["path"])
    if not path.is_file():
      raise ValueError(f"backup artifact is missing: {artifact['path']}")
    if sha256(path) != artifact["sha256"]:
      raise ValueError(f"backup checksum mismatch: {artifact['path']}")
  return manifest


def stop_project_containers(project_name, runner=subprocess.run):
  """Stop every container belonging to a Compose project name."""
  if not project_name:
    raise ValueError("project name is required to stop Compose services before restore")
  result = runner(
    ["docker", "ps", "-aq",
     "--filter", f"label=com.docker.compose.project={project_name}"],
    check=True, capture_output=True, text=True)
  container_ids = result.stdout.split()
  if container_ids:
    run_command(["docker", "stop", "--time", "30", *container_ids], runner=runner)
  return container_ids


def _stack_from_args(compose_files, profiles, project_name, deployment_root):
  if not compose_files:
    return None
  return {
    "compose_files": compose_files,
    "profiles": profiles or [],
    "project_name": project_name,
    "root": deployment_root,
  }


def stop_compose_for_restore(manifest, runner=subprocess.run, compose_files=None,
                             profiles=None, project_name=None, deployment_root=None,
                             compose_stacks=None):
  """Stop every Compose definition that may own the volumes being restored.

  Runs `compose down` for each known source/target stack, then stops any
  remaining containers labeled with the Compose project name so target-only
  services cannot keep volumes open during restore.
  """
  stacks = [dict(stack) for stack in (compose_stacks or [])]
  legacy = _stack_from_args(compose_files, profiles, project_name, deployment_root)
  if legacy:
    stacks.append(legacy)
  if not stacks and manifest.get("compose_files"):
    stacks.append({
      "compose_files": manifest.get("compose_files"),
      "profiles": manifest.get("profiles") or [],
      "project_name": manifest.get("project_name"),
      "root": manifest.get("deployment_root"),
    })
  project = project_name or manifest.get("project_name")
  for stack in stacks:
    project = project or stack.get("project_name")
    stack_files = stack.get("compose_files")
    if not stack_files:
      continue
    compose = compose_base(
      stack_files, stack.get("profiles") or [],
      stack.get("project_name") or project, stack.get("root"))
    run_command(compose + ["down", "--remove-orphans"], runner=runner)
  if not project:
    raise ValueError("project name is required to stop Compose services before restore")
  stop_project_containers(project, runner=runner)
  return project


def restore_backup(backup_dir, overwrite=False, runner=subprocess.run,
                   compose_files=None, profiles=None, project_name=None,
                   deployment_root=None, compose_stacks=None):
  """Verify and restore all Docker volume artifacts in a backup.

  Stops every Compose stack that may be using the volumes first and leaves the
  project stopped so callers can restart the intended release after restore.
  """
  backup_dir = Path(backup_dir).resolve()
  manifest = verify_backup(backup_dir)
  stop_compose_for_restore(
    manifest, runner=runner, compose_files=compose_files, profiles=profiles,
    project_name=project_name, deployment_root=deployment_root,
    compose_stacks=compose_stacks)
  restored = []
  for artifact in manifest["artifacts"]:
    if artifact["type"] != "docker_volume":
      continue
    restore_volume(artifact["volume_name"],
                   artifact_path(backup_dir, artifact["path"]),
                   overwrite=overwrite, runner=runner)
    restored.append(artifact["volume_name"])
  return restored
