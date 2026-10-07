#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MapAnything Model Implementation
Implementation of the ReconstructionModel interface for MapAnything.

This model is instantiated directly by the mapanything-service container.
"""

import base64
import os
import sys
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from PIL import Image

import traceback

from scene_common import log

from model_interface import ReconstructionModel
from image_transforms import mapanything_transform


def hf_offline_forced() -> bool:
  return os.environ.get("HF_HUB_OFFLINE", "").strip().lower() in ("1", "true", "yes")


def pin_cached_torch_hub_refs() -> None:
  """Make ``torch.hub.load("owner/repo", ...)`` use the cached checkout offline.

  Without an explicit ref torch.hub first asks github.com whether the default
  branch is main or master, and only consults the cache after that request
  fails (a 20 s DNS timeout, or a hang behind a dead resolver). MapAnything's
  vendored aggregator loads DINOv2 that way. Append the ref of the checkout
  already in TORCH_HOME so the lookup is skipped.
  """
  import torch.hub as hub
  if getattr(hub.load, "_scenescape_pinned", False):
    return
  original = hub.load

  def load(repo_or_dir, *args, **kwargs):
    if isinstance(repo_or_dir, str) and ":" not in repo_or_dir and repo_or_dir.count("/") == 1 \
       and not os.path.isdir(repo_or_dir):
      owner, name = repo_or_dir.split("/")
      for ref in ("main", "master"):
        if os.path.isdir(os.path.join(hub.get_dir(), f"{owner}_{name}_{ref}")):
          repo_or_dir = f"{repo_or_dir}:{ref}"
          break
    return original(repo_or_dir, *args, **kwargs)

  load._scenescape_pinned = True
  hub.load = load


def load_from_cache_first(model_cls, checkpoint: str):
  """``from_pretrained`` without touching the network when the weights are cached.

  huggingface_hub revalidates every file against the Hub before falling back
  to the cache, which stalls (DNS/connect timeouts per file) or fails on an
  air-gapped edge node even though the volume holds the weights. Try the
  cache alone first; download only when nothing is cached and offline mode
  is not forced via HF_HUB_OFFLINE.
  """
  pin_cached_torch_hub_refs()
  try:
    model = model_cls.from_pretrained(checkpoint, local_files_only=True)
    log.info(f"Loaded {checkpoint} from the local Hugging Face cache")
    return model
  except Exception as exc:  # noqa: BLE001 - any cache miss means download
    if hf_offline_forced():
      raise RuntimeError(
        f"{checkpoint} is not in the local Hugging Face cache and HF_HUB_OFFLINE is set"
      ) from exc
    log.info(f"{checkpoint} not fully cached ({exc.__class__.__name__}); downloading")
  return model_cls.from_pretrained(checkpoint)

# Add model paths to sys.path
sys.path.append('/workspace/map-anything')

# Import MapAnything-specific modules
from mapanything.models import MapAnything
from mapanything.utils.image import find_closest_aspect_ratio, IMAGE_NORMALIZATION_DICT
from mapanything.utils.geometry import depthmap_to_world_frame
from mapanything.utils.cropping import crop_resize_if_necessary
import torch
import torchvision.transforms as tvf


class MapAnythingModel(ReconstructionModel):
  """
  MapAnything model for 3D reconstruction.

  MapAnything is a metric 3D reconstruction model that outputs meshes
  with accurate scale and camera poses.

  This model is used by the mapanything-service container.
  """

  # Rx(180°): MapAnything's world has +Y down / +Z into the scene relative to
  # the Scenescape frame. Self-inverse, so the same matrix maps both ways.
  SCENE_TO_MODEL_WORLD = np.array([
    [1, 0, 0, 0],
    [0, -1, 0, 0],
    [0, 0, -1, 0],
    [0, 0, 0, 1],
  ], dtype=np.float64)

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
      log.info(f"Loading MapAnything model from {self.model_checkpoint}...")
      self.model = load_from_cache_first(MapAnything, self.model_checkpoint).to(self.device)
      self.model.eval()
      self.is_loaded = True
      log.info("MapAnything model loaded successfully")

    except Exception as e:
      log.error(f"Failed to load MapAnything model: {e}\n{traceback.format_exc()}")
      raise RuntimeError(f"MapAnything model loading failed: {e}")

  def run_inference(self, frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run MapAnything inference on a LIST of frames.

    Args:
      frames: [{"data": "<base64>", "camera_intrinsics": {...}?, "camera_location": {...}?}, ...]
        Optional intrinsics (pixels of the uploaded image) and camera-to-world
        poses are passed to the model as geometric conditioning.

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
      prior_intrinsics = []
      prior_poses = []

      for img_data in frames:
        camera_ids.append(img_data.get("camera_id"))
        img_array = self.decode_base64_image(img_data["data"])
        # Apply CLAHE for improved contrast
        img_array = self._apply_clahe(img_array)
        pil_image = Image.fromarray(img_array)
        pil_images.append(pil_image)
        original_sizes.append((pil_image.size[0], pil_image.size[1]))  # (width, height)
        prior_intrinsics.append(self.intrinsics_from_metadata(img_data.get("camera_intrinsics")))
        prior_poses.append(self.pose_from_location(img_data.get("camera_location")))

      views = self._preprocess_images(pil_images, prior_intrinsics, prior_poses)
      if not views:
        raise ValueError("No valid images processed")

      model_height, model_width = views[0]["img"].shape[-2:]
      model_size = (model_height, model_width)

      log.info(f"Running MapAnything inference on device: {self.device}")
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
    """Undo MapAnything's per-image resize + center crop on model-resolution intrinsics.

    Args:
      intrinsics: (S, 3, 3) intrinsics in model-input pixels
      model_size: (height, width) of the model input
      original_sizes: [(orig_width, orig_height), ...]
      preprocessing_mode: unused; MapAnything always resizes then crops
    """
    if len(intrinsics.shape) == 2:
      # Single matrix (3, 3) -> (1, 3, 3)
      intrinsics = intrinsics[np.newaxis, ...]

    model_height, model_width = model_size
    target_size = (model_width, model_height)
    scaled_intrinsics = []
    for i, original_size in enumerate(original_sizes):
      transform = mapanything_transform(original_size, target_size)
      scaled_intrinsics.append(transform.invert_intrinsics(intrinsics[i]))

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

  def _preprocess_images(
    self,
    pil_images: List[Image.Image],
    prior_intrinsics: Optional[List[Optional[np.ndarray]]] = None,
    prior_poses: Optional[List[Optional[np.ndarray]]] = None,
  ) -> List[Dict[str, Any]]:
    """
    Preprocess images using MapAnything's logic and attach geometric priors.

    Args:
      pil_images: List of PIL images
      prior_intrinsics: Per-image 3x3 intrinsics in original pixels, or None
      prior_poses: Per-image 4x4 camera-to-world poses, or None

    Returns:
      List of view dictionaries ready for inference
    """
    n = len(pil_images)
    prior_intrinsics = list(prior_intrinsics or [None] * n)
    prior_poses = list(prior_poses or [None] * n)

    # Output poses and the GLB are rotated 180° about world X on the way out
    # (see _process_outputs), so priors given in the scene frame must be
    # rotated the same way on the way in or they land in a mirrored world.
    prior_poses = [
      None if p is None else self.SCENE_TO_MODEL_WORLD @ np.asarray(p, dtype=np.float64)
      for p in prior_poses
    ]

    # MapAnything requires view 0 to carry a pose whenever any view does.
    if prior_poses and prior_poses[0] is None and any(p is not None for p in prior_poses):
      log.warning("MapAnything: first view has no camera_location; ignoring pose priors for all views")
      prior_poses = [None] * n

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
    conditioned = 0
    for i, pil_image in enumerate(pil_images):
      # Apply MapAnything's crop_resize_if_necessary
      processed_img = crop_resize_if_necessary(pil_image, resolution=target_size)[0]

      # Normalize and create view dict
      view = dict(
        img=ImgNorm(processed_img)[None],
        true_shape=np.int32([processed_img.size[::-1]]),
        idx=i,
        instance=str(i),
        data_norm_type=[norm_type],
      )

      K = prior_intrinsics[i]
      if K is not None:
        transform = mapanything_transform(pil_image.size, target_size)
        K_model = transform.apply_to_intrinsics(K)
        view["intrinsics"] = torch.from_numpy(K_model.astype(np.float32))[None]
        conditioned += 1

      pose = prior_poses[i]
      if pose is not None:
        view["camera_poses"] = torch.from_numpy(pose.astype(np.float32))[None]

      views.append(view)

    log.info(
      f"MapAnything views: {len(views)} images, {conditioned} with intrinsics, "
      f"{sum(1 for p in prior_poses if p is not None)} with poses"
    )
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
