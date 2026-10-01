# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-method mapping artifacts and depth-capped GLB revisions.

Every scene mesh is a ``SceneMapRevision`` tagged with the method that
produced it (``user`` for direct uploads). ``Scene.map`` mirrors
``scene.default_map_revision``; nothing writes ``Scene.map`` directly.

An artifact zip may carry a standard ``manifest.json`` and a ``mesh.glb``;
everything else in the zip is the method's own business.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from functools import partial
from types import SimpleNamespace
from zipfile import BadZipFile, ZipFile

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.base import ContentFile
from django.db import IntegrityError, OperationalError, connection, transaction

from manager.models import Scene, SceneMapRevision, SceneMappingArtifact, sendUpdateCommand
from scene_common import log

DIGEST_HEADER = "X-Scenescape-Sha256"
METHOD_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_METHOD_FILES = "rtabmap=rtabmap.db,arkit=arworldmap.bin,orbslam3=orbslam3.osa"
RTABMAP_MEMBER = "rtabmap.db"
MANIFEST_MEMBER = "manifest.json"
MESH_MEMBER = "mesh.glb"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_FIDUCIALS = 100
FIDUCIAL_TYPES = ("apriltag", "aruco")
USER_METHOD = SceneMapRevision.USER_METHOD


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
  """How many revisions to keep per method, for artifacts and for GLBs."""
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
                   map_revision_id, activate=False):
  """Insert a new head revision for ``method`` and evict past the depth cap.

  A ``mesh.glb`` member becomes this method's GLB revision when the request
  names no existing ``map_revision``. With ``activate`` that revision also
  becomes the scene default; otherwise it waits to be reviewed.
  """
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
  revision = _map_revision_for_scene(scene, map_revision_id)
  depth = history_depth()
  size = os.path.getsize(zip_path)
  try:
    with transaction.atomic():
      _lock_scene(scene.pk, nowait=True)
      if revision is None and _zip_has_member(zip_path, MESH_MEMBER):
        revision = _revision_from_zip_mesh(scene, method, contributor, manifest, zip_path)
      SceneMappingArtifact.objects.filter(
        scene=scene, method=method, head=True).update(head=False)
      artifact = SceneMappingArtifact(
        id=uuid.uuid4(),
        scene=scene,
        method=method,
        sha256=digest,
        size=size,
        fiducials=fiducials,
        manifest=manifest,
        contributor=(contributor or "")[:200],
        map_revision=revision,
        head=True,
      )
      with open(zip_path, "rb") as handle:
        artifact.bundle.save(f"{artifact.id}.zip", File(handle), save=False)
      artifact.save()
      if activate and revision is not None:
        _activate_locked(scene, revision)
      _evict_artifacts(scene, method, depth)
      _evict_glb_revisions(scene, depth)
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


def _zip_has_member(zip_path, name):
  with ZipFile(zip_path) as archive:
    return name in archive.namelist()


def transform_from_manifest(manifest):
  """Mesh transform declared by a manifest, or the identity."""
  raw = (manifest.get("mesh") or {}).get("transform") or manifest.get("transform") or {}
  if not isinstance(raw, dict):
    raise ValidationError("mesh.transform must be an object")
  out = {
    "translation": _vec(raw.get("translation", [0.0, 0.0, 0.0]), 3, "translation"),
    "rotation": _vec(raw.get("rotation", [0.0, 0.0, 0.0]), 3, "rotation"),
    "scale": _vec(raw.get("scale", [1.0, 1.0, 1.0]), 3, "scale"),
  }
  return out


def _revision_from_zip_mesh(scene, method, contributor, manifest, zip_path):
  """Create a (not yet default) revision from the zip's ``mesh.glb``."""
  from manager.validators import validate_glb
  try:
    transform = transform_from_manifest(manifest)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  with tempfile.NamedTemporaryFile(prefix="mesh-", suffix=".glb", delete=False) as tmp:
    tmp_path = tmp.name
  try:
    with ZipFile(zip_path) as archive, archive.open(MESH_MEMBER) as src, \
        open(tmp_path, "wb") as dst:
      shutil.copyfileobj(src, dst)
    with open(tmp_path, "rb") as handle:
      try:
        validate_glb(handle)
      except ValidationError as exc:
        raise MappingStoreError("; ".join(exc.messages), 400) from exc
    revision = SceneMapRevision(
      scene=scene,
      sha256=sha256_file(tmp_path),
      method=method,
      contributor=(contributor or "")[:200],
      transform=transform,
    )
    with open(tmp_path, "rb") as handle:
      revision.file.save(f"{revision.id}.glb", File(handle), save=False)
    revision.save()
    _save_revision_thumbnail(revision)
    return revision
  finally:
    try:
      os.remove(tmp_path)
    except OSError:
      pass


