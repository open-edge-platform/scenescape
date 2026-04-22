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
from typing import Dict, Any, List, Tuple
import numpy as np
import torch
from PIL import Image
import torchvision.transforms as tvf


import tempfile
import numpy as np
import trimesh
import shutil
from scene_common.mesh_util import image_mesh

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
      camera_ids = []
      camera_locations = []

      for img_data in images:
        img_array = self.decodeBase64Image(img_data["data"])
        camera_ids.append(img_data.get("camera_id"))
        camera_locations.append(img_data.get("camera_location"))
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
      result = self._processOutputs(predictions, original_sizes, model_size, camera_ids=camera_ids, camera_locations=camera_locations)

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

  def _camera_center_from_c2w(self, c2w: np.ndarray) -> np.ndarray:
    return c2w[:3, 3]

  def _baseline_units(self, c2w_a: np.ndarray, c2w_b: np.ndarray) -> float:
    ca = self._camera_center_from_c2w(c2w_a)
    cb = self._camera_center_from_c2w(c2w_b)
    return float(np.linalg.norm(cb - ca))

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

  def createOutput(
    self,
    result: Dict[str, Any],
    output_format: str = None,
    voxel_size: float = 0.01,
    floor_margin: float = 0.02,
  ) -> "trimesh.Scene":
    """
    Create 3D output scene from VGGT results.

    - Fast path (mesh): MapAnything-style image-grid triangulation (image_mesh) using
      world_points_from_depth + images (+ optional depth_conf mask). This avoids Poisson
      and is much faster.
    - Fallback: original VGGT GLB export via predictions_to_glb.

    Args:
      result: Result dictionary from runInference containing predictions
      output_format: Desired output format ('pointcloud' or 'mesh'). If None, uses native format.
      voxel_size: Kept for backward compat; not used in fast mesh path.
      floor_margin: Floor flattening margin (meters) for fast mesh path.

    Returns:
      trimesh.Scene: Processed 3D scene
    """
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
        # Prefer VGGT-generated world points from depth (already in world coords)
        world_points = predictions.get("world_points_from_depth", None)
        if world_points is None:
          world_points = predictions.get("world_points", None)

        images = predictions.get("images", predictions.get("image", None))

        if world_points is None or images is None:
          raise RuntimeError("Missing world_points/world_points_from_depth and/or images for mesh creation.")

        # Expected shapes:
        # world_points: (V, H, W, 3)
        # images: (V, 3, H, W) or (V, H, W, 3)
        if world_points.ndim != 4 or world_points.shape[-1] != 3:
          raise RuntimeError(f"world_points must be (V,H,W,3). Got {world_points.shape}")

        V, H, W, _ = world_points.shape

        # Convert images to NHWC float [0,1]
        if images.ndim == 4 and images.shape[1] == 3 and images.shape[2] == H and images.shape[3] == W:
          images_nhwc = np.transpose(images, (0, 2, 3, 1))
        elif images.ndim == 4 and images.shape[1] == H and images.shape[2] == W and images.shape[3] == 3:
          images_nhwc = images
        else:
          raise RuntimeError(f"Unexpected images shape {images.shape}; expected (V,3,H,W) or (V,H,W,3)")

        images_nhwc = images_nhwc.astype(np.float32)
        if images_nhwc.max() > 1.0:
          images_nhwc /= 255.0

        # Optional depth/confidence (VGGT provides these)
        depth = predictions.get("depth", None)            # (V,H,W) likely
        depth_conf = predictions.get("depth_conf", None)  # (V,H,W) likely

        # Tuning knobs
        stride = int(os.getenv("VGGT_MESH_STRIDE", "2"))  # 1=full res, 2=4x faster, 3=9x faster
        conf_th = float(os.getenv("VGGT_DEPTH_CONF_TH", "0.30"))
        merge_frames = os.getenv("VGGT_MESH_MERGE_FRAMES", "0") == "1"
        scene = trimesh.Scene()

        merged_vertices = []
        merged_faces = []
        merged_colors = []
        vert_offset = 0

        for i in range(V):
          pts = world_points[i]    # (H,W,3)
          img = images_nhwc[i]     # (H,W,3)

          # Validity mask (approx MapAnything final_masks)
          mask = np.isfinite(pts).all(axis=-1)

          if depth is not None and isinstance(depth, np.ndarray) and depth.ndim == 3:
            mask &= (depth[i] > 0)

          if depth_conf is not None and isinstance(depth_conf, np.ndarray) and depth_conf.ndim == 3:
            mask &= (depth_conf[i] >= conf_th)

          # Optional floor flattening (only on valid points)
          if floor_margin is not None and floor_margin > 0:
            z = pts[..., 2]
            z_valid = z[mask]
            if z_valid.size > 0:
              z_min = float(z_valid.min())
              floor_idx = (z <= z_min + floor_margin) & mask
              # copy only if we actually modify
              if floor_idx.any():
                pts = pts.copy()
                pts[..., 2][floor_idx] = z_min

          # Downsample grid for speed (stride)
          if stride > 1:
            pts = pts[::stride, ::stride]
            img = img[::stride, ::stride]
            mask = mask[::stride, ::stride]

          # Build mesh by triangulating the image grid
          faces, vertices, vertex_colors = image_mesh(
            pts * np.array([1, -1, 1], dtype=np.float32),  # match MapAnything convention
            img,
            mask=mask,
            tri=True,
            return_indices=False,
          )
          vertices = vertices * np.array([1, -1, 1], dtype=np.float32)

          # ---- FAST BAD-TRIANGLE FILTER (key fix) ----
          max_edge = float(os.getenv("VGGT_MAX_EDGE_M", "0.06"))  # 6cm start; tune 0.03–0.12

          v0 = vertices[faces[:, 0]]
          v1 = vertices[faces[:, 1]]
          v2 = vertices[faces[:, 2]]

          e01 = np.linalg.norm(v0 - v1, axis=1)
          e12 = np.linalg.norm(v1 - v2, axis=1)
          e20 = np.linalg.norm(v2 - v0, axis=1)

          good = (e01 < max_edge) & (e12 < max_edge) & (e20 < max_edge)
          faces = faces[good]
          vertex_colors = vertex_colors  # unchanged
          # -------------------------------------------
          vc_uint8 = (vertex_colors * 255).astype(np.uint8)

          if merge_frames:
            merged_vertices.append(vertices)
            merged_faces.append(faces + vert_offset)
            merged_colors.append(vc_uint8)
            vert_offset += vertices.shape[0]
          else:
            mesh = trimesh.Trimesh(
              vertices=vertices,
              faces=faces,
              vertex_colors=vc_uint8,
              process=False,
            )
            scene.add_geometry(mesh)

        if merge_frames and merged_vertices:
          Vv = np.vstack(merged_vertices)
          Ff = np.vstack(merged_faces)
          Cc = np.vstack(merged_colors)
          mesh = trimesh.Trimesh(vertices=Vv, faces=Ff, vertex_colors=Cc, process=False)
          scene.add_geometry(mesh)

        # Orientation fix (same as MapAnything predictions_to_glb)
        scene.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))

        log.info("Fast mesh created using MapAnything image_mesh triangulation")
        return scene

      except Exception as e:
        log.warning(f"Fast mesh path failed: {e}. Falling back to VGGT point cloud export.")

    log.info("Using VGGT point cloud export as fallback")
    temp_dir = tempfile.mkdtemp(prefix="vggt_glb_")
    try:
      from visual_util import predictions_to_glb
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
    No-padding preprocess:
    1) Resize so the SHORTER side becomes 518 (keeps aspect ratio).
    2) (Optionally) round resized dims to multiples of 14 for VGGT.
    3) Center-crop to 518x518.
    """
    processed_images = []
    target = 518

    for pil_image in pil_images:
      w, h = pil_image.size

      # Scale so min side == 518
      scale = target / float(min(w, h))
      new_w = int(round((w * scale) / 14.0) * 14)
      new_h = int(round((h * scale) / 14.0) * 14)

      # Safety: ensure both dims >= 518 after rounding
      new_w = max(target, new_w)
      new_h = max(target, new_h)

      img_resized = pil_image.resize((new_w, new_h), Image.Resampling.BICUBIC)
      img_tensor = tvf.ToTensor()(img_resized)  # (3, H, W)

      # Center crop to 518x518 (no padding)
      H, W = img_tensor.shape[1], img_tensor.shape[2]
      top = (H - target) // 2
      left = (W - target) // 2
      img_tensor = img_tensor[:, top:top + target, left:left + target]

      if img_tensor.shape[1] != target or img_tensor.shape[2] != target:
        raise RuntimeError(f"Preprocess produced {tuple(img_tensor.shape)}; expected (3,{target},{target})")

      processed_images.append(img_tensor)

    images_tensor = torch.stack(processed_images, dim=0).to(self.device)  # (N,3,518,518)
    model_size = (target, target)
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

  def _baseline_metric_from_camera_locations(self, camera_locations, camera_ids=None) -> float:
    """
    Robustly compute a metric baseline (meters) from camera_locations.

    camera_locations may contain dicts, None, and/or malformed entries.
    Each valid dict must contain 'translation': [x,y,z] in meters.
    """
    if not camera_locations or len(camera_locations) < 2:
      return 0.0

    try:
      translations = []
      for loc in camera_locations:
        if not isinstance(loc, dict):
          continue
        t = loc.get("translation", None)
        if t is None or len(t) != 3:
          continue
        t = np.asarray(t, dtype=np.float32)
        if t.shape != (3,) or not np.isfinite(t).all():
          continue
        translations.append(t)

      if len(translations) < 2:
        return 0.0

      distances = []
      for i in range(len(translations)):
        for j in range(i + 1, len(translations)):
          d = float(np.linalg.norm(translations[j] - translations[i]))
          if np.isfinite(d) and d > 1e-6:
            distances.append(d)

      if not distances:
        return 0.0

      return float(np.min(distances))

    except Exception as e:
      log.exception(f"Failed to compute baseline from camera_locations: {e}")
      return 0.0

  def _processOutputs(self, predictions: Dict[str, Any], original_sizes: List[tuple],
            model_size: tuple, camera_ids: List[Any] = None, camera_locations: List[Any] = None) -> Dict[str, Any]:
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
    rotation_x_180 = np.array([
      [1, 0, 0, 0],
      [0, -1, 0, 0],
      [0, 0, -1, 0],
      [0, 0, 0, 1]
    ], dtype=np.float32)

    # --- build camera_to_world for all frames first ---
    camera_to_world_list = []

    for i in range(extrinsic_matrices.shape[0]):
      world_to_camera = extrinsic_matrices[i]  # (4,4) or (3,4)

      # Convert 3x4 to 4x4 if needed
      if world_to_camera.shape == (3, 4):
        w2c = np.eye(4, dtype=np.float32)
        w2c[:3, :4] = world_to_camera
        world_to_camera = w2c

      # Invert to get camera-to-world
      c2w = np.linalg.inv(world_to_camera).astype(np.float32)

      # Apply your orientation fix
      c2w = rotation_x_180 @ c2w

      camera_to_world_list.append(c2w)

    # --- SCALE FIX: compute metric baseline from provided camera_locations ---
    baseline_metric = self._baseline_metric_from_camera_locations(camera_locations, camera_ids=camera_ids)

    if baseline_metric <= 0:
      log.warning("VGGT: camera_locations missing/invalid; skipping metric scaling (scale will be arbitrary).")

    if baseline_metric > 0 and len(camera_to_world_list) >= 2:
      b_units = self._baseline_units(camera_to_world_list[0], camera_to_world_list[1])
      if b_units > 1e-6:
        scale = baseline_metric / b_units
        log.info(f"Scaling VGGT outputs by s={scale:.6f} (baseline {baseline_metric:.6f}m / {b_units:.6f} units)")

        # scale camera translations
        for k in range(len(camera_to_world_list)):
          camera_to_world_list[k] = camera_to_world_list[k].copy()
          camera_to_world_list[k][:3, 3] *= scale

        # scale world points (affects glb_size -> pixels_per_meter)
        if isinstance(predictions.get("world_points_from_depth"), np.ndarray):
          predictions["world_points_from_depth"] *= scale
        if isinstance(predictions.get("world_points"), np.ndarray):
          predictions["world_points"] *= scale

        # optional: scale depth too (only if used elsewhere)
        if isinstance(predictions.get("depth"), np.ndarray):
          predictions["depth"] *= scale
      else:
        log.warning(f"VGGT: predicted baseline too small ({b_units}); skipping scaling.")

    # --- now build camera_poses + intrinsics_list using the scaled camera_to_world_list ---
    camera_poses = []
    intrinsics_list = []

    for i, camera_to_world in enumerate(camera_to_world_list):
      cam_id = camera_ids[i] if camera_ids is not None and i < len(camera_ids) else None
      K = original_intrinsics[i]

      rotation_matrix = camera_to_world[:3, :3]
      quaternion = self.rotationMatrixToQuaternion(rotation_matrix)

      camera_poses.append({
        "camera_id": cam_id,
        "rotation": quaternion.tolist(), # [x, y, z, w]
        "translation": camera_to_world[:3, 3].tolist()
      })

      intrinsics_list.append({
        "camera_id": cam_id,
        "K": K.tolist()
      })

    return {
      "predictions": predictions,
      "camera_poses": camera_poses,
      "intrinsics": intrinsics_list
    }
