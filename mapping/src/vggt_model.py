#!/usr/bin/env python3

"""
VGGT Model Plugin
Implementation of the ReconstructionModel interface for VGGT.
"""

import logging
import os
import sys
from typing import Dict, Any, List
import numpy as np
import torch
from PIL import Image
import torchvision.transforms as tvf

from model_interface import ReconstructionModel
from model_registry import register_model
from mesh_utils import scale_intrinsics_to_original_size

logger = logging.getLogger(__name__)

sys.path.append('/workspace/vggt')

# Import VGGT-specific modules
from vggt.models.vggt import VGGT
from vggt.utils.pose_enc import pose_encoding_to_extri_intri
from vggt.utils.geometry import unproject_depth_map_to_point_map


@register_model("vggt")
class VGGTModel(ReconstructionModel):
    """
    VGGT model plugin for 3D reconstruction.
    
    VGGT (Visual Geometry Grounded Transformer) is optimized for sparse view reconstruction
    and outputs point clouds with depth information.
    """
    
    def __init__(self, device: str = "cpu"):
        super().__init__(
            model_name="vggt",
            description="VGGT - Visual Geometry Grounded Transformer for sparse view reconstruction",
            device=device
        )
        self.model_weights_url = "https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt"
        self.local_weights_path = "/workspace/model_weights/vggt_model.pt"
    
    def load_model(self) -> None:
        """Load VGGT model and weights."""
        try:
            logger.info("Initializing VGGT model...")
            self.model = VGGT()
            
            # Try to load from local cache first, otherwise download
            if os.path.exists(self.local_weights_path):
                logger.info("Loading VGGT weights from local cache...")
                weights = torch.load(self.local_weights_path, map_location=self.device)
            else:
                logger.info("Downloading VGGT weights...")
                weights = torch.hub.load_state_dict_from_url(
                    self.model_weights_url, 
                    map_location=self.device
                )
            
            self.model.load_state_dict(weights)
            self.model.eval()
            self.model = self.model.to(self.device)
            self.is_loaded = True
            logger.info("VGGT model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load VGGT model: {e}")
            raise RuntimeError(f"VGGT model loading failed: {e}")
    
    def run_inference(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run VGGT inference on input images.
        
        Note: VGGT outputs extrinsics (world-to-camera), but we convert them to 
        camera poses (camera-to-world) for API consistency.
        
        Args:
            images: List of image dictionaries with 'data' field containing base64 images
        
        Returns:
            Dictionary containing predictions, camera poses, and intrinsics
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        self.validate_images(images)
        
        try:
            # Decode images and get original sizes
            pil_images = []
            original_sizes = []
            
            for img_data in images:
                img_array = self.decode_base64_image(img_data["data"])
                pil_image = Image.fromarray(img_array)
                pil_images.append(pil_image)
                original_sizes.append((pil_image.size[0], pil_image.size[1]))  # (width, height)
            
            # Preprocess images using VGGT's logic
            images_tensor, model_size = self._preprocess_images(pil_images)
            
            # Run inference
            logger.info(f"Running VGGT inference on device: {self.device}")
            predictions = self._run_model_inference(images_tensor)
            
            # Process outputs
            result = self._process_outputs(predictions, original_sizes, model_size)
            
            return result
            
        except Exception as e:
            logger.error(f"VGGT inference failed: {e}")
            raise RuntimeError(f"VGGT inference failed: {e}")
    
    def get_supported_outputs(self) -> List[str]:
        """Get supported output formats."""
        return ["pointcloud", "mesh"]
    
    def get_native_output(self) -> str:
        """Get native output format."""
        return "pointcloud"
    def create_output(self, result: Dict[str, Any], output_format: str = None, voxel_size: float = 0.01, floor_margin: float = 0.02) -> 'trimesh.Scene':
        """
        Create 3D output scene from VGGT results.
        Supports 'pointcloud' and 'mesh' output modes.
        Single Poisson reconstruction from combined point cloud to avoid stitched floor.
        Optional voxel downsampling helps clean noisy point clouds.
        Floor flattening added to smooth floor plane.
        """

        import tempfile
        import numpy as np
        import open3d as o3d
        import trimesh
        from plyfile import PlyData, PlyElement
        from scene_common.mesh_util import extractMeshFromPointCloud
        import logging
        import shutil
        from visual_util import predictions_to_glb

        logger = logging.getLogger(__name__)

        if output_format is None:
            output_format = self.get_native_output()

        if output_format not in self.get_supported_outputs():
            raise ValueError(
                f"Output format '{output_format}' not supported. Supported formats: {self.get_supported_outputs()}"
            )

        predictions = result["predictions"]
        logger.info("Creating 3D output scene...")
        logger.info(f"Available prediction keys: {list(predictions.keys())}")

        if output_format == "mesh":
            try:
                world_points = predictions.get("world_points_from_depth")
                images = predictions.get("images", predictions.get("image", None))
                extrinsics = predictions.get("camera_extrinsics", predictions.get("extrinsic", None))

                if world_points is None:
                    world_points = predictions.get("world_points")

                if world_points is not None:
                    transformed_points = []
                    transformed_colors = []

                    # Check if points are already in world coordinates
                    already_world = "world_points_from_depth" in predictions
                    logger.info(f"Already in world coordinates: {already_world}")

                    for i in range(world_points.shape[0]):
                        pts = world_points[i].reshape(-1, 3)

                        # Only apply extrinsics if points are local (not already world)
                        if not already_world and extrinsics is not None:
                            ones = np.ones((pts.shape[0], 1))
                            pts_h = np.concatenate([pts, ones], axis=1)
                            world_pts = (extrinsics[i] @ pts_h.T).T[:, :3]
                        else:
                            world_pts = pts

                        transformed_points.append(world_pts)

                        # Handle image colors if available
                        if images is not None:
                            img = images[i]
                            # Ensure channel order is (H, W, 3)
                            if img.shape[0] == 3:
                                img = np.moveaxis(img, 0, -1)
                            colors = img.reshape(-1, 3)
                            if colors.max() > 1.0:
                                colors = colors / 255.0
                            transformed_colors.append(colors)

                    # Combine all camera points
                    points_flat = np.concatenate(transformed_points, axis=0)
                    colors_flat = np.concatenate(transformed_colors, axis=0) if transformed_colors else None

                    # Floor flattening (optional)
                    z_min = points_flat[:, 2].min()
                    floor_idx = points_flat[:, 2] <= z_min + floor_margin
                    points_flat[floor_idx, 2] = z_min

                    # Create point cloud
                    pcd = o3d.geometry.PointCloud()
                    pcd.points = o3d.utility.Vector3dVector(points_flat)
                    if colors_flat is not None:
                        pcd.colors = o3d.utility.Vector3dVector(colors_flat)

                    # Downsample to clean noise
                    pcd_down = pcd.voxel_down_sample(voxel_size=voxel_size)
                    down_pts = np.asarray(pcd_down.points)
                    down_colors = np.asarray(pcd_down.colors) if pcd_down.has_colors() else None

                    # Run Poisson reconstruction
                    mesh = extractMeshFromPointCloud(down_pts, colors=down_colors, voxel_size=voxel_size, depth=16)
                    scene = trimesh.Scene([mesh])
                    logger.info(f"Watertight mesh created: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
                    return scene

                else:
                    logger.warning("No world_points found, falling back to original VGGT export")

            except Exception as e:
                logger.warning(f"Mesh reconstruction failed: {e}, using original VGGT export")

        logger.info("Using VGGT point cloud export as fallback")
        temp_dir = tempfile.mkdtemp(prefix="vggt_glb_")
        try:
            glb_scene = predictions_to_glb(
                predictions,
                conf_thres=50.0,
                filter_by_frames="All",
                show_cam=False,
                target_dir=temp_dir
            )
            return glb_scene
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _preprocess_images(self, pil_images: List[Image.Image]) -> tuple:
        """
        Preprocess images using VGGT's logic.
        
        Args:
            pil_images: List of PIL images
        
        Returns:
            Tuple of (processed_tensor, model_size)
        """
        processed_images = []
        target_size = 518
        
        for pil_image in pil_images:
            # Apply VGGT preprocessing (similar to load_and_preprocess_images)
            width, height = pil_image.size
            
            # Set width to target_size, calculate height maintaining aspect ratio
            new_width = target_size
            new_height = round(height * (new_width / width) / 14) * 14  # Divisible by 14
            
            # Resize image
            img_resized = pil_image.resize((new_width, new_height), Image.Resampling.BICUBIC)
            
            # Convert to tensor
            img_tensor = tvf.ToTensor()(img_resized)  # Shape: (3, H, W), values [0, 1]
            
            # Center crop height if larger than target_size
            if new_height > target_size:
                start_y = (new_height - target_size) // 2
                img_tensor = img_tensor[:, start_y:start_y + target_size, :]
            
            processed_images.append(img_tensor)
        
        # Stack all images and move to device
        images_tensor = torch.stack(processed_images).to(self.device)  # Shape: (N, 3, H, W)
        model_size = images_tensor.shape[-2:]  # (height, width)
        
        return images_tensor, model_size
    
    def _run_model_inference(self, images_tensor: torch.Tensor) -> Dict[str, Any]:
        """
        Run the VGGT model inference.
        
        Args:
            images_tensor: Preprocessed images tensor
        
        Returns:
            Raw model predictions
        """
        with torch.no_grad():
            if self.device == "cuda" and torch.cuda.is_available():
                dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
                with torch.cuda.amp.autocast(dtype=dtype):
                    predictions = self.model(images_tensor)
            else:
                predictions = self.model(images_tensor)
        
        return predictions
    
    def _process_outputs(self, predictions: Dict[str, Any], original_sizes: List[tuple], 
                        model_size: tuple) -> Dict[str, Any]:
        """
        Process VGGT outputs into standard format.
        
        Args:
            predictions: Raw model predictions
            original_sizes: List of original image sizes
            model_size: Model input size
        
        Returns:
            Processed results dictionary
        """
        # Convert pose encoding to extrinsic and intrinsic matrices (for model input size)
        extrinsic, intrinsic = pose_encoding_to_extri_intri(
            predictions["pose_enc"], 
            (model_size[0], model_size[1])
        )
        predictions["extrinsic"] = extrinsic
        predictions["intrinsic"] = intrinsic
        
        # Convert tensors to numpy
        for key in predictions.keys():
            if isinstance(predictions[key], torch.Tensor):
                predictions[key] = predictions[key].cpu().numpy().squeeze(0)
        
        # Generate world points from depth map (using model-sized intrinsics)
        depth_map = predictions["depth"]
        world_points = unproject_depth_map_to_point_map(
            depth_map, 
            predictions["extrinsic"], 
            predictions["intrinsic"]
        )
        predictions["world_points_from_depth"] = world_points
        
        # Scale intrinsics back to original image sizes
        model_intrinsics = predictions["intrinsic"]  # (S, 3, 3)
        original_intrinsics = scale_intrinsics_to_original_size(
            model_intrinsics, 
            model_size, 
            original_sizes, 
            preprocessing_mode="crop",  # VGGT default mode
            model_type="vggt"
        )
        
        # Extract camera poses and scaled intrinsics
        camera_poses = []
        intrinsics_list = []
        
        extrinsic_matrices = predictions["extrinsic"]  # Shape: (S, 4, 4) - world-to-camera
        
        for i in range(extrinsic_matrices.shape[0]):
            # VGGT outputs extrinsics (world-to-camera), but we want camera poses (camera-to-world)
            # Convert by taking the inverse of the extrinsic matrix
            world_to_camera = extrinsic_matrices[i]  # 4x4 matrix
            
            # Convert 3x4 to 4x4 if needed
            if world_to_camera.shape == (3, 4):
                world_to_camera_4x4 = np.eye(4)
                world_to_camera_4x4[:3, :4] = world_to_camera
                world_to_camera = world_to_camera_4x4
            
            # Invert to get camera-to-world (camera pose)
            camera_to_world = np.linalg.inv(world_to_camera)
            
            intrinsic_matrix = original_intrinsics[i]  # Use scaled intrinsics
            
            # Convert rotation matrix to quaternion
            rotation_matrix = camera_to_world[:3, :3]
            quaternion = self.rotation_matrix_to_quaternion(rotation_matrix)
            
            camera_poses.append({
                "rotation": quaternion.tolist(),  # [w, x, y, z]
                "translation": camera_to_world[:3, 3].tolist()
            })
            intrinsics_list.append(intrinsic_matrix.tolist())
        
        return {
            "predictions": predictions,
            "camera_poses": camera_poses,
            "intrinsics": intrinsics_list
        }