def scene_transform(scene):
  return {
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


def _save_revision_thumbnail(revision):
  """Top view of this revision in its own transform; failures leave it unset."""
  try:
    import numpy as np
    from PIL import Image
    from scene_common.glb_top_view import generateOrthoView
    t = revision.transform or {}
    rot = t.get("rotation", [0.0, 0.0, 0.0])
    tr = t.get("translation", [0.0, 0.0, 0.0])
    shim = SimpleNamespace(rotation_x=rot[0], rotation_y=rot[1], rotation_z=rot[2],
                           translation_x=tr[0], translation_y=tr[1], translation_z=tr[2])
    img_data, _ = generateOrthoView(shim, revision.file.path)
    img = Image.fromarray(np.uint8(img_data))
    with ContentFile(b"") as imgfile:
      img.save(imgfile, format="PNG")
      revision.thumbnail.save(f"{revision.id}_2d.png", imgfile, save=False)
    SceneMapRevision.objects.filter(pk=revision.pk).update(thumbnail=revision.thumbnail.name)
  except Exception as exc:  # noqa: BLE001 - thumbnail is best effort
    log.warning("Revision thumbnail failed for %s: %s", revision.pk, exc)


def record_glb_revision(scene, source, contributor):
  """A GLB was uploaded straight to ``Scene.map``: record it and make it default."""
  method = source or USER_METHOD
  try:
    validate_slug(method)
  except ValidationError as exc:
    raise MappingStoreError("; ".join(exc.messages), 400) from exc
  depth = history_depth()
  digest = sha256_file(scene.map.path)
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    revision = SceneMapRevision(
      scene=scene,
      sha256=digest,
      method=method,
      contributor=(contributor or "")[:200],
      transform=scene_transform(scene),
    )
    revision.file.name = scene.map.name
    revision.save()
    if scene.thumbnail:
      revision.thumbnail.name = scene.thumbnail.name
      revision.save(update_fields=["thumbnail"])
    Scene.objects.filter(pk=scene.pk).update(default_map_revision=revision)
    scene.default_map_revision = revision
    _evict_glb_revisions(scene, depth)
  return revision


def clear_default_revision(scene):
  """A non-mesh map replaced Scene.map. Keep history, but nothing is default."""
  depth = history_depth()
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    Scene.objects.filter(pk=scene.pk).update(default_map_revision=None)
    scene.default_map_revision = None
    _evict_glb_revisions(scene, depth)


def activate_revision(scene, revision):
  """Make ``revision`` the scene default and mirror it into ``Scene.map``."""
  if revision.scene_id != scene.pk:
    raise MappingStoreError("map_revision is not a GLB revision of this scene", 400)
  if not revision.file or not revision.file.name:
    raise MappingStoreError("map_revision has no GLB file", 409)
  depth = history_depth()
  try:
    with transaction.atomic():
      _lock_scene(scene.pk, nowait=True)
      _activate_locked(scene, revision)
      _evict_glb_revisions(scene, depth)
  except OperationalError as exc:
    raise MappingConflict() from exc
  return revision


def _activate_locked(scene, revision):
  t = revision.transform or {}
  tr = t.get("translation", [0.0, 0.0, 0.0])
  rot = t.get("rotation", [0.0, 0.0, 0.0])
  sc = t.get("scale", [1.0, 1.0, 1.0])
  scene.map.name = revision.file.name
  scene.translation_x, scene.translation_y, scene.translation_z = tr
  scene.rotation_x, scene.rotation_y, scene.rotation_z = rot
  scene.scale_x, scene.scale_y, scene.scale_z = sc
  scene.map_contributor = revision.contributor or scene.map_contributor
  from scene_common.timestamp import get_iso_time
  scene.map_processed = get_iso_time()
  # saveThumbnail() also derives the scene's pixels-per-meter scale.
  scene.saveThumbnail()
  scene.default_map_revision = revision
  Scene.objects.filter(pk=scene.pk).update(
    map=scene.map.name, thumbnail=scene.thumbnail.name, scale=scene.scale,
    translation_x=tr[0], translation_y=tr[1], translation_z=tr[2],
    rotation_x=rot[0], rotation_y=rot[1], rotation_z=rot[2],
    scale_x=sc[0], scale_y=sc[1], scale_z=sc[2],
    map_contributor=scene.map_contributor, map_processed=scene.map_processed,
    default_map_revision=revision,
  )
  if not revision.thumbnail and scene.thumbnail:
    SceneMapRevision.objects.filter(pk=revision.pk).update(thumbnail=scene.thumbnail.name)
  transaction.on_commit(partial(sendUpdateCommand, scene_id=scene.pk))


def delete_revision(scene, revision):
  """Delete one revision and the artifacts that produced it.

  Rejecting a candidate means rejecting that method's result as a whole, so
  the artifact zip goes with the GLB. The default revision cannot be deleted.
  """
  if revision.scene_id != scene.pk:
    raise MappingStoreError("map_revision is not a GLB revision of this scene", 400)
  if scene.default_map_revision_id == revision.pk:
    raise MappingStoreError("Cannot delete the default map revision", 409)
  with transaction.atomic():
    _lock_scene(scene.pk, nowait=False)
    for artifact in SceneMappingArtifact.objects.filter(map_revision=revision):
      if artifact.bundle:
        artifact.bundle.delete(save=False)
      artifact.delete()
    _delete_revision_files(scene, revision)
    revision.delete()


def _delete_revision_files(scene, revision):
  live_name = scene.map.name if scene.map else ""
  shared = SceneMapRevision.objects.filter(
    scene=scene, file=revision.file.name).exclude(pk=revision.pk).exists()
  if revision.file and revision.file.name and revision.file.name != live_name and not shared:
    revision.file.delete(save=False)
  thumb_live = scene.thumbnail.name if scene.thumbnail else ""
  if revision.thumbnail and revision.thumbnail.name and revision.thumbnail.name != thumb_live:
    revision.thumbnail.delete(save=False)


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
  """Keep ``depth`` newest revisions per method, plus the default and any
  revision an artifact still points at."""
  referenced = set(SceneMappingArtifact.objects.filter(
    scene=scene, map_revision__isnull=False).values_list(
      "map_revision_id", flat=True))
  rows = list(SceneMapRevision.objects.filter(
    scene=scene).order_by("-created", "-id"))
  default_id = Scene.objects.filter(pk=scene.pk).values_list(
    "default_map_revision_id", flat=True).first()
  keep = {default_id} | referenced
  per_method = {}
  for row in rows:
    count = per_method.get(row.method, 0)
    if count < depth:
      keep.add(row.id)
      per_method[row.method] = count + 1
  for row in rows:
    if row.id in keep:
      continue
    _delete_revision_files(scene, row)
    row.delete()
