# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-method mapping artifacts and the current mesh from each method.

Each method (``user`` for direct uploads, otherwise the mapping backend)
holds at most one ``SceneSourceMap`` row (its current mesh) and one
``SceneMappingArtifact`` row (its current resume zip). A new upload from a
method replaces the matching row; there is no history. ``Scene.map`` mirrors
``scene.default_source_map`` for meshes recorded here; Generate Mesh on main
still writes ``Scene.map`` directly.

An artifact zip may carry a standard ``manifest.json``; everything else in
the zip is the method's own business.
"""

import hashlib
import json
import os
import re
import uuid
from datetime import timezone
from functools import partial
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone as dj_timezone

from manager.models import Scene, SceneMappingArtifact, SceneSourceMap, sendUpdateCommand
from scene_common.timestamp import get_iso_time

DIGEST_HEADER = "X-Scenescape-Sha256"
METHOD_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# Member a method's zip must contain; unlisted methods are opaque.
METHOD_REQUIRED_FILES = {
  "rtabmap": "rtabmap.db",
  "arkit": "arworldmap.bin",
  "orbslam3": "orbslam3.osa",
}
MANIFEST_MEMBER = "manifest.json"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_FIDUCIALS = 100
FIDUCIAL_TYPES = ("apriltag", "aruco")
USER_METHOD = SceneSourceMap.USER_METHOD


class MappingStoreError(Exception):
  """Request cannot be stored. ``status`` is the HTTP status to return."""

  def __init__(self, message, status):
    super().__init__(message)
    self.status = status


class MappingConflict(MappingStoreError):
  """Another upload for this scene and method is in progress."""

  def __init__(self):
    super().__init__("Concurrent upload for this scene and method", 409)


def validate_slug(value):
  """Accept a method or GLB source slug stored as given."""
  if not isinstance(value, str) or METHOD_RE.fullmatch(value) is None:
    raise ValidationError(
      "Must match [a-z][a-z0-9_-]{0,31}")
  return value


def isoformat_z(value):
  """UTC timestamp matching the scene serializer, or None."""
  if value is None:
    return None
  if dj_timezone.is_naive(value):
    value = dj_timezone.make_aware(value, timezone.utc)
  value = value.astimezone(timezone.utc)
  return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sha256_file(path):
  """Lowercase hex SHA-256 of the file at ``path``."""
  digest = hashlib.sha256()
  with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def parse_fiducials(raw):
  """Validate the optional fiducial list from form data."""
  if raw is None or raw == "":
    return []
  if isinstance(raw, str):
    try:
      raw = json.loads(raw)
    except json.JSONDecodeError as exc:
      raise ValidationError(f"fiducials is not valid JSON: {exc}") from exc
  if not isinstance(raw, list):
    raise ValidationError("fiducials must be a list")
  if len(raw) > MAX_FIDUCIALS:
    raise ValidationError(f"fiducials exceeds {MAX_FIDUCIALS} entries")
  seen = set()
  cleaned = []
  for entry in raw:
    cleaned.append(_one_fiducial(entry, seen))
  return cleaned


def _one_fiducial(entry, seen):
  if not isinstance(entry, dict):
    raise ValidationError("Each fiducial must be an object")
  kind = entry.get("type")
  if kind not in FIDUCIAL_TYPES:
    raise ValidationError("Fiducial type must be apriltag or aruco")
  family = entry.get("family")
  if not isinstance(family, str) or not family.strip():
    raise ValidationError("Fiducial family is required")
  tag_id = entry.get("id")
  if not isinstance(tag_id, str) or not tag_id:
    raise ValidationError("Fiducial id must be a string")
  if kind == "apriltag" and not tag_id.isdecimal():
    raise ValidationError("AprilTag id must be a numeric string")
  key = (kind, family, tag_id)
  if key in seen:
    raise ValidationError("Duplicate fiducial (type, family, id)")
  seen.add(key)
  item = {
    "type": kind,
    "family": family,
    "id": tag_id,
    "size_m": _number(entry.get("size_m"), "size_m", positive=True),
    "t": _vec(entry.get("t"), 3, "t"),
  }
  if "q" in entry and entry["q"] is not None:
    item["q"] = _vec(entry["q"], 4, "q")
  if "observations" in entry and entry["observations"] is not None:
    count = entry["observations"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
      raise ValidationError("Fiducial observations must be a non-negative integer")
    item["observations"] = count
  return item


def _number(value, name, positive=False):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise ValidationError(f"Fiducial {name} must be a number")
  value = float(value)
  if positive and value <= 0:
    raise ValidationError(f"Fiducial {name} must be positive")
  return value


def _vec(value, length, name):
  if not isinstance(value, (list, tuple)) or len(value) != length:
    raise ValidationError(f"Fiducial {name} must have {length} numbers")
  return [_number(item, name) for item in value]


def validate_artifact_zip(path, method):
  """Check the zip, and the required member when this method lists one."""
  required = METHOD_REQUIRED_FILES.get(method)
  try:
    with ZipFile(path, "r") as archive:
      bad_entry = archive.testzip()
      if bad_entry is not None:
        raise ValidationError(f"Corrupt entry in mapping artifact: {bad_entry}")
      if required is None:
        return
      try:
        info = archive.getinfo(required)
      except KeyError as exc:
        raise ValidationError(
          f"Mapping artifact must contain {required}") from exc
      if info.file_size < 1:
        raise ValidationError(f"{required} is empty")
  except ValidationError:
    raise
  except BadZipFile as exc:
    raise ValidationError(f"Invalid zip file: {exc}") from exc


def download_digest(artifact):
  """Stored digest, recomputed only when the file size no longer matches."""
  path = artifact.bundle.path
  try:
    size = os.path.getsize(path)
  except OSError:
    return artifact.sha256
  if size == artifact.size:
    return artifact.sha256
  return sha256_file(path)


def store_artifact(scene, method, zip_path, sha256, fiducials, contributor):
  """Replace ``method``'s current artifact zip. The method's mesh is untouched."""
  try:
    validate_slug(method)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  if not isinstance(sha256, str) or SHA_RE.fullmatch(sha256.lower()) is None:
    raise MappingStoreError("sha256 must be a lowercase hex digest", 400)
  digest = sha256_file(zip_path)
  if digest != sha256.lower():
    raise MappingStoreError("sha256 does not match the uploaded zip", 400)
  try:
    validate_artifact_zip(zip_path, method)
    manifest = read_zip_manifest(zip_path)
    if fiducials is None or fiducials == "":
      fiducials = manifest.get("fiducials")
    fiducials = parse_fiducials(fiducials)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  if not contributor:
    contributor = manifest.get("contributor") or ""
  size = os.path.getsize(zip_path)
  try:
    with transaction.atomic():
      _lock_scene(scene.pk, nowait=True)
      _replace_artifact(scene, method)
      artifact = SceneMappingArtifact(
        id=uuid.uuid4(),
        scene=scene,
        method=method,
        sha256=digest,
        size=size,
        fiducials=fiducials,
        manifest=manifest,
        contributor=(contributor or "")[:200],
      )
      with open(zip_path, "rb") as handle:
        artifact.bundle.save(f"{artifact.id}.zip", File(handle), save=False)
      artifact.save()
  except OperationalError as exc:
    raise MappingConflict() from exc
  except IntegrityError as exc:
    raise MappingConflict() from exc
  return artifact


def read_zip_manifest(zip_path):
  """The standard ``manifest.json`` member as a dict, or {} when absent."""
  try:
    with ZipFile(zip_path) as archive:
      try:
        info = archive.getinfo(MANIFEST_MEMBER)
      except KeyError:
        return {}
      if info.file_size > MAX_MANIFEST_BYTES:
        raise ValidationError(f"{MANIFEST_MEMBER} exceeds {MAX_MANIFEST_BYTES} bytes")
      raw = archive.read(info)
  except BadZipFile as exc:
    raise ValidationError(f"Invalid zip file: {exc}") from exc
  try:
    manifest = json.loads(raw.decode("utf-8"))
  except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise ValidationError(f"{MANIFEST_MEMBER} is not valid JSON: {exc}") from exc
  if not isinstance(manifest, dict):
    raise ValidationError(f"{MANIFEST_MEMBER} must be a JSON object")
  return manifest


def scene_transform(scene):
  return {
    "translation": [
      float(scene.translation_x or 0.0),
      float(scene.translation_y or 0.0),
      float(scene.translation_z or 0.0),
    ],
    "rotation": [
      float(scene.rotation_x or 0.0),
      float(scene.rotation_y or 0.0),
      float(scene.rotation_z or 0.0),
    ],
    "scale": [
      float(scene.scale_x) if scene.scale_x is not None else 1.0,
      float(scene.scale_y) if scene.scale_y is not None else 1.0,
      float(scene.scale_z) if scene.scale_z is not None else 1.0,
    ],
  }


def record_glb_source_map(scene, source, contributor):
  """A GLB was uploaded straight to ``Scene.map``: record it and make it default."""
  method = source or USER_METHOD
  try:
    validate_slug(method)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  digest = sha256_file(scene.map.path)
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    source_map = SceneSourceMap(
      scene=scene,
      sha256=digest,
      method=method,
      contributor=(contributor or "")[:200],
      transform=scene_transform(scene),
    )
    source_map.file.name = scene.map.name
    _replace_source_map(scene, method)
    source_map.save()
    if scene.thumbnail:
      source_map.thumbnail.name = scene.thumbnail.name
      source_map.save(update_fields=["thumbnail"])
    Scene.objects.filter(pk=scene.pk).update(default_source_map=source_map)
    scene.default_source_map = source_map
  return source_map


def clear_default_source_map(scene):
  """A non-mesh map replaced Scene.map; no method is currently active."""
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    Scene.objects.filter(pk=scene.pk).update(default_source_map=None)
    scene.default_source_map = None


def activate_source_map(scene, source_map):
  """Make this source's mesh the scene default and mirror it into ``Scene.map``."""
  if source_map.scene_id != scene.pk:
    raise MappingStoreError("source map does not belong to this scene", 400)
  if not source_map.file or not source_map.file.name:
    raise MappingStoreError("source map has no GLB file", 409)
  try:
    with transaction.atomic():
      _lock_scene(scene.pk, nowait=True)
      _activate_locked(scene, source_map)
  except OperationalError as exc:
    raise MappingConflict() from exc
  return source_map


