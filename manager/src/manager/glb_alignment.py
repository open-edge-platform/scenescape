# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stage an uploaded GLB and render a top-down preview for geospatial alignment."""

import math
import os
import time
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
import numpy as np
from PIL import Image

from scene_common import log
from scene_common.earth_lla import localFootprintCornersLLA, footprintAnchorFromCornersLLA
from scene_common.glb_top_view import generateOrthoView

from .models import Cam, Scene, SingletonSensor
from .validators import validate_glb

STAGING_SUBDIR = 'glb_staging'
STAGING_TTL_SECONDS = 24 * 3600
MAX_GLB_BYTES = settings.GLB_UPLOAD_MAX_BYTES
# Staged GLBs are z-up (generated meshes and most exports), so no X rotation is applied
ALIGN_ROTATION_X = 0.0


def staging_dir():
  return os.path.join(settings.MEDIA_ROOT, STAGING_SUBDIR)


class GlbAlignmentError(Exception):
  """Failure with an HTTP status and a client-safe message."""

  def __init__(self, status, message):
    super().__init__(message)
    self.status = status
    self.message = message


def purge_stale_files():
  """Delete staged files older than STAGING_TTL_SECONDS."""
  if not os.path.isdir(staging_dir()):
    return
  cutoff = time.time() - STAGING_TTL_SECONDS
  for entry in os.scandir(staging_dir()):
    try:
      if entry.is_file() and entry.stat().st_mtime < cutoff:
        os.remove(entry.path)
    except FileNotFoundError:
      # Another request removed the file between scandir and stat/remove
      pass


def remove_staged_files(token):
  """Delete the staged GLB and preview PNG of a token, if present."""
  for ext in ('glb', 'png'):
    try:
      os.remove(os.path.join(staging_dir(), f'{token}.{ext}'))
    except FileNotFoundError:
      pass


def stage_glb(upload):
  """Validate an uploaded GLB and store it under a server-generated token.

  @return  token (UUID string)
  """
  purge_stale_files()
  if upload.size > MAX_GLB_BYTES:
    raise GlbAlignmentError(413, 'GLB file is too large')
  try:
    validate_glb(upload)
  except ValidationError as e:
    log.error(f'Rejected GLB upload: {e}')
    raise GlbAlignmentError(400, 'Invalid GLB file')
  token = str(uuid.uuid4())
  os.makedirs(staging_dir(), exist_ok=True)
  try:
    with open(os.path.join(staging_dir(), f'{token}.glb'), 'wb') as f:
      for chunk in upload.chunks():
        f.write(chunk)
  except OSError:
    # The token is never returned, so nothing else would clean up the partial file
    remove_staged_files(token)
    raise
  return token


def build_preview(token):
  """Render the staged GLB top-down (default alignment) and save it as <token>.png.

  @return  (footprint_m, px_per_m) with footprint_m = {"width": W, "height": H} in metres
  """
  scene = Scene(map=f'{STAGING_SUBDIR}/{token}.glb')
  width, height, _ = scene.autoAlignSceneMap(rotation_x=ALIGN_ROTATION_X)
  img_data, px_per_m = generateOrthoView(scene, scene.map.path)
  Image.fromarray(np.uint8(img_data)).save(os.path.join(staging_dir(), f'{token}.png'), format='PNG')
  return {'width': float(width), 'height': float(height)}, float(px_per_m)


def existing_content(scene):
  """Counts of content whose local frame a new GLB map would change."""
  return {
    'cameras': Cam.objects.filter(scene=scene).count(),
    'regions': scene.regions.count(),
    'sensors': SingletonSensor.objects.filter(scene=scene).count(),
  }


def get_geospatial_scene(scene_uid):
  """Get a scene by UUID, validating it is a geospatial_map.

  Raises GlbAlignmentError(404, 'Scene not found') if scene does not exist.
  Raises GlbAlignmentError(400, 'Scene map type must be geospatial_map') if map type is wrong.
  """
  try:
    scene = Scene.objects.get(pk=scene_uid)
  except (Scene.DoesNotExist, ValueError):
    raise GlbAlignmentError(404, 'Scene not found')
  if scene.map_type != 'geospatial_map':
    raise GlbAlignmentError(400, 'Scene map type must be geospatial_map')
  return scene


