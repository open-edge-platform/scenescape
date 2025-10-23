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

# Add model paths to sys.path
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
    
    def create_output(self, result: Dict[str, Any], output_format: str = None) -> 'trimesh.Scene':
        """
        Create 3D output scene from VGGT results.
        
        Args:
            result: Result dictionary from run_inference containing predictions
            output_format: Desired output format ('pointcloud' or 'mesh'). If None, uses native format.
        
        Returns:
            trimesh.Scene: Processed 3D scene
        """
        if output_format is None:
            output_format = self.get_native_output()
        
        if output_format not in self.get_supported_outputs():
            raise ValueError(f"Output format '{output_format}' not supported. Supported formats: {self.get_supported_outputs()}")
        
        predictions = result["predictions"]
        
        if output_format == "mesh":
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
                    from mesh_utils import create_mesh_from_pointcloud
                    import trimesh
                    mesh = create_mesh_from_pointcloud(
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
        import tempfile
        import shutil
        from vggt.utils.visual_util import predictions_to_glb
        
        temp_dir = tempfile.mkdtemp(prefix="vggt_glb_")
        
        try:
            glb_scene = predictions_to_glb(
                predictions,
                conf_thres=50.0,
                filter_by_frames="All",
                show_cam=False,  # Show cameras in pointcloud mode
                target_dir=temp_dir
            )
            return glb_scene
        finally:
            # Clean up temp directory
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