# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-method mapping artifacts and depth-capped GLB revisions."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import IntegrityError, OperationalError, connection, transaction

from manager.models import Scene, SceneMapRevision, SceneMappingArtifact

DIGEST_HEADER = "X-Scenescape-Sha256"
METHOD_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_METHOD_FILES = "rtabmap=rtabmap.db,arkit=arworldmap.bin,orbslam3=orbslam3.osa"
RTABMAP_MEMBER = "rtabmap.db"
MAX_FIDUCIALS = 100
FIDUCIAL_TYPES = ("apriltag", "aruco")


class MappingStoreError(Exception):
  """Request cannot be stored. ``status`` is the HTTP status to return."""

  def __init__(self, message, status):
    super().__init__(message)
    self.status = status


class MappingConflict(MappingStoreError):
  """Another upload for this scene and method is in progress."""

  def __init__(self):
    super().__init__("Concurrent upload for this scene and method", 409)


def history_depth():
  """How many revisions to keep for one method, and for one scene's GLBs."""
  raw = os.environ.get("MAPPING_HISTORY_DEPTH", "1").strip()
  try:
    depth = int(raw)
  except ValueError as exc:
    raise MappingStoreError(
      "MAPPING_HISTORY_DEPTH must be an integer >= 1", 500) from exc
  if depth < 1:
    raise MappingStoreError("MAPPING_HISTORY_DEPTH must be an integer >= 1", 500)
  return depth


def method_required_file(method):
  """Filename that ``method`` must contain, or None when the method is unlisted.

  ``MAPPING_METHOD_FILES`` is a comma-separated list of ``method=filename``
  pairs. Unset uses the built-in default. An empty value lists nothing.
  """
  raw = os.environ.get("MAPPING_METHOD_FILES")
  if raw is None:
    raw = DEFAULT_METHOD_FILES
  for part in raw.split(","):
    part = part.strip()
    if "=" not in part:
      continue
    name, filename = part.split("=", 1)
    if name.strip() == method:
      filename = filename.strip()
      return filename or None
  return None


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
  from datetime import timezone
  from django.utils import timezone as dj_timezone
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
  """Check the zip, and the configured member when this method lists one."""
  required = method_required_file(method)
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
      if required == RTABMAP_MEMBER:
        _validate_rtabmap_member(archive)
  except ValidationError:
    raise
  except BadZipFile as exc:
    raise ValidationError(f"Invalid zip file: {exc}") from exc


def _validate_rtabmap_member(archive):
  with tempfile.TemporaryDirectory(prefix="mapping_artifact_") as tmp:
    db_path = os.path.join(tmp, RTABMAP_MEMBER)
    with archive.open(RTABMAP_MEMBER) as src, open(db_path, "wb") as dst:
      shutil.copyfileobj(src, dst)
    _validate_rtabmap_database(db_path)


def _validate_rtabmap_database(db_path):
  try:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
      if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValidationError(
          "Mapping artifact RTAB-Map database failed SQLite integrity check")
      nodes = _sqlite_table_count(db, "Node")
      words = _sqlite_table_count(db, "Word")
      features = _sqlite_table_count(db, "Feature")
  except sqlite3.Error as exc:
    raise ValidationError(
      f"Invalid RTAB-Map database in mapping artifact: {exc}") from exc
  if nodes == 0:
    raise ValidationError("Mapping artifact RTAB-Map database contains no nodes")
  if words == 0 and features == 0:
    raise ValidationError(
      "Mapping artifact RTAB-Map database contains no visual words")


