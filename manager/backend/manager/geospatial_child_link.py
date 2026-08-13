# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Resolve scene maps to local XYZ and apply geospatial child poses."""

import os

from PIL import Image

from django.db.models import Q
from rest_framework.serializers import ValidationError

from scene_common import log
from scene_common.geospatial_hierarchy import (
    GeospatialHierarchyError,
    compute_child_to_parent_pose,
    local_xyz_corners_from_image_size,
    scene_is_georeferenced,
)
from scene_common.mesh_util import extractMeshFromGLB, getMeshAxisAlignedProjectionToXY
from scene_common.options import EULER, TRANSFORM_SOURCE_GEOSPATIAL

IMAGE_MAP_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
MESH_MAP_EXTENSIONS = {'.glb'}

TRANSFORM_REQUEST_KEYS = {f'transform{i}' for i in range(1, 17)} | {'transform'}


def scene_local_xyz_corners(scene):
  """Local AABB corners on z=0 for an image or GLB scene map.

  Args:
    scene: Django Scene instance.

  Returns:
    numpy array of shape (4, 3).

  Raises:
    GeospatialHierarchyError: Map, scale, or mesh extents are missing/invalid.
  """
  if scene.map is None or not getattr(scene.map, 'name', None):
    raise GeospatialHierarchyError(
        f"Scene '{scene.name}' needs a map image or mesh to compute geospatial linking")
  try:
    map_path = scene.map.path
  except ValueError as exc:
    raise GeospatialHierarchyError(
        f"Scene '{scene.name}' map file is not available") from exc
  if not os.path.isfile(map_path):
    raise GeospatialHierarchyError(
        f"Scene '{scene.name}' map file is not available")

  ext = os.path.splitext(map_path)[1].lower()
  if ext in IMAGE_MAP_EXTENSIONS:
    if scene.scale is None or scene.scale <= 0:
      raise GeospatialHierarchyError(
          f"Scene '{scene.name}' needs a positive scale (pixels per meter)")
    with Image.open(map_path) as image:
      width_px, height_px = image.size
    return local_xyz_corners_from_image_size(width_px, height_px, scene.scale)

  if ext in MESH_MAP_EXTENSIONS:
    rotation = [
        scene.rotation_x or 0.0,
        scene.rotation_y or 0.0,
        scene.rotation_z or 0.0,
    ]
    mesh, _ = extractMeshFromGLB(map_path, rotation=rotation)
    return getMeshAxisAlignedProjectionToXY(mesh)

  raise GeospatialHierarchyError(
      f"Scene '{scene.name}' map type '{ext}' is not supported for geospatial linking")


def scenes_are_georeferenced(parent_scene, child_scene):
  """True when both scenes have geospatial output and four corners."""
  return (
      parent_scene is not None
      and child_scene is not None
      and scene_is_georeferenced(parent_scene.output_lla, parent_scene.map_corners_lla)
      and scene_is_georeferenced(child_scene.output_lla, child_scene.map_corners_lla)
  )


def require_geospatial_scenes(parent_scene, child_scene):
  """Raise a DRF ValidationError when geospatial linking is not possible."""
  if child_scene is None:
    raise ValidationError({
        'child': ['Geospatial transform requires a local child scene.']
    })
  if parent_scene is None:
    raise ValidationError({
        'parent': ['Parent scene is required for geospatial transform.']
    })
  if not scene_is_georeferenced(parent_scene.output_lla, parent_scene.map_corners_lla):
    raise ValidationError({
        'parent': ['Parent scene must have output_lla and map_corners_lla for geospatial linking.']
    })
  if not scene_is_georeferenced(child_scene.output_lla, child_scene.map_corners_lla):
    raise ValidationError({
        'child': ['Child scene must have output_lla and map_corners_lla for geospatial linking.']
    })
  return


def compute_pose_for_scenes(parent_scene, child_scene):
  """Compute Euler child-to-parent pose from two georeferenced scenes."""
  require_geospatial_scenes(parent_scene, child_scene)
  try:
    parent_xyz = scene_local_xyz_corners(parent_scene)
    child_xyz = scene_local_xyz_corners(child_scene)
    return compute_child_to_parent_pose(
        parent_xyz, parent_scene.map_corners_lla,
        child_xyz, child_scene.map_corners_lla)
  except GeospatialHierarchyError as exc:
    raise ValidationError({'transform_source': [str(exc)]}) from exc


def pose_to_child_fields(pose):
  """Map a computed Euler pose to ChildScene transform columns."""
  translation = pose['translation']
  rotation = pose['rotation']
  scale = pose['scale']
  return {
      'transform_type': EULER,
      'transform_source': TRANSFORM_SOURCE_GEOSPATIAL,
      'transform1': translation[0],
      'transform2': translation[1],
      'transform3': translation[2],
      'transform4': rotation[0],
      'transform5': rotation[1],
      'transform6': rotation[2],
      'transform7': scale[0],
      'transform8': scale[1],
      'transform9': scale[2],
  }


def apply_geospatial_pose(link, pose=None):
  """Write a geospatial Euler pose onto a ChildScene row without extra save hooks."""
  from manager.models import ChildScene

  if pose is None:
    pose = compute_pose_for_scenes(link.parent, link.child)
  fields = pose_to_child_fields(pose)
  ChildScene.objects.filter(pk=link.pk).update(**fields)
  for key, value in fields.items():
    setattr(link, key, value)
  return pose


def refresh_geospatial_links_for_scene(scene):
  """Recompute every geospatial ChildScene that references this scene."""
  from manager.models import ChildScene

  if scene is None or scene.pk is None:
    return
  links = ChildScene.objects.filter(
      transform_source=TRANSFORM_SOURCE_GEOSPATIAL
  ).filter(Q(parent=scene) | Q(child=scene)).select_related('parent', 'child')
  for link in links:
    if link.child_type != 'local' or link.child is None:
      continue
    try:
      apply_geospatial_pose(link)
    except (ValidationError, GeospatialHierarchyError) as exc:
      log.warning(
          f"Could not refresh geospatial child link {link.pk} "
          f"after updating scene '{scene.name}': {exc}")
  return


def request_has_explicit_transform(initial_data):
  """True when the client sent transform numbers or a transform object."""
  if not initial_data:
    return False
  return bool(TRANSFORM_REQUEST_KEYS & set(initial_data.keys()))
