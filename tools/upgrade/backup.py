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


def compose_base(compose_files, profiles, project_name=None):
  """Return Compose arguments without a terminal operation."""
  command = compose_command(compose_files, profiles)[:-3]
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
  command += f"tar xzpf /backup/{archive.name} -C /volume"
  run_command([
    "docker", "run", "--rm", "-v", f"{volume_name}:/volume",
    "-v", f"{archive.parent}:/backup:ro", ARCHIVE_IMAGE,
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
  compose = compose_base(compose_files, profiles, compose_config.get("name"))
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
    "project_name": compose_config.get("name"),
    "compose_files": [str(Path(path).resolve()) for path in compose_files],
    "profiles": profiles,
    "artifacts": artifacts,
  }
  (output_dir / MANIFEST_NAME).write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return output_dir, manifest


def verify_backup(backup_dir):
  """Validate a backup manifest and every declared artifact checksum."""
  backup_dir = Path(backup_dir).resolve()
  manifest = json.loads((backup_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
  if manifest.get("schema_version") != 1:
    raise ValueError("unsupported backup manifest schema")
  for artifact in manifest.get("artifacts", []):
    path = backup_dir / artifact["path"]
    if not path.is_file():
      raise ValueError(f"backup artifact is missing: {artifact['path']}")
    if sha256(path) != artifact["sha256"]:
      raise ValueError(f"backup checksum mismatch: {artifact['path']}")
  return manifest


def restore_backup(backup_dir, overwrite=False, runner=subprocess.run):
  """Verify and restore all Docker volume artifacts in a backup."""
  backup_dir = Path(backup_dir).resolve()
  manifest = verify_backup(backup_dir)
  restored = []
  for artifact in manifest["artifacts"]:
    if artifact["type"] != "docker_volume":
      continue
    restore_volume(artifact["volume_name"], backup_dir / artifact["path"],
                   overwrite=overwrite, runner=runner)
    restored.append(artifact["volume_name"])
  return restored