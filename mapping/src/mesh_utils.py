#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Mesh and Point Cloud Utilities
Utilities for converting between meshes and point clouds for 3D reconstruction models.
"""

from typing import Dict, Any

import numpy as np
import trimesh

from scene_common import log

def createPointcloudFromMesh(predictions: Dict[str, Any]) -> 'trimesh.Scene':
  """
  Convert MapAnything mesh predictions to point cloud format.

  Args:
    predictions: MapAnything predictions containing world_points, images, masks

  Returns:
    trimesh.Scene: Scene containing point cloud

  Raises:
    RuntimeError: If mesh reconstruction libraries not available
    ValueError: If predictions structure is invalid
  """

  # Extract data from MapAnything predictions
  world_points = predictions.get("world_points")  # (S, H, W, 3)
  images = predictions.get("images")  # (S, H, W, 3)
  masks = predictions.get("final_masks")  # (S, H, W)

  if world_points is None:
    raise ValueError("No world_points found in MapAnything predictions")

  # Flatten and filter points
  points_flat = world_points.reshape(-1, 3)

  # Apply masks if available
  if masks is not None:
    masks_flat = masks.reshape(-1)
    points_flat = points_flat[masks_flat]

  # Extract colors if available
  colors = None
  if images is not None:
    colors_flat = images.reshape(-1, 3)
    if masks is not None:
      colors_flat = colors_flat[masks_flat]
    # Normalize colors to [0, 1] if needed
    if colors_flat.max() > 1.0:
      colors_flat = colors_flat / 255.0
    colors = colors_flat

  # Remove invalid points
  valid_mask = np.isfinite(points_flat).all(axis=1)
  points_flat = points_flat[valid_mask]
  if colors is not None:
    colors = colors[valid_mask]

  # Create point cloud
  point_cloud = trimesh.PointCloud(vertices=points_flat, colors=colors)

  # Create scene
  scene = trimesh.Scene([point_cloud])

  # Rotate scene by 180 degrees along the world x-axis
  rotation_matrix = trimesh.transformations.rotation_matrix(
    angle=np.pi, direction=[1, 0, 0], point=[0, 0, 0]
  )
  scene.apply_transform(rotation_matrix)

  log.info(f"Point cloud created: {len(points_flat)} points")
  return scene

def getMeshInfo(scene: 'trimesh.Scene') -> Dict[str, Any]:
  """
  Extract information about a mesh or point cloud scene.

  Args:
    scene: Trimesh scene object

  Returns:
    Dict containing scene information
  """
  info = {
    "geometries": len(scene.geometry),
    "total_vertices": 0,
    "total_faces": 0,
    "has_colors": False,
    "is_watertight": False,
    "geometry_types": []
  }

  for geom in scene.geometry.values():
    if hasattr(geom, 'vertices'):
      info["total_vertices"] += len(geom.vertices)

    if hasattr(geom, 'faces'):
      info["total_faces"] += len(geom.faces)
      info["geometry_types"].append("mesh")

      # Check if watertight
      if hasattr(geom, 'is_watertight'):
        info["is_watertight"] = info["is_watertight"] or geom.is_watertight
    else:
      info["geometry_types"].append("pointcloud")

    # Check for colors
    if hasattr(geom, 'visual') and hasattr(geom.visual, 'vertex_colors'):
      info["has_colors"] = True

  return info
