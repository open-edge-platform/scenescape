#!/usr/bin/env python3

"""
Mesh and Point Cloud Utilities
Utilities for converting between meshes and point clouds for 3D reconstruction models.
"""

from typing import Dict, Any, Optional

import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from sklearn.cluster import DBSCAN

from scene_common import log

def create_pointcloud_from_mesh(predictions: Dict[str, Any]) -> 'trimesh.Scene':
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


def create_mesh_from_pointcloud(points: np.ndarray, colors: Optional[np.ndarray] = None,
                               method: str = "alpha_shape") -> 'trimesh.Trimesh':
    """
    Create a watertight mesh from a point cloud using various reconstruction methods.

    Args:
        points: Point cloud coordinates (N, 3)
        colors: Point colors (N, 3), optional
        method: Reconstruction method ('alpha_shape', 'convex_hull', 'poisson')

    Returns:
        trimesh.Trimesh: Reconstructed watertight mesh

    Raises:
        RuntimeError: If mesh reconstruction libraries not available
        ValueError: If insufficient valid points for reconstruction
    """

    # Remove invalid points (NaN, infinity)
    valid_mask = np.isfinite(points).all(axis=1)
    points = points[valid_mask]
    if colors is not None:
        colors = colors[valid_mask]

    if len(points) < 4:
        raise ValueError("Not enough valid points for mesh reconstruction")

    # Remove outliers using DBSCAN clustering
    try:
        clustering = DBSCAN(eps=0.1, min_samples=10).fit(points)
        # Keep largest cluster
        labels = clustering.labels_
        if len(np.unique(labels)) > 1:
            largest_cluster = np.argmax(np.bincount(labels[labels >= 0]))
            cluster_mask = labels == largest_cluster
            points = points[cluster_mask]
            if colors is not None:
                colors = colors[cluster_mask]
    except Exception as e:
        log.warn(f"Outlier removal failed: {e}")

    if method == "convex_hull":
        # Simple convex hull - fast but may not capture concave details
        try:
            hull = ConvexHull(points)
            mesh = trimesh.Trimesh(vertices=points, faces=hull.simplices)
        except Exception as e:
            log.warn(f"Convex hull failed: {e}, trying alpha shape")
            method = "alpha_shape"

    if method == "alpha_shape":
        # Alpha shape - better for concave shapes
        try:
            # Use trimesh's alpha shape functionality
            mesh = trimesh.creation.alpha_shape(points, alpha=0.1)
            if not mesh.is_watertight:
                # Try different alpha values
                for alpha in [0.05, 0.2, 0.5]:
                    mesh = trimesh.creation.alpha_shape(points, alpha=alpha)
                    if mesh.is_watertight:
                        break
        except Exception as e:
            log.warn(f"Alpha shape failed: {e}, trying convex hull")
            hull = ConvexHull(points)
            mesh = trimesh.Trimesh(vertices=points, faces=hull.simplices)

    elif method == "poisson":
        # Poisson surface reconstruction - best quality but requires normals
        try:
            # This would require additional dependencies like Open3D
            # For now, fall back to alpha shape
            mesh = trimesh.creation.alpha_shape(points, alpha=0.1)
        except Exception as e:
            log.warn(f"Poisson reconstruction failed: {e}, using alpha shape")
            mesh = trimesh.creation.alpha_shape(points, alpha=0.1)

    # Ensure mesh is watertight
    if not mesh.is_watertight:
        try:
            mesh.fill_holes()
        except:
            pass

    # Apply colors if provided
    if colors is not None and len(colors) == len(mesh.vertices):
        mesh.visual.vertex_colors = colors

    return mesh

def get_mesh_info(scene: 'trimesh.Scene') -> Dict[str, Any]:
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