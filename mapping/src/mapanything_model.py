#!/usr/bin/env python3

"""
MapAnything Model Plugin
Implementation of the ReconstructionModel interface for MapAnything.
"""

import logging
import sys
from typing import Dict, Any, List
import numpy as np
import torch
from PIL import Image

from model_interface import ReconstructionModel
from model_registry import register_model
from mesh_utils import scale_intrinsics_to_original_size

logger = logging.getLogger(__name__)

# Add model paths to sys.path
sys.path.append('/workspace/map-anything')

# Import MapAnything-specific modules
from mapanything.models import MapAnything
from mapanything.utils.image import find_closest_aspect_ratio, IMAGE_NORMALIZATION_DICT
from mapanything.utils.geometry import depthmap_to_world_frame
from mapanything.utils.cropping import crop_resize_if_necessary
import torchvision.transforms as tvf


@register_model("mapanything")
class MapAnythingModel(ReconstructionModel):
    """
    MapAnything model plugin for 3D reconstruction.
    
    MapAnything is a metric 3D reconstruction model that outputs meshes
    with accurate scale and camera poses.
    """
    
    def __init__(self, device: str = "cpu"):
        super().__init__(
            model_name="mapanything",
            description="MapAnything - Apache 2.0 licensed model for metric 3D reconstruction",
            device=device
        )
        self.model_checkpoint = "facebook/map-anything-apache"
    
    def load_model(self) -> None:
        """Load MapAnything model and weights."""
        try:
            logger.info(f"Loading MapAnything model from {self.model_checkpoint}...")
            self.model = MapAnything.from_pretrained(self.model_checkpoint).to(self.device)
            self.model.eval()
            self.is_loaded = True
            logger.info("MapAnything model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load MapAnything model: {e}")
            raise RuntimeError(f"MapAnything model loading failed: {e}")
    
    def run_inference(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run MapAnything inference on input images.
        
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
            
            # Process images using MapAnything's preprocessing logic
            views = self._preprocess_images(pil_images)
            
            if not views:
                raise ValueError("No valid images processed")
            
            # Get model input size from processed views
            model_height, model_width = views[0]["img"].shape[-2:]
            model_size = (model_height, model_width)
            
            logger.info(f"Running MapAnything inference on device: {self.device}")
            # Run inference with FP32 model as we use CPU
            outputs = self.model.infer(views, memory_efficient_inference=False, amp_dtype="fp32")
            
            # Process outputs
            result = self._process_outputs(outputs, original_sizes, model_size)
            
            return result
            
        except Exception as e:
            logger.error(f"MapAnything inference failed: {e}")
            raise RuntimeError(f"MapAnything inference failed: {e}")
    
    def get_supported_outputs(self) -> List[str]:
        """Get supported output formats."""
        return ["mesh", "pointcloud"]
    
    def get_native_output(self) -> str:
        """Get native output format."""
        return "mesh"
    
    def _preprocess_images(self, pil_images: List[Image.Image]) -> List[Dict[str, Any]]:
        """
        Preprocess images using MapAnything's logic.
        
        Args:
            pil_images: List of PIL images
        
        Returns:
            List of view dictionaries ready for inference
        """
        # Calculate average aspect ratio (MapAnything uses this)
        aspect_ratios = [img.size[0] / img.size[1] for img in pil_images]
        average_aspect_ratio = sum(aspect_ratios) / len(aspect_ratios)
        
        # Find target resolution using MapAnything's logic
        target_width, target_height = find_closest_aspect_ratio(average_aspect_ratio, 518)
        target_size = (target_width, target_height)
        
        # Get normalization transform
        norm_type = "dinov2"  # MapAnything default
        img_norm = IMAGE_NORMALIZATION_DICT[norm_type]
        ImgNorm = tvf.Compose([
            tvf.ToTensor(), 
            tvf.Normalize(mean=img_norm.mean, std=img_norm.std)
        ])
        
        # Process each image
        views = []
        for i, pil_image in enumerate(pil_images):
            # Apply MapAnything's crop_resize_if_necessary
            processed_img = crop_resize_if_necessary(pil_image, resolution=target_size)[0]
            
            # Normalize and create view dict
            views.append(dict(
                img=ImgNorm(processed_img)[None],
                true_shape=np.int32([processed_img.size[::-1]]),
                idx=i,
                instance=str(i),
                data_norm_type=[norm_type],
            ))
        
        return views
    
    def _process_outputs(self, outputs: List[Dict], original_sizes: List[tuple], 
                        model_size: tuple) -> Dict[str, Any]:
        """
        Process MapAnything outputs into standard format.
        
        Args:
            outputs: Raw model outputs
            original_sizes: List of original image sizes
            model_size: Model input size
        
        Returns:
            Processed results dictionary
        """
        # Process outputs for GLB generation
        world_points_list = []
        images_list = []
        masks_list = []
        camera_poses = []
        model_intrinsics_list = []
        
        for view_idx, pred in enumerate(outputs):
            # Extract data from predictions
            depthmap_torch = pred["depth_z"][0].squeeze(-1)
            intrinsics_torch = pred["intrinsics"][0]
            camera_pose_torch = pred["camera_poses"][0]
            
            # Compute 3D points
            pts3d_computed, valid_mask = depthmap_to_world_frame(
                depthmap_torch, intrinsics_torch, camera_pose_torch
            )
            
            # Convert to numpy
            mask = pred["mask"][0].squeeze(-1).cpu().numpy().astype(bool)
            mask = mask & valid_mask.cpu().numpy()
            pts3d_np = pts3d_computed.cpu().numpy()
            image_np = pred["img_no_norm"][0].cpu().numpy()
            
            # Store for GLB export
            world_points_list.append(pts3d_np)
            images_list.append(image_np)
            masks_list.append(mask)
            
            # Store camera data
            pose_np = camera_pose_torch.cpu().numpy()  # MapAnything outputs camera-to-world poses
            intrinsics_np = intrinsics_torch.cpu().numpy()
            
            # Convert rotation matrix to quaternion
            rotation_matrix = pose_np[:3, :3]
            quaternion = self.rotation_matrix_to_quaternion(rotation_matrix)
            
            camera_poses.append({
                "rotation": quaternion.tolist(),  # [w, x, y, z]
                "translation": pose_np[:3, 3].tolist()
            })
            model_intrinsics_list.append(intrinsics_np)
        
        # Scale intrinsics back to original image sizes  
        model_intrinsics = np.stack(model_intrinsics_list, axis=0)  # (S, 3, 3)
        original_intrinsics = scale_intrinsics_to_original_size(
            model_intrinsics,
            model_size,
            original_sizes,
            model_type="mapanything"
        )
        
        # Convert scaled intrinsics to list format
        intrinsics_list = [K.tolist() for K in original_intrinsics]
        
        # Create predictions dict for GLB export
        predictions = {
            "world_points": np.stack(world_points_list, axis=0),
            "images": np.stack(images_list, axis=0),
            "final_masks": np.stack(masks_list, axis=0),
        }
        
        return {
            "predictions": predictions,
            "camera_poses": camera_poses,
            "intrinsics": intrinsics_list
        }