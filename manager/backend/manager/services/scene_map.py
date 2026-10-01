# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene map upload / align / thumbnail domain helpers.

Callable from Scene.save(), SceneSerializer, and future non-Django hosts
without duplicating GLB/PLY/thumbnail logic in views.
"""

import os
import zipfile

import numpy as np
from django.core.files import File
from django.core.files.base import ContentFile
from PIL import Image

from scene_common import log
from scene_common.glb_top_view import generateOrthoView, getMeshSize
from scene_common.mesh_util import extractMeshFromGLB, extractMeshFromPointCloud

# Matches Scene.DEFAULT_MESH_ROTATION (Y-up → Z-up for uploaded GLBs).
DEFAULT_MESH_ROTATION = 90.0


def auto_align_uploaded_map(scene):
  """Rotate uploaded GLB Y-up → Z-up and translate into the first quadrant.

  No-op when ``scene._from_generate_mesh`` is set (mapping-service meshes are
  already aligned).
  """
  if getattr(scene, "_from_generate_mesh", False):
    return
  if not scene.map:
    return
  if os.path.splitext(scene.map.path)[1].lower() != ".glb":
    return
  scene.rotation_x = DEFAULT_MESH_ROTATION
  scene.rotation_y = 0.0
  scene.rotation_z = 0.0
  mesh, _ = extractMeshFromGLB(
    scene.map.path,
    rotation=np.array([scene.rotation_x, scene.rotation_y, scene.rotation_z]),
  )
  width, height, depth = getMeshSize(mesh)
  scene.translation_x = width / 2
  scene.translation_y = height / 2
  scene.translation_z = depth / 2


def reset_map_pose(scene):
  scene.rotation_x = 0.0
  scene.rotation_y = 0.0
  scene.rotation_z = 0.0
  scene.translation_x = 0.0
  scene.translation_y = 0.0
  scene.translation_z = 0.0


def save_scene_thumbnail(scene):
  """Render ortho PNG onto ``scene.thumbnail`` and set ``scene.scale`` (ppm)."""
  img_data, pixels_per_meter = generateOrthoView(scene, scene.map.path)
  scene.scale = pixels_per_meter
  img = Image.fromarray(np.uint8(img_data))
  with ContentFile(b"") as imgfile:
    img.save(imgfile, format="PNG")
    scene.thumbnail.save(scene.name + "_2d.png", imgfile, save=False)


def map_pose_changed(scene, original_map, originals):
  """True when map file or mesh pose differs from ``originals`` snapshot."""
  return (
    scene.map != original_map
    or originals["rotation_x"] != scene.rotation_x
    or originals["rotation_y"] != scene.rotation_y
    or originals["rotation_z"] != scene.rotation_z
    or originals["translation_x"] != scene.translation_x
    or originals["translation_y"] != scene.translation_y
    or originals["translation_z"] != scene.translation_z
  )


def extract_glb_from_zip(scene, zip_field):
  """Replace ``scene.map`` with ``raw.glb`` from a polycam/map zip upload."""
  try:
    with zipfile.ZipFile(zip_field.path, "r") as zf:
      base_file_name = zf.namelist()[0].split("/")[0]
      glb_content = zf.read(os.path.join(base_file_name, "raw.glb"))
      scene.map.save(f"{scene.name}.glb", ContentFile(glb_content), save=False)
  except KeyError:
    log.info(
      "Using old map file %s as glb not found in zip file %s.",
      scene.map.path if scene.map else None,
      zip_field.name,
    )


def finalize_scene_map(scene, *, original_map, glb_from_zip=None):
  """After the scene row is persisted: unzip / convert / align / thumbnail.

  Mutates ``scene`` in memory. Returns True if the caller should save again.
  """
  if glb_from_zip:
    extract_glb_from_zip(scene, glb_from_zip)
    auto_align_uploaded_map(scene)

  originals = {
    "rotation_x": getattr(scene, "_original_rotation_x", scene.rotation_x),
    "rotation_y": getattr(scene, "_original_rotation_y", scene.rotation_y),
    "rotation_z": getattr(scene, "_original_rotation_z", scene.rotation_z),
    "translation_x": getattr(
      scene, "_original_translation_x", scene.translation_x
    ),
    "translation_y": getattr(
      scene, "_original_translation_y", scene.translation_y
    ),
    "translation_z": getattr(
      scene, "_original_translation_z", scene.translation_z
    ),
  }
  if not (map_pose_changed(scene, original_map, originals) or glb_from_zip):
    return False

  if not scene.map:
    scene.thumbnail = None
    scene.map_processed = None
    return True

  ext = os.path.splitext(scene.map.path)[1].lower()
  if ext == ".ply":
    glb_file = extractMeshFromPointCloud(scene.map.path)
    with open(glb_file, "rb") as f:
      scene.map.save(os.path.basename(glb_file), File(f), save=False)
    save_scene_thumbnail(scene)
  elif ext == ".glb":
    # Generated meshes skip align via _from_generate_mesh inside auto_align.
    if original_map != scene.map:
      auto_align_uploaded_map(scene)
    save_scene_thumbnail(scene)
  else:
    scene.thumbnail = None
    reset_map_pose(scene)
  return True


def apply_map_on_scene_create(scene):
  """Align/thumbnail for a newly bulk-created scene that already has a map.

  Persists pose, scale, and thumbnail in one update (create path previously
  only flushed thumbnail).
  """
  if not scene.map:
    return
  ext = os.path.splitext(scene.map.name)[1].lower()
  if ext == ".ply":
    glb_file = scene.map.path.replace(".ply", ".glb")
    if not os.path.exists(glb_file):
      raise ValueError("Error processing .ply file")
    with open(glb_file, "rb") as f:
      scene.map.save(os.path.basename(glb_file), File(f), save=False)
    ext = ".glb"
  if ext == ".glb":
    # New scenes always align uploaded GLBs (create path never went through
    # Scene.save()'s map-changed check with a prior original).
    auto_align_uploaded_map(scene)
    save_scene_thumbnail(scene)
    from manager.models import Scene

    Scene.objects.filter(pk=scene.pk).update(
      map=scene.map,
      thumbnail=scene.thumbnail,
      scale=scene.scale,
      rotation_x=scene.rotation_x,
      rotation_y=scene.rotation_y,
      rotation_z=scene.rotation_z,
      translation_x=scene.translation_x,
      translation_y=scene.translation_y,
      translation_z=scene.translation_z,
    )