def _activate_locked(scene, source_map):
  t = source_map.transform or {}
  tr = t.get("translation", [0.0, 0.0, 0.0])
  rot = t.get("rotation", [0.0, 0.0, 0.0])
  sc = t.get("scale", [1.0, 1.0, 1.0])
  scene.map.name = source_map.file.name
  scene.translation_x, scene.translation_y, scene.translation_z = tr
  scene.rotation_x, scene.rotation_y, scene.rotation_z = rot
  scene.scale_x, scene.scale_y, scene.scale_z = sc
  scene.map_contributor = source_map.contributor or scene.map_contributor
  scene.map_processed = get_iso_time()
  # saveThumbnail() also derives the scene's pixels-per-meter scale.
  scene.saveThumbnail()
  scene.default_source_map = source_map
  Scene.objects.filter(pk=scene.pk).update(
    map=scene.map.name, thumbnail=scene.thumbnail.name, scale=scene.scale,
    translation_x=tr[0], translation_y=tr[1], translation_z=tr[2],
    rotation_x=rot[0], rotation_y=rot[1], rotation_z=rot[2],
    scale_x=sc[0], scale_y=sc[1], scale_z=sc[2],
    map_contributor=scene.map_contributor, map_processed=scene.map_processed,
    default_source_map=source_map,
  )
  if not source_map.thumbnail and scene.thumbnail:
    SceneSourceMap.objects.filter(pk=source_map.pk).update(thumbnail=scene.thumbnail.name)
  transaction.on_commit(partial(sendUpdateCommand, scene_id=scene.pk))


