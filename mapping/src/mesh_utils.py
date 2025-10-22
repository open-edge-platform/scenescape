#!/usr/bin/env python3

"""
Mesh and Point Cloud Utilities
Utilities for converting between meshes and point clouds for 3D reconstruction models.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

import trimesh
from scipy.spatial import ConvexHull
from sklearn.cluster import DBSCAN


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
    
    logger.info(f"Point cloud created: {len(points_flat)} points")
    return scene


def create_watertight_mesh_from_points(points: np.ndarray, colors: Optional[np.ndarray] = None, 
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
        logger.warning(f"Outlier removal failed: {e}")
    
    if method == "convex_hull":
        # Simple convex hull - fast but may not capture concave details
        try:
            hull = ConvexHull(points)
            mesh = trimesh.Trimesh(vertices=points, faces=hull.simplices)
        except Exception as e:
            logger.warning(f"Convex hull failed: {e}, trying alpha shape")
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
            logger.warning(f"Alpha shape failed: {e}, trying convex hull")
            hull = ConvexHull(points)
            mesh = trimesh.Trimesh(vertices=points, faces=hull.simplices)
    
    elif method == "poisson":
        # Poisson surface reconstruction - best quality but requires normals
        try:
            # This would require additional dependencies like Open3D
            # For now, fall back to alpha shape
            mesh = trimesh.creation.alpha_shape(points, alpha=0.1)
        except Exception as e:
            logger.warning(f"Poisson reconstruction failed: {e}, using alpha shape")
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


def create_vggt_mesh(predictions: Dict[str, Any], mesh_type: str = "mesh") -> 'trimesh.Scene':
    """
    Create GLB scene from VGGT predictions with optional mesh reconstruction.
    
    Args:
        predictions: VGGT predictions dictionary
        mesh_type: Output type preference ('mesh', 'pointcloud')
    
    Returns:
        trimesh.Scene: Processed 3D scene
    """
    from visual_util import predictions_to_glb as vggt_predictions_to_glb
    import tempfile
    
    if mesh_type == "mesh":
        try:
            # Extract point cloud and colors from VGGT predictions
            world_points = predictions.get("world_points_from_depth")
            images = predictions.get("images", predictions.get("image", None))
            
            if world_points is not None:
                # Flatten the point cloud (S, H, W, 3) -> (N, 3)
                points_flat = world_points.reshape(-1, 3)
                
                # Extract colors from images if available
                colors = None
                if images is not None:
                    # Match image colors to points (S, H, W, 3) -> (N, 3)
                    colors_flat = images.reshape(-1, 3)
                    # Normalize colors to [0, 1] if needed
                    if colors_flat.max() > 1.0:
                        colors_flat = colors_flat / 255.0
                    colors = colors_flat
                
                logger.info("Creating watertight mesh from VGGT point cloud...")
                mesh = create_watertight_mesh_from_points(
                    points_flat, 
                    colors=colors,
                    method="alpha_shape"
                )
                
                # Create scene with the mesh
                scene = trimesh.Scene([mesh])
                logger.info(f"Watertight mesh created: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
                return scene

            else:
                logger.warning("No world_points found, falling back to original VGGT export")
                
        except Exception as e:
            logger.warning(f"Mesh reconstruction failed: {e}, using original VGGT export")
    
    # Fallback to original VGGT GLB export (point cloud mode)
    logger.info("Using VGGT point cloud export")
    temp_dir = tempfile.mkdtemp(prefix="vggt_glb_")
    
    try:
        glb_scene = vggt_predictions_to_glb(
            predictions,
            conf_thres=50.0,
            filter_by_frames="All",
            show_cam=False,  # Show cameras in pointcloud mode
            target_dir=temp_dir
        )
        return glb_scene
    finally:
        # Clean up temp directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def create_mapanything_output(predictions: Dict[str, Any], mesh_type: str = "mesh") -> 'trimesh.Scene':
    """
    Create GLB scene from MapAnything predictions with optional format conversion.
    
    Args:
        predictions: MapAnything predictions dictionary
        mesh_type: Output type preference ('mesh', 'pointcloud')
    
    Returns:
        trimesh.Scene: Processed 3D scene
    """
    from mapanything.utils.viz import predictions_to_glb
    
    # Handle MapAnything output based on mesh_type preference
    if mesh_type == "pointcloud":
        # Convert MapAnything mesh to point cloud
        logger.info("Converting MapAnything mesh to point cloud format...")
        scene = create_pointcloud_from_mesh(predictions)
        return scene
    else:
        # Use MapAnything's default GLB export (mesh)
        scene = predictions_to_glb(predictions, as_mesh=True)
        return scene

def scale_intrinsics_to_original_size(intrinsics: np.ndarray, model_size: tuple, original_sizes: list, 
                                     preprocessing_mode: str = "crop", model_type: str = "vggt") -> list:
    """
    Scale intrinsics matrices from model input size back to original image dimensions.
    
    Args:
        intrinsics: Numpy array of intrinsics matrices (S, 3, 3) 
        model_size: Tuple of (height, width) that model used
        original_sizes: List of tuples [(orig_width_0, orig_height_0), ...]
        preprocessing_mode: How images were preprocessed ("crop" or "pad")
        model_type: Either "vggt" or "mapanything" to handle different preprocessing
    
    Returns:
        List of scaled intrinsics matrices for original image sizes
    """
    if len(intrinsics.shape) == 2:
        # Single matrix (3, 3) -> (1, 3, 3)
        intrinsics = intrinsics[np.newaxis, ...]
    
    if model_type == "vggt":
        return _scale_intrinsics_vggt(intrinsics, model_size, original_sizes, preprocessing_mode)
    elif model_type == "mapanything":
        return _scale_intrinsics_mapanything(intrinsics, model_size, original_sizes)
    else:
        raise ValueError(f"Unsupported model_type: {model_type}")


def _scale_intrinsics_vggt(intrinsics: np.ndarray, model_size: tuple, original_sizes: list, 
                          preprocessing_mode: str) -> list:
    """Scale intrinsics for VGGT preprocessing (simple resize + crop/pad)"""
    scaled_intrinsics = []
    model_height, model_width = model_size
    target_size = 518  # VGGT target size
    
    for i, (orig_width, orig_height) in enumerate(original_sizes):
        K = intrinsics[i].copy()
        
        if preprocessing_mode == "crop":
            # Original VGGT crop mode: width is set to target_size, height may be cropped
            width_scale = orig_width / target_size
            
            # Calculate what the new height would have been after resize
            new_height_before_crop = round(orig_height * (target_size / orig_width) / 14) * 14
            
            if new_height_before_crop > target_size:
                # Height was cropped - need to account for cropping offset
                height_scale = orig_height / new_height_before_crop
                # Principal point offset due to center cropping
                crop_offset = (new_height_before_crop - target_size) // 2
                K[1, 2] = K[1, 2] * height_scale + crop_offset * height_scale
            else:
                # Height was not cropped
                height_scale = orig_height / new_height_before_crop
                K[1, 2] = K[1, 2] * height_scale
            
            # Scale focal lengths and principal point
            K[0, 0] *= width_scale  # fx
            K[0, 2] *= width_scale  # cx
            K[1, 1] *= height_scale # fy
            
        elif preprocessing_mode == "pad":
            # Pad mode: largest dimension set to target_size, smaller padded
            if orig_width >= orig_height:
                # Width was the larger dimension
                scale = orig_width / target_size
                new_height_before_pad = round(orig_height * (target_size / orig_width) / 14) * 14
                
                # Remove padding offset from principal point
                h_padding = target_size - new_height_before_pad
                pad_top = h_padding // 2
                K[1, 2] = (K[1, 2] - pad_top) * scale
                K[0, 2] *= scale
                
                # Scale focal lengths
                K[0, 0] *= scale
                K[1, 1] *= scale
                
            else:
                # Height was the larger dimension  
                scale = orig_height / target_size
                new_width_before_pad = round(orig_width * (target_size / orig_height) / 14) * 14
                
                # Remove padding offset from principal point
                w_padding = target_size - new_width_before_pad
                pad_left = w_padding // 2
                K[0, 2] = (K[0, 2] - pad_left) * scale
                K[1, 2] *= scale
                
                # Scale focal lengths
                K[0, 0] *= scale
                K[1, 1] *= scale
        
        scaled_intrinsics.append(K)
    
    return scaled_intrinsics


def _scale_intrinsics_mapanything(intrinsics: np.ndarray, model_size: tuple, original_sizes: list) -> list:
    """Scale intrinsics for MapAnything preprocessing (resolution mapping + rescale + crop)"""
    # MapAnything resolution mappings
    RESOLUTION_MAPPINGS = {
        518: {
            1.000: (518, 518),  # 1:1
            1.321: (518, 392),  # 4:3
            1.542: (518, 336),  # 3:2
            1.762: (518, 294),  # 16:9
            2.056: (518, 252),  # 2:1
            3.083: (518, 168),  # 3.2:1
            0.757: (392, 518),  # 3:4
            0.649: (336, 518),  # 2:3
            0.567: (294, 518),  # 9:16
            0.486: (252, 518),  # 1:2
        }
    }
    
    def find_closest_aspect_ratio(aspect_ratio, resolution_set=518):
        """Find closest aspect ratio mapping"""
        aspect_keys = sorted(RESOLUTION_MAPPINGS[resolution_set].keys())
        closest_key = min(aspect_keys, key=lambda x: abs(x - aspect_ratio))
        return RESOLUTION_MAPPINGS[resolution_set][closest_key]
    
    scaled_intrinsics = []
    model_height, model_width = model_size
    
    # Calculate average aspect ratio (MapAnything uses this to determine target size)
    aspect_ratios = [w / h for w, h in original_sizes]
    avg_aspect_ratio = sum(aspect_ratios) / len(aspect_ratios)
    
    # Get the target size that MapAnything would have used
    target_width, target_height = find_closest_aspect_ratio(avg_aspect_ratio)
    
    for i, (orig_width, orig_height) in enumerate(original_sizes):
        K = intrinsics[i].copy()
        
        # MapAnything preprocessing steps (reverse them):
        # 1. Rescale image to target size using Lanczos
        # 2. Crop if necessary to exact target dimensions
        
        # Step 1: Reverse the rescaling
        # Calculate what intermediate size would have been after rescaling
        scale_factor_width = target_width / orig_width
        scale_factor_height = target_height / orig_height
        scale_factor = min(scale_factor_width, scale_factor_height)  # Maintain aspect ratio
        
        intermediate_width = int(orig_width * scale_factor)
        intermediate_height = int(orig_height * scale_factor)
        
        # Step 2: Reverse any cropping that was applied
        # If intermediate size > target size, then cropping was applied
        crop_offset_x = 0
        crop_offset_y = 0
        
        if intermediate_width > target_width:
            crop_offset_x = (intermediate_width - target_width) // 2
        if intermediate_height > target_height:
            crop_offset_y = (intermediate_height - target_height) // 2
        
        # Apply reverse transformations to intrinsics
        # First, undo cropping (add back the crop offset)
        K[0, 2] += crop_offset_x  # cx
        K[1, 2] += crop_offset_y  # cy
        
        # Then, undo scaling (scale back to original)
        inverse_scale = 1.0 / scale_factor
        K[0, 0] *= inverse_scale  # fx
        K[1, 1] *= inverse_scale  # fy
        K[0, 2] *= inverse_scale  # cx
        K[1, 2] *= inverse_scale  # cy
        
        scaled_intrinsics.append(K)
    
    return scaled_intrinsics


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