#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MapAnything Model Implementation
Implementation of the ReconstructionModel interface for MapAnything.

This model is instantiated directly by the mapanything-service container.
"""

import base64
import sys
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import torch
from PIL import Image

import traceback

from scene_common import log

from model_interface import ReconstructionModel

# Add model paths to sys.path
sys.path.append('/workspace/map-anything')

# Import MapAnything-specific modules
from mapanything.models import MapAnything
from mapanything.utils.image import find_closest_aspect_ratio, IMAGE_NORMALIZATION_DICT, RESOLUTION_MAPPINGS
from mapanything.utils.geometry import depthmap_to_world_frame
from mapanything.utils.cropping import crop_resize_if_necessary
import torchvision.transforms as tvf


class MapAnythingModel(ReconstructionModel):
  """
  MapAnything model for 3D reconstruction.

  MapAnything is a metric 3D reconstruction model that outputs meshes
  with accurate scale and camera poses.

  This model is used by the mapanything-service container.
  """

  def __init__(self, device: str = "cpu"):
    super().__init__(
      model_name="mapanything",
      description="MapAnything - Apache 2.0 licensed model for metric 3D reconstruction",
      device=device
    )
    self.model_checkpoint = "facebook/map-anything-apache"

  def _get_frame_rotation_180_x(self) -> np.ndarray:
    """
    Get 180° rotation matrix around X-axis (Scenescape <-> MapAnything frame conversion).
    This matrix is self-inverse.
    
    Returns:
      4x4 rotation matrix as numpy array
    """
    rotation_x_180 = np.array([
      [1, 0, 0, 0],
      [0, -1, 0, 0],
      [0, 0, -1, 0],
      [0, 0, 0, 1]
    ], dtype=np.float32)
    return rotation_x_180

  def _convert_camera_location_to_mapanything_frame(self, camera_location: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a camera location (pose) from Scenescape frame to MapAnything frame.
    
    Scenescape and MapAnything use different coordinate frame conventions.
    Conversion requires a 180° rotation around X-axis (which is self-inverse).
    
    Args:
      camera_location: Dict with 'translation' (list), 'rotation' (list), 'scale' (list)
        - rotation is expected as quaternion [x, y, z, w] or rotation matrix
        - translation is [x, y, z]
        - scale is [sx, sy, sz]
    
    Returns:
      Dict with same structure but coordinates in MapAnything frame
    """
    if not camera_location:
      return None
    
    try:
      translation = np.array(camera_location.get('translation', [0, 0, 0]), dtype=np.float32)
      scale = np.array(camera_location.get('scale', [1.0, 1.0, 1.0]), dtype=np.float32)
      
      # Handle rotation - could be quaternion or matrix
      rotation = camera_location.get('rotation')
      
      # Build 4x4 pose matrix
      pose_4x4 = np.eye(4, dtype=np.float32)
      pose_4x4[:3, 3] = translation
      
      if isinstance(rotation, (list, np.ndarray)):
        rotation = np.array(rotation, dtype=np.float32)
        if len(rotation) == 4:
          # Quaternion [x, y, z, w] - convert to rotation matrix
          from scipy.spatial.transform import Rotation
          R = Rotation.from_quat(rotation).as_matrix()
          pose_4x4[:3, :3] = R
        elif rotation.shape == (3, 3):
          # Already a rotation matrix
          pose_4x4[:3, :3] = rotation
        else:
          log.warning(f"Unexpected rotation shape {rotation.shape}, using identity")
          pose_4x4[:3, :3] = np.eye(3)
      
      # Apply 180° rotation around X-axis to convert frames
      rotation_x_180 = self._get_frame_rotation_180_x()
      converted_pose = rotation_x_180 @ pose_4x4
      
      # Extract back to Scenescape format
      converted_location = {
        'translation': converted_pose[:3, 3].tolist(),
        'rotation': converted_pose[:3, :3].tolist(),  # Return as rotation matrix
        'scale': scale.tolist()
      }
      
      return converted_location
    except Exception as e:
      log.error(f"Error converting camera location to MapAnything frame: {e}")
      return None

  def load_model(self) -> None:
    """Load MapAnything model and weights."""
    try:
      log.info(f"Loading MapAnything model from {self.model_checkpoint}...")
      self.model = MapAnything.from_pretrained(self.model_checkpoint).to(self.device)
      self.model.eval()
      self.is_loaded = True
      log.info("MapAnything model loaded successfully")

    except Exception as e:
      log.error(f"Failed to load MapAnything model: {e}\n{traceback.format_exc()}")
      raise RuntimeError(f"MapAnything model loading failed: {e}")

  def run_inference(self, frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run MapAnything inference on a LIST of frames, with optional pose conditioning.

    Args:
      frames: [{"data": "<base64>", "camera_location": {...}, ...}, ...]
        camera_location is optional and contains pose information for anchoring

    Returns:
      Dictionary containing predictions, camera poses, and intrinsics
    """
    if not self.is_loaded:
      raise RuntimeError("Model not loaded. Call load_model() first.")

    self.validate_images(frames)

    try:
      pil_images = []
      original_sizes = []
      camera_ids = []
      camera_locations = []

      for img_data in frames:
        camera_ids.append(img_data.get("camera_id"))
        camera_locations.append(img_data.get("camera_location"))
        
        img_array = self.decode_base64_image(img_data["data"])
        # Apply CLAHE for improved contrast
        img_array = self._apply_clahe(img_array)
        pil_image = Image.fromarray(img_array)
        pil_images.append(pil_image)
        original_sizes.append((pil_image.size[0], pil_image.size[1]))  # (width, height)

      # Preprocess images with optional camera location conditioning
      views = self._preprocess_images(pil_images, camera_locations)
      if not views:
        raise ValueError("No valid images processed")

      model_height, model_width = views[0]["img"].shape[-2:]
      model_size = (model_height, model_width)

      log.info(f"Running MapAnything inference on device: {self.device}")
      try:
        # Try with pose conditioning if available
        outputs = self.model.infer(
          views,
          memory_efficient_inference=True,
          amp_dtype="fp32"
        )
      except Exception as e:
        # If anchored inference fails, fall back to full auto-estimation
        log.error(f"Anchored inference failed ({e}), falling back to full auto-estimation. "
                  "Reconstruction will not be aligned to the calibrated cameras.")
        # Remove pose conditioning and retry
        for view in views:
          view.pop('camera_poses', None)
          view.pop('is_metric_scale', None)
        outputs = self.model.infer(
          views,
          memory_efficient_inference=True,
          amp_dtype="fp32"
        )
      
      return self._process_outputs(
          outputs,
          original_sizes,
          model_size,
          camera_ids=camera_ids,
      )

    except Exception as e:
      log.error(f"MapAnything inference (frames) failed: {e}\n{traceback.format_exc()}")
      raise RuntimeError(f"MapAnything inference (frames) failed: {e}")

  def get_supported_outputs(self) -> List[str]:
    """Get supported output formats."""
    return ["mesh", "pointcloud"]

  def get_native_output(self) -> str:
    """Get native output format."""
    return "mesh"

  def scale_intrinsics_to_original_size(self, intrinsics: np.ndarray, model_size: tuple, original_sizes: list,
                   preprocessing_mode: str = "crop") -> list:
    """Scale intrinsics for MapAnything preprocessing (resolution mapping + rescale + crop)"""
    if len(intrinsics.shape) == 2:
      # Single matrix (3, 3) -> (1, 3, 3)
      intrinsics = intrinsics[np.newaxis, ...]

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

  def create_output(self, result: Dict[str, Any], output_format: str = None) -> 'trimesh.Scene':
    """
    Create 3D output scene from MapAnything results.

    Args:
      result: Result dictionary from run_inference containing predictions
      output_format: Desired output format ('mesh' or 'pointcloud'). If None, uses native format.

    Returns:
      trimesh.Scene: Processed 3D scene
    """
    if output_format is None:
      output_format = self.get_native_output()

    if output_format not in self.get_supported_outputs():
      raise ValueError(f"Output format '{output_format}' not supported. Supported formats: {self.get_supported_outputs()}")

    predictions = result["predictions"]

    if output_format == "pointcloud":
      # Convert MapAnything mesh to point cloud
      log.info("Converting MapAnything mesh to point cloud format...")
      from mesh_utils import create_pointcloud_from_mesh
      scene = create_pointcloud_from_mesh(predictions)
      return scene
    else:
      # Use MapAnything's default GLB export (mesh)
      from mapanything.utils.viz import predictions_to_glb
      log.info("Creating MapAnything mesh output...")
      scene = predictions_to_glb(predictions, as_mesh=True)
      return scene

  def _preprocess_images(self, pil_images: List[Image.Image], camera_locations: List[Optional[Dict]] = None) -> List[Dict[str, Any]]:
    """
    Preprocess images using MapAnything's logic, optionally with camera pose conditioning.

    Args:
      pil_images: List of PIL images
      camera_locations: Optional list of camera location dicts (same length as pil_images)
        Each dict can be None (uncalibrated) or contain 'translation', 'rotation', 'scale'

    Returns:
      List of view dictionaries ready for inference, with optional pose conditioning
    """
    if camera_locations is None:
      camera_locations = [None] * len(pil_images)
    
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
      view_dict = dict(
        img=ImgNorm(processed_img)[None],
        true_shape=np.int32([processed_img.size[::-1]]),
        idx=i,
        instance=str(i),
        data_norm_type=[norm_type],
      )
      
      # Add pose conditioning if camera_location is available
      if camera_locations and i < len(camera_locations) and camera_locations[i] is not None:
        cam_loc = camera_locations[i]
        try:
          # Convert from Scenescape frame to MapAnything frame
          converted_loc = self._convert_camera_location_to_mapanything_frame(cam_loc)
          if converted_loc:
            # MapAnything requires camera_poses as a (B, 4, 4) tensor of
            # camera-to-world matrices, matching the batch dim used by 'img'.
            pose_4x4 = np.eye(4, dtype=np.float32)
            pose_4x4[:3, :3] = np.array(converted_loc['rotation'], dtype=np.float32)
            pose_4x4[:3, 3] = np.array(converted_loc['translation'], dtype=np.float32)
            view_dict['camera_poses'] = torch.from_numpy(pose_4x4)[None]
            view_dict['is_metric_scale'] = torch.tensor([True])
            log.info(f"Added pose conditioning for view {i}")
        except Exception as e:
          log.warning(f"Failed to add pose conditioning for view {i}: {e}. Proceeding without it.")
      
      views.append(view_dict)

    return views

  def _process_outputs(self, outputs: List[Dict], original_sizes: List[tuple],
            model_size: tuple, camera_ids: Optional[List[Any]] = None) -> Dict[str, Any]:
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

    # Create rotation matrix for 180° around X-axis (applied to all cameras).
    # Mesh already is rotated 180° around x-axis in MapAnything output.
    rotation_x_180 = np.array([
      [1, 0, 0, 0],
      [0, -1, 0, 0],
      [0, 0, -1, 0],
      [0, 0, 0, 1]
    ], dtype=np.float32)

    for view_idx, pred in enumerate(outputs):
      if camera_ids:
        cam_id = camera_ids[view_idx]
      else:
        cam_id = None

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

      # Apply 180-degree rotation around world X-axis to camera pose
      pose_4x4 = np.eye(4, dtype=np.float32)
      pose_4x4[:3, :3] = pose_np[:3, :3]
      pose_4x4[:3, 3] = pose_np[:3, 3]
      rotated_pose = rotation_x_180 @ pose_4x4

      # Convert rotation matrix to quaternion
      rotation_matrix = rotated_pose[:3, :3]
      quaternion = self.rotation_matrix_to_quaternion(rotation_matrix)

      camera_poses.append({
        "camera_id": cam_id,
        "rotation": quaternion.tolist(),  # [x, y, z, w]
        "translation": rotated_pose[:3, 3].tolist()
      })
      model_intrinsics_list.append(intrinsics_np)

    # Scale intrinsics back to original image sizes
    model_intrinsics = np.stack(model_intrinsics_list, axis=0)  # (S, 3, 3)
    original_intrinsics = self.scale_intrinsics_to_original_size(
      model_intrinsics,
      model_size,
      original_sizes
    )

    # Convert scaled intrinsics to list format
    intrinsics_list = []
    for i, K in enumerate(original_intrinsics):
      cam_id = camera_ids[i] if camera_ids is not None and i < len(camera_ids) else None
      intrinsics_list.append({
          "camera_id": cam_id,
          "K": K.tolist()
      })

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