def staged_glb_path(token):
  """Get the file path for a staged GLB, validating the token format.

  Token must be a valid UUID string; build path only from canonical form.
  Raises GlbAlignmentError(400, 'Invalid token') if token is malformed.
  Raises GlbAlignmentError(404, 'Staged GLB not found or expired') if file does not exist.
  """
  if not isinstance(token, str):
    raise GlbAlignmentError(400, 'Invalid token')
  try:
    canonical = str(uuid.UUID(token))
  except (ValueError, AttributeError):
    raise GlbAlignmentError(400, 'Invalid token')
  path = os.path.join(staging_dir(), f'{canonical}.glb')
  if not os.path.isfile(path):
    raise GlbAlignmentError(404, 'Staged GLB not found or expired')
  return path


def parse_anchor(anchor):
  """Validate an anchor dict; returns (lat, lng, heading_deg normalised to [0, 360))."""
  try:
    lat, lng, heading = (anchor[key] for key in ('lat', 'lng', 'heading_deg'))
  except (TypeError, KeyError):
    raise GlbAlignmentError(400, 'Invalid anchor')
  numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in (lat, lng, heading))
  if not numeric or abs(lat) > 90.0 or abs(lng) > 180.0:
    raise GlbAlignmentError(400, 'Invalid anchor')
  return lat, lng, heading % 360.0


def remove_stored_file(storage, name):
  """Best-effort delete of a file from map storage; failures are ignored."""
  try:
    storage.delete(name)
  except Exception:
    pass


def commit_glb(scene, token, anchor, acknowledged):
  """Make a staged GLB the scene map, with corners computed from the anchor.

  Scene.save() re-aligns the mesh, regenerates the thumbnail and notifies the controller.
  @return  saved_alignment(scene)
  """
  path = staged_glb_path(token)
  lat, lng, heading = parse_anchor(anchor)

  if not isinstance(acknowledged, bool):
    raise GlbAlignmentError(400, 'Invalid acknowledge_frame_change')
  if any(existing_content(scene).values()) and acknowledged is not True:
    raise GlbAlignmentError(
      409,
      'Scene has cameras, regions or sensors that would be moved by the new map frame; '
      'set acknowledge_frame_change to true to continue'
    )

  old_map = scene.map.name if scene.map else ''
  try:
    with transaction.atomic():
      with open(path, 'rb') as f:
        scene.map.save(f'{scene.name}.glb', File(f), save=False)
      width, height, _ = scene.autoAlignSceneMap(rotation_x=ALIGN_ROTATION_X)
      scene.map_corners_lla = localFootprintCornersLLA(lat, lng, heading, width, height).tolist()
      scene.trs_matrix = None
      scene.osm_ways_cache = None
      scene.osm_ways_cache_bbox = None
      scene.save()
  except Exception:
    if scene.map.name != old_map:
      remove_stored_file(scene.map.storage, scene.map.name)
    raise

  remove_staged_files(str(uuid.UUID(token)))
  if old_map and scene.map and old_map != scene.map.name:
    remove_stored_file(scene.map.storage, old_map)

  return saved_alignment(scene)


def saved_alignment(scene):
  """Build alignment response from a scene with a committed geospatial GLB.

  Returns dict with anchor, footprint_m, and preview_url.
  Raises GlbAlignmentError(404, 'Scene map is not an aligned GLB') if not aligned.
  """
  if not scene.map or not scene.map.name.lower().endswith('.glb') or not scene.map_corners_lla:
    raise GlbAlignmentError(404, 'Scene map is not an aligned GLB')
  lat, lng, heading, w, h = footprintAnchorFromCornersLLA(scene.map_corners_lla)
  preview_url = scene.thumbnail.url if scene.thumbnail else None
  return {
    'anchor': {
      'lat': float(lat),
      'lng': float(lng),
      'heading_deg': float(heading),
    },
    'footprint_m': {
      'width': float(w),
      'height': float(h),
    },
    'preview_url': preview_url,
  }
