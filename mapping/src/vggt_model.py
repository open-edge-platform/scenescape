#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
VGGT Model Implementation
Implementation of the ReconstructionModel interface for VGGT.

This model is instantiated directly by the vggt-service container.
"""

import os
import sys
from typing import Dict, Any, List
import numpy as np
import torch
from PIL import Image
import torchvision.transforms as tvf

from scene_common import log

from model_interface import ReconstructionModel

sys.path.append('/workspace/vggt')

# Import VGGT-specific modules
from vggt.models.vggt import VGGT
from vggt.utils.pose_enc import pose_encoding_to_extri_intri
from vggt.utils.geometry import unproject_depth_map_to_point_map


class VGGTModel(ReconstructionModel):
  """
  VGGT model for 3D reconstruction.

  VGGT (Visual Geometry Grounded Transformer) is optimized for sparse view reconstruction
  and outputs point clouds with depth information.

  This model is used by the vggt-service container.
  """

  def __init__(self, device: str = "cpu"):
    super().__init__(
      model_name="vggt",
      description="VGGT - Visual Geometry Grounded Transformer for sparse view reconstruction",
      device=device
    )
    self.model_weights_url = "https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt"
    self.local_weights_path = "/workspace/model_weights/vggt_model.pt"

  def loadModel(self) -> None:
    """Load VGGT model and weights."""
    try:
      log.info("Initializing VGGT model...")
      self.model = VGGT()

      # Try to load from local cache first, otherwise download
      if os.path.exists(self.local_weights_path):
        log.info("Loading VGGT weights from local cache...")
        weights = torch.load(self.local_weights_path, map_location=self.device)
      else:
        log.info("Downloading VGGT weights...")
        weights = torch.hub.load_state_dict_from_url(
          self.model_weights_url,
          map_location=self.device
        )

      self.model.load_state_dict(weights)
      self.model.eval()
      self.model = self.model.to(self.device)
      self.is_loaded = True
      log.info("VGGT model loaded successfully")

    except Exception as e:
      log.error(f"Failed to load VGGT model: {e}")
      raise RuntimeError(f"VGGT model loading failed: {e}")

  def runInference(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
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
      raise RuntimeError("Model not loaded. Call loadModel() first.")

    self.validateImages(images)

    try:
      # Decode images and get original sizes
      pil_images = []
      original_sizes = []

      for img_data in images:
        img_array = self.decodeBase64Image(img_data["data"])
        # Apply CLAHE for improved contrast
        img_array = self._applyCLAHE(img_array)
        pil_image = Image.fromarray(img_array)
        pil_images.append(pil_image)
        original_sizes.append((pil_image.size[0], pil_image.size[1]))  # (width, height)

      # Preprocess images using VGGT's logic
      images_tensor, model_size = self._preprocessImages(pil_images)

      # Run inference
      log.info(f"Running VGGT inference on device: {self.device}")
      predictions = self._runModelInference(images_tensor)

      # Process outputs
      result = self._processOutputs(predictions, original_sizes, model_size)

      return result

    except Exception as e:
      log.error(f"VGGT inference failed: {e}")
      raise RuntimeError(f"VGGT inference failed: {e}")

  def getSupportedOutputs(self) -> List[str]:
    """Get supported output formats."""
    return ["pointcloud", "mesh"]

  def getNativeOutput(self) -> str:
    """Get native output format."""
    return "pointcloud"

  def scaleIntrinsicsToOriginalSize(self, intrinsics: np.ndarray, model_size: tuple, original_sizes: list,
                   preprocessing_mode: str = "crop") -> list:
    """Scale intrinsics for VGGT preprocessing (simple resize + crop/pad)"""
    if len(intrinsics.shape) == 2:
      # Single matrix (3, 3) -> (1, 3, 3)
      intrinsics = intrinsics[np.newaxis, ...]

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

  def createOutput(self, result: Dict[str, Any], output_format: str = None, voxel_size: float = 0.01, floor_margin: float = 0.02) -> 'trimesh.Scene':
    """
    Create 3D output scene from VGGT results.

    Args:
      result: Result dictionary from runInference containing predictions
      output_format: Desired output format ('pointcloud' or 'mesh'). If None, uses native format.
      voxel_size: Optional voxel downsampling helps clean noisy point clouds.
      floor_margin: Floor flattening added to smooth floor plane.

    Returns:
      trimesh.Scene: Processed 3D scene
    """

    import tempfile
    import numpy as np
    import open3d as o3d
    import trimesh
    from scene_common.mesh_util import extractMeshFromPointCloud
    import shutil
    from visual_util import predictions_to_glb

    if output_format is None:
      output_format = self.getNativeOutput()

    if output_format not in self.getSupportedOutputs():
      raise ValueError(
        f"Output format '{output_format}' not supported. Supported formats: {self.getSupportedOutputs()}"
      )

    predictions = result["predictions"]
    log.info("Creating 3D output scene...")
    log.info(f"Available prediction keys: {list(predictions.keys())}")

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
          log.info(f"Already in world coordinates: {already_world}")

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
          # Rotate mesh by 180 degrees along the Z-axis
          rotation_matrix = trimesh.transformations.rotation_matrix(
            np.pi, [0, 0, 1], mesh.centroid
          )
          mesh.apply_transform(rotation_matrix)

          log.info(f"Watertight mesh created: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
          return scene

        else:
          log.warning("No world_points found, falling back to original VGGT export")

      except Exception as e:
        log.warning(f"Mesh reconstruction failed: {e}, using original VGGT export")

    log.info("Using VGGT point cloud export as fallback")
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

  def _preprocessImages(self, pil_images: List[Image.Image]) -> tuple:
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

  def _runModelInference(self, images_tensor: torch.Tensor) -> Dict[str, Any]:
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

  def _processOutputs(self, predictions: Dict[str, Any], original_sizes: List[tuple],
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

    model_intrinsics = predictions["intrinsic"]  # (S, 3, 3)
    original_intrinsics = self.scaleIntrinsicsToOriginalSize(
      model_intrinsics,
      model_size,
      original_sizes,
      preprocessing_mode="crop"  # VGGT default mode
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
      quaternion = self.rotationMatrixToQuaternion(rotation_matrix)

      camera_poses.append({
        "rotation": quaternion.tolist(),  # [x, y, z, w]
        "translation": camera_to_world[:3, 3].tolist()
      })
      intrinsics_list.append(intrinsic_matrix.tolist())

    return {
      "predictions": predictions,
      "camera_poses": camera_poses,
      "intrinsics": intrinsics_list
    }