def _sqlite_table_count(db, table):
  try:
    return int(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
  except sqlite3.Error:
    return 0


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


def store_artifact(scene, method, zip_path, sha256, fiducials, contributor,
                   map_revision_id):
  """Insert a new head revision for ``method`` and evict past the depth cap."""
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
    fiducials = parse_fiducials(fiducials)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  revision = _map_revision_for_scene(scene, map_revision_id)
  depth = history_depth()
  size = os.path.getsize(zip_path)
  try:
    with transaction.atomic():
      _lock_scene(scene.pk, nowait=True)
      SceneMappingArtifact.objects.filter(
        scene=scene, method=method, head=True).update(head=False)
      artifact = SceneMappingArtifact(
        id=uuid.uuid4(),
        scene=scene,
        method=method,
        sha256=digest,
        size=size,
        fiducials=fiducials,
        contributor=(contributor or "")[:200],
        map_revision=revision,
        head=True,
      )
      with open(zip_path, "rb") as handle:
        artifact.bundle.save(f"{artifact.id}.zip", File(handle), save=False)
      artifact.save()
      _evict_artifacts(scene, method, depth)
      _evict_glb_revisions(scene, depth)
  except OperationalError as exc:
    raise MappingConflict() from exc
  except IntegrityError as exc:
    raise MappingConflict() from exc
  return artifact


def record_glb_revision(scene, source, contributor):
  """Append a GLB revision that shares the scene map file, then evict."""
  if not source:
    source = "upload"
  try:
    validate_slug(source)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  depth = history_depth()
  digest = sha256_file(scene.map.path)
  transform = {
    "translation": [
      scene.translation_x or 0.0,
      scene.translation_y or 0.0,
      scene.translation_z or 0.0,
    ],
    "rotation": [
      scene.rotation_x or 0.0,
      scene.rotation_y or 0.0,
      scene.rotation_z or 0.0,
    ],
    "scale": [
      scene.scale_x if scene.scale_x is not None else 1.0,
      scene.scale_y if scene.scale_y is not None else 1.0,
      scene.scale_z if scene.scale_z is not None else 1.0,
    ],
  }
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    SceneMapRevision.objects.filter(scene=scene, head=True).update(head=False)
    revision = SceneMapRevision(
      scene=scene,
      sha256=digest,
      source=source,
      contributor=(contributor or "")[:200],
      transform=transform,
      head=True,
    )
    revision.file.name = scene.map.name
    revision.save()
    _evict_glb_revisions(scene, depth)
  return revision


def clear_glb_head(scene):
  """A non-mesh map replaced Scene.map. Keep history, but it is not the head."""
  depth = history_depth()
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    SceneMapRevision.objects.filter(scene=scene, head=True).update(head=False)
    _evict_glb_revisions(scene, depth)


def delete_head_artifact(scene, method):
  """Delete the live artifact for ``method``. Older revisions stay."""
  validate_slug(method)
  artifact = SceneMappingArtifact.objects.filter(
    scene=scene, method=method, head=True).first()
  if artifact is None:
    return False
  if artifact.bundle:
    artifact.bundle.delete(save=False)
  artifact.delete()
  return True


def _map_revision_for_scene(scene, map_revision_id):
  if map_revision_id is None:
    return None
  if isinstance(map_revision_id, str) and not map_revision_id.strip():
    raise MappingStoreError(
      "map_revision is not a GLB revision of this scene", 400)
  try:
    return SceneMapRevision.objects.get(pk=map_revision_id, scene=scene)
  except (SceneMapRevision.DoesNotExist, ValueError, ValidationError) as exc:
    raise MappingStoreError(
      "map_revision is not a GLB revision of this scene", 400) from exc


def _lock_scene(scene_id, *, nowait):
  if nowait and connection.vendor != "sqlite":
    queryset = Scene.objects.select_for_update(nowait=True)
  else:
    queryset = Scene.objects.select_for_update()
  return queryset.get(pk=scene_id)


def _evict_artifacts(scene, method, depth):
  rows = list(SceneMappingArtifact.objects.filter(
    scene=scene, method=method).order_by("-created", "-id"))
  keep = set()
  for row in rows:
    if row.head:
      keep.add(row.id)
  for row in rows:
    if len(keep) >= depth:
      break
    keep.add(row.id)
  for row in rows:
    if row.id in keep:
      continue
    if row.bundle:
      row.bundle.delete(save=False)
    row.delete()


def _evict_glb_revisions(scene, depth):
  referenced = set(SceneMappingArtifact.objects.filter(
    scene=scene, map_revision__isnull=False).values_list(
      "map_revision_id", flat=True))
  rows = list(SceneMapRevision.objects.filter(
    scene=scene).order_by("-created", "-id"))
  keep = set()
  for row in rows:
    if row.head:
      keep.add(row.id)
  for row in rows:
    if len(keep) >= depth:
      break
    keep.add(row.id)
  keep.update(row.id for row in rows if row.id in referenced)
  live_name = scene.map.name if scene.map else ""
  for row in rows:
    if row.id in keep:
      continue
    if row.file and row.file.name and row.file.name != live_name:
      row.file.delete(save=False)
    row.delete()
