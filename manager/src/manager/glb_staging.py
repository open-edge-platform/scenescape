# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stage an uploaded GLB and render the top-down previews used for geospatial alignment."""

import os
import shutil
import time
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
import numpy as np
from PIL import Image

from scene_common import log
from scene_common.glb_top_view import generateOrthoView

from .models import Scene, glb_preview_name
from .validators import validate_glb

STAGING_SUBDIR = 'glb_staging'
STAGING_TTL_SECONDS = 24 * 3600
MAX_GLB_BYTES = settings.GLB_UPLOAD_MAX_BYTES
# Uploaded GLBs are Y-up (glTF); the same X rotation as every other GLB map brings them into the Z-up scene frame
ALIGN_ROTATION_X = Scene.DEFAULT_MESH_ROTATION


def staging_dir():
  return os.path.join(settings.MEDIA_ROOT, STAGING_SUBDIR)


class GlbAlignmentError(Exception):
  """Failure with an HTTP status and a client-safe message."""

  def __init__(self, status, message):
    super().__init__(message)
    self.status = status
    self.message = message


def purge_stale_files():
  """Delete staged files older than STAGING_TTL_SECONDS.

  Best effort: runs when a GLB is staged or committed, not on a timer.
  """
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
    raise GlbAlignmentError(413, f'GLB file is too large (limit {MAX_GLB_BYTES / (1024 * 1024):g} MB)')
  try:
    validate_glb(upload)
  except ValidationError as e:
    log.error(f'Rejected GLB upload: {e}')
    raise GlbAlignmentError(400, e.messages[0])
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


def _render_top_view(scene, glb_path, png_path):
  """Render glb_path top-down with the scene's pose, save it as a PNG; returns pixels per metre."""
  img_data, px_per_m = generateOrthoView(scene, glb_path)
  Image.fromarray(np.uint8(img_data)).save(png_path, format='PNG')
  return float(px_per_m)


def build_preview(token):
  """Render the staged GLB top-down (default alignment) and save it as <token>.png.

  @return  (footprint_m, px_per_m) with footprint_m = {"width": W, "height": H} in metres
  """
  scene = Scene(map=f'{STAGING_SUBDIR}/{token}.glb')
  width, height, _ = scene.autoAlignSceneMap(rotation_x=ALIGN_ROTATION_X)
  px_per_m = _render_top_view(scene, scene.map.path, os.path.join(staging_dir(), f'{token}.png'))
  return {'width': float(width), 'height': float(height)}, px_per_m


def glb_preview_path(glb_path):
  """Cache path of the top-view preview of a stored GLB, next to the GLB file."""
  return glb_preview_name(glb_path)


def adopt_staged_preview(scene, token):
  """Cache the staged top view as the GLB's preview: the image depends only on the GLB file."""
  staged_png = os.path.join(staging_dir(), f'{token}.png')
  if os.path.isfile(staged_png):
    shutil.copyfile(staged_png, glb_preview_path(scene.glb_map.path))


def ensure_glb_preview(scene):
  """Render the preview of the stored GLB if it is not cached yet.

  The preview depends only on the GLB file, so the staged top view is normally adopted on
  commit and this only repairs a missing one. Call it outside the write transaction, never
  from the GET read path. A failed render is logged and retried on the next call.
  """
  if not scene.glb_map:
    return
  preview_path = glb_preview_path(scene.glb_map.path)
  if os.path.exists(preview_path):
    return
  try:
    # Alignment rotation only; generateOrthoView does not use translation
    temp_scene = Scene(map=scene.glb_map.path)
    temp_scene.rotation_x = ALIGN_ROTATION_X
    temp_scene.rotation_y = 0.0
    temp_scene.rotation_z = 0.0
    _render_top_view(temp_scene, scene.glb_map.path, preview_path)
  except Exception as e:
    log.warning(f'Failed to generate GLB preview: {e}')