def delete_source_map(scene, source_map):
  """Delete one method's mesh and its artifact zip.

  Rejecting a source's result rejects it as a whole, so the artifact zip goes
  with the GLB. The default map cannot be deleted.
  """
  if source_map.scene_id != scene.pk:
    raise MappingStoreError("source map does not belong to this scene", 400)
  if scene.default_source_map_id == source_map.pk:
    raise MappingStoreError("Cannot delete the default map", 409)
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    _replace_artifact(scene, source_map.method)
    _delete_source_map_files(scene, source_map)
    source_map.delete()


def _delete_source_map_files(scene, source_map):
  live_name = scene.map.name if scene.map else ""
  shared = SceneSourceMap.objects.filter(
    scene=scene, file=source_map.file.name).exclude(pk=source_map.pk).exists()
  if source_map.file and source_map.file.name and source_map.file.name != live_name and not shared:
    source_map.file.delete(save=False)
  thumb_live = scene.thumbnail.name if scene.thumbnail else ""
  if source_map.thumbnail and source_map.thumbnail.name and source_map.thumbnail.name != thumb_live:
    source_map.thumbnail.delete(save=False)


def delete_artifact(scene, method):
  """Delete the current ZIP for ``method`` without removing its mesh."""
  validate_slug(method)
  artifact = SceneMappingArtifact.objects.filter(scene=scene, method=method).first()
  if artifact is None:
    return False
  if artifact.bundle:
    artifact.bundle.delete(save=False)
  artifact.delete()
  return True


def source_map_for_method(scene, method):
  """The current mesh row for ``method``, or None."""
  return SceneSourceMap.objects.filter(scene=scene, method=method).first()


def _lock_scene(scene_id, *, nowait):
  if nowait and connection.vendor != "sqlite":
    queryset = Scene.objects.select_for_update(nowait=True)
  else:
    queryset = Scene.objects.select_for_update()
  return queryset.get(pk=scene_id)


def _replace_artifact(scene, method):
  """Drop ``method``'s current zip; its file is deleted after commit."""
  for artifact in SceneMappingArtifact.objects.filter(scene=scene, method=method):
    if artifact.bundle:
      transaction.on_commit(partial(artifact.bundle.storage.delete, artifact.bundle.name))
    artifact.delete()


def _replace_source_map(scene, method):
  """Drop ``method``'s previous mesh row. The caller makes the replacement default."""
  previous = SceneSourceMap.objects.filter(scene=scene, method=method)
  default_id = Scene.objects.filter(pk=scene.pk).values_list(
    "default_source_map_id", flat=True).first()
  was_default = previous.filter(pk=default_id).exists()
  # The old default's file is no longer live once the replacement is activated.
  live_name = "" if was_default else (scene.map.name if scene.map else "")
  for old in previous:
    shared = SceneSourceMap.objects.filter(file=old.file.name).exclude(pk=old.pk).exists()
    if old.file and old.file.name != live_name and not shared:
      transaction.on_commit(partial(old.file.storage.delete, old.file.name))
    live_thumbnail = scene.thumbnail.name if scene.thumbnail else ""
    if old.thumbnail and old.thumbnail.name != live_thumbnail:
      transaction.on_commit(partial(old.thumbnail.storage.delete, old.thumbnail.name))
    old.delete()
