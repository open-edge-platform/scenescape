#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MapAnything Model Implementation
Implementation of the ReconstructionModel interface for MapAnything.

This model is instantiated directly by the mapanything-service container.
"""

import sys
from typing import Dict, Any, List
import numpy as np
from PIL import Image

from scene_common import log

from model_interface import ReconstructionModel

# Add model paths to sys.path
sys.path.append('/workspace/map-anything')

# Import MapAnything-specific modules
from mapanything.models import MapAnything
from mapanything.utils.image import find_closest_aspect_ratio, IMAGE_NORMALIZATION_DICT
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

  def loadModel(self) -> None:
    """Load MapAnything model and weights."""
    try:
      log.info(f"Loading MapAnything model from {self.model_checkpoint}...")
      self.model = MapAnything.from_pretrained(self.model_checkpoint).to(self.device)
      self.model.eval()
      self.is_loaded = True
      log.info("MapAnything model loaded successfully")

    except Exception as e:
      log.error(f"Failed to load MapAnything model: {e}")
      raise RuntimeError(f"MapAnything model loading failed: {e}")

  def runInference(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run MapAnything inference on input images.

    Args:
      images: List of image dictionaries with 'data' field containing base64 images

    Returns:
      Dictionary containing predictions, camera poses, and intrinsics
    """
    if not self.is_loaded:
      raise RuntimeError("Model not loaded. Call loadModel() first.")

    self.validateImages(images)

    try:
      # Decode images and get original sizes
      pil_images = []
      original_sizes = []

      for img_data in images:
        img_array = self.decodeBase64Image(img_data["data"])
        pil_image = Image.fromarray(img_array)
        pil_images.append(pil_image)
        original_sizes.append((pil_image.size[0], pil_image.size[1]))  # (width, height)

      # Process images using MapAnything's preprocessing logic
      views = self._preprocessImages(pil_images)

      if not views:
        raise ValueError("No valid images processed")

      # Get model input size from processed views
      model_height, model_width = views[0]["img"].shape[-2:]
      model_size = (model_height, model_width)

      log.info(f"Running MapAnything inference on device: {self.device}")
      # Run inference with FP32 model as we use CPU
      outputs = self.model.infer(views, memory_efficient_inference=False, amp_dtype="fp32")

      # Process outputs
      result = self._processOutputs(outputs, original_sizes, model_size)

      return result

    except Exception as e:
      log.error(f"MapAnything inference failed: {e}")
      raise RuntimeError(f"MapAnything inference failed: {e}")

  def getSupportedOutputs(self) -> List[str]:
    """Get supported output formats."""
    return ["mesh", "pointcloud"]

  def getNativeOutput(self) -> str:
    """Get native output format."""
    return "mesh"

  def scaleIntrinsicsToOriginalSize(self, intrinsics: np.ndarray, model_size: tuple, original_sizes: list,
                   preprocessing_mode: str = "crop") -> list:
    """Scale intrinsics for MapAnything preprocessing (resolution mapping + rescale + crop)"""
    if len(intrinsics.shape) == 2:
      # Single matrix (3, 3) -> (1, 3, 3)
      intrinsics = intrinsics[np.newaxis, ...]

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

    def findClosestAspectRatio(aspect_ratio, resolution_set=518):
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
    target_width, target_height = findClosestAspectRatio(avg_aspect_ratio)

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

  def createOutput(self, result: Dict[str, Any], output_format: str = None) -> 'trimesh.Scene':
    """
    Create 3D output scene from MapAnything results.

    Args:
      result: Result dictionary from runInference containing predictions
      output_format: Desired output format ('mesh' or 'pointcloud'). If None, uses native format.

    Returns:
      trimesh.Scene: Processed 3D scene
    """
    if output_format is None:
      output_format = self.getNativeOutput()

    if output_format not in self.getSupportedOutputs():
      raise ValueError(f"Output format '{output_format}' not supported. Supported formats: {self.getSupportedOutputs()}")

    predictions = result["predictions"]

    if output_format == "pointcloud":
      # Convert MapAnything mesh to point cloud
      log.info("Converting MapAnything mesh to point cloud format...")
      from mesh_utils import createPointcloudFromMesh
      scene = createPointcloudFromMesh(predictions)
      return scene
    else:
      # Use MapAnything's default GLB export (mesh)
      from mapanything.utils.viz import predictions_to_glb
      log.info("Creating MapAnything mesh output...")
      scene = predictions_to_glb(predictions, as_mesh=True)
      return scene

  def _preprocessImages(self, pil_images: List[Image.Image]) -> List[Dict[str, Any]]:
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

  def _processOutputs(self, outputs: List[Dict], original_sizes: List[tuple],
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

    # Create rotation matrix for 180° around X-axis (applied to all cameras).
    # Mesh already is rotated 180° around x-axis in MapAnything output.
    rotation_x_180 = np.array([
      [1, 0, 0, 0],
      [0, -1, 0, 0],
      [0, 0, -1, 0],
      [0, 0, 0, 1]
    ], dtype=np.float32)

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

      # Apply 180-degree rotation around world X-axis to camera pose
      pose_4x4 = np.eye(4, dtype=np.float32)
      pose_4x4[:3, :3] = pose_np[:3, :3]
      pose_4x4[:3, 3] = pose_np[:3, 3]
      rotated_pose = rotation_x_180 @ pose_4x4

      # Convert rotation matrix to quaternion
      rotation_matrix = rotated_pose[:3, :3]
      quaternion = self.rotationMatrixToQuaternion(rotation_matrix)

      camera_poses.append({
        "rotation": quaternion.tolist(),  # [x, y, z, w]
        "translation": rotated_pose[:3, 3].tolist()
      })
      model_intrinsics_list.append(intrinsics_np)

    # Scale intrinsics back to original image sizes
    model_intrinsics = np.stack(model_intrinsics_list, axis=0)  # (S, 3, 3)
    original_intrinsics = self.scaleIntrinsicsToOriginalSize(
      model_intrinsics,
      model_size,
      original_sizes
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
