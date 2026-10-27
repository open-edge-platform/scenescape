# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stage an uploaded GLB and render a top-down preview for geospatial alignment."""

import os
import time
import uuid

import numpy as np
from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image

from scene_common import log
from scene_common.glb_top_view import generateOrthoView

from .models import Cam, Scene, SingletonSensor
from .validators import validate_glb

STAGING_SUBDIR = 'glb_staging'
STAGING_TTL_SECONDS = 24 * 3600
MAX_GLB_BYTES = settings.FILE_UPLOAD_MAX_MEMORY_SIZE


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
    if entry.is_file() and entry.stat().st_mtime < cutoff:
      os.remove(entry.path)


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
  with open(os.path.join(staging_dir(), f'{token}.glb'), 'wb') as f:
    for chunk in upload.chunks():
      f.write(chunk)
  return token


def build_preview(token):
  """Render the staged GLB top-down (default alignment) and save it as <token>.png.

  @return  (footprint_m, px_per_m) with footprint_m = {"width": W, "height": H} in metres
  """
  scene = Scene(map=f'{STAGING_SUBDIR}/{token}.glb')
  scene.autoAlignSceneMap()
  img_data, px_per_m = generateOrthoView(scene, scene.map.path)
  Image.fromarray(np.uint8(img_data)).save(os.path.join(staging_dir(), f'{token}.png'), format='PNG')
  # autoAlignSceneMap translates by half the posed size
  return {'width': float(2 * scene.translation_x), 'height': float(2 * scene.translation_y)}, float(px_per_m)


def existing_content(scene):
  """Counts of content whose local frame a new GLB map would change."""
  return {
    'cameras': Cam.objects.filter(scene=scene).count(),
    'regions': scene.regions.count(),
    'sensors': SingletonSensor.objects.filter(scene=scene).count(),
  }
