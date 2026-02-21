#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Model Interface for 3D Reconstruction Models
Defines the interface for different 3D reconstruction models.

Note: Model selection is done at build-time. Each service container
is built with a specific model (MapAnything or VGGT).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

import base64
import cv2
import numpy as np
import os
import subprocess
import math
import tempfile

from scene_common import log

class ReconstructionModel(ABC):
  """
  Abstract base class for 3D reconstruction models.

  This interface defines the standard API that all 3D reconstruction models
  must implement to be used with the mapping service.

  Model instances are created directly by the service-specific containers
  (mapanything-service, vggt-service) at initialization time.
  """

  def __init__(self, model_name: str, description: str, device: str = "cpu"):
    """
    Initialize the reconstruction model.

    Args:
      model_name: Unique identifier for the model
      description: Human-readable description of the model
      device: Device to run inference on ("cpu" or "cuda")
    """
    self.model_name = model_name
    self.description = description
    self.device = device
    self.model = None
    self.is_loaded = False

    log.info(f"Initializing {model_name} on device: {device}")

  @abstractmethod
  def loadModel(self) -> None:
    """
    Load the model and its weights.

    Raises:
      RuntimeError: If model loading fails
    """
    raise NotImplementedError

  @abstractmethod
  def runInference(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run 3D reconstruction inference on input images.

    Args:
      images: List of image dictionaries containing:
        - data: Base64 encoded image data
        - (optional) metadata like filename, timestamp, etc.

    Returns:
      Dictionary containing:
        - predictions: Model-specific predictions dict
        - camera_poses: List of camera poses (camera-to-world transformations)
          - Each pose has "rotation" (quaternion [w,x,y,z]) and "translation" ([x,y,z])
        - intrinsics: List of camera intrinsic matrices (3x3) for original image sizes

    Raises:
      RuntimeError: If inference fails
      ValueError: If input data is invalid
    """
    raise NotImplementedError

  @abstractmethod
  def getSupportedOutputs(self) -> List[str]:
    """
    Get list of supported output formats for this model.

    Returns:
      List of supported output types (e.g., ["mesh", "pointcloud"])
    """
    raise NotImplementedError

  @abstractmethod
  def getNativeOutput(self) -> str:
    """
    Get the native/preferred output format for this model.

    Returns:
      String indicating native output type ("mesh" or "pointcloud")
    """
    raise NotImplementedError

  @abstractmethod
  def scaleIntrinsicsToOriginalSize(self, intrinsics: np.ndarray, model_size: tuple, original_sizes: list,
                   preprocessing_mode: str = "crop") -> list:
    """Scale intrinsics matrices from model input size back to original image dimensions.

    Args:
      intrinsics: Numpy array of intrinsics matrices (S, 3, 3)
      model_size: Tuple of (height, width) that model used
      original_sizes: List of tuples [(orig_width_0, orig_height_0), ...]
      preprocessing_mode: How images were preprocessed ("crop" or "pad")

    Returns:
      List of scaled intrinsics matrices for original image sizes
    """
    raise NotImplementedError

  @abstractmethod
  def createOutput(self, result: Dict[str, Any], output_format: str = None) -> 'trimesh.Scene':
    """
    Create 3D output scene from model results.

    Args:
      result: Result dictionary from runInference
      output_format: Desired output format ('mesh' or 'pointcloud').
              If None, uses the model's native output format.

    Returns:
      trimesh.Scene: Processed 3D scene ready for export

    Raises:
      ValueError: If output_format is not supported by this model
      RuntimeError: If output generation fails
    """
    raise NotImplementedError

  def isModelLoaded(self) -> bool:
    """
    Check if the model is loaded and ready for inference.

    Returns:
      True if model is loaded, False otherwise
    """
    return self.is_loaded

  def getModelInfo(self) -> Dict[str, Any]:
    """
    Get information about the model.

    Returns:
      Dictionary containing model metadata
    """
    return {
      "name": self.model_name,
      "description": self.description,
      "device": self.device,
      "loaded": self.is_loaded,
      "native_output": self.getNativeOutput(),
      "supported_outputs": self.getSupportedOutputs()
    }

  def validateImages(self, images: List[Dict[str, Any]]) -> None:
    """
    Validate input image data structure.

    Args:
      images: List of image dictionaries to validate

    Raises:
      ValueError: If image data is invalid
    """
    if not isinstance(images, list) or len(images) == 0:
      raise ValueError("Images must be a non-empty list")

    for i, img in enumerate(images):
      if not isinstance(img, dict):
        raise ValueError(f"Image {i} must be a dictionary")
      if 'data' not in img:
        raise ValueError(f"Image {i} missing required field: data")
      if not isinstance(img['data'], str):
        raise ValueError(f"Image {i} data must be a base64 string")

  def decodeBase64Image(self, image_data: str) -> np.ndarray:
    """
    Decode base64 image data to numpy array.

    Args:
      image_data: Base64 encoded image string

    Returns:
      Image as numpy array (H, W, 3) in RGB format

    Raises:
      ValueError: If image decoding fails
    """
    import base64
    import io
    from PIL import Image

    try:
      # Remove data URL prefix if present
      if image_data.startswith('data:image'):
        image_data = image_data.split(',')[1]

      # Decode base64
      img_bytes = base64.b64decode(image_data)

      # Convert to PIL Image
      pil_image = Image.open(io.BytesIO(img_bytes))

      # Convert to RGB if needed
      if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')

      # Convert to numpy array
      img_array = np.array(pil_image)

      return img_array

    except Exception as e:
      raise ValueError(f"Failed to decode image data: {e}")

  def _applyCLAHE(self, img_array: np.ndarray, clip_limit: float = 2.0, tile_grid_size: tuple = (8, 8)) -> np.ndarray:
    """
    Apply Contrast Limited Adaptive Histogram Equalization (CLAHE) to improve image contrast.

    Args:
      img_array: RGB image array (H, W, 3)
      clip_limit: Threshold for contrast limiting (default: 2.0)
      tile_grid_size: Size of grid for histogram equalization (default: 8x8)

    Returns:
      CLAHE-enhanced image array
    """
    # Convert RGB to LAB color space for better color preservation
    lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)

    # Apply CLAHE to L channel (lightness)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])

    # Convert back to RGB
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    return enhanced

  def rotationMatrixToQuaternion(self, R: np.ndarray) -> np.ndarray:
    """
    Convert a 3x3 rotation matrix to a quaternion [x, y, z, w].

    Args:
      R: 3x3 rotation matrix (numpy array)

    Returns:
      Quaternion as [x, y, z, w] (numpy array)
    """
    # Ensure the matrix is valid
    R = np.array(R, dtype=np.float64)

    # Shepperd's method for robust quaternion extraction
    trace = np.trace(R)

    if trace > 0:
      s = np.sqrt(trace + 1.0) * 2  # s = 4 * qw
      w = 0.25 * s
      x = (R[2, 1] - R[1, 2]) / s
      y = (R[0, 2] - R[2, 0]) / s
      z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
      s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2  # s = 4 * qx
      w = (R[2, 1] - R[1, 2]) / s
      x = 0.25 * s
      y = (R[0, 1] + R[1, 0]) / s
      z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
      s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2  # s = 4 * qy
      w = (R[0, 2] - R[2, 0]) / s
      x = (R[0, 1] + R[1, 0]) / s
      y = 0.25 * s
      z = (R[1, 2] + R[2, 1]) / s
    else:
      s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2  # s = 4 * qz
      w = (R[1, 0] - R[0, 1]) / s
      x = (R[0, 2] + R[2, 0]) / s
      y = (R[1, 2] + R[2, 1]) / s
      z = 0.25 * s

    return np.array([x, y, z, w])

  def _maxFramesForTimeBudget(
    self,
    time_budget_seconds: float,
    overhead: float,
  ) -> int:

    cpu_sec_per_frame = float(os.getenv("MAPPING_CPU_SEC_PER_FRAME", "10"))
    cuda_sec_per_frame = float(os.getenv("MAPPING_CUDA_SEC_PER_FRAME", "0.8"))
    sec_per_frame = cpu_sec_per_frame
    if self.device.startswith("cuda") and cuda_sec_per_frame:
      sec_per_frame = cuda_sec_per_frame

    usable = max(0.0, time_budget_seconds - overhead)
    if usable <= 0:
      return 0

    # conservative: floor
    max_frames = int(math.floor(usable / max(1e-6, sec_per_frame)))
    return max_frames

  def _framesFromVideoAsBase64Dicts(
    self,
    video_path: str,
    max_frames: int,
    use_keyframes: bool = True,
    sample_every_n: int = 10,
    jpeg_quality: int = 85,
    max_side: Optional[int] = 960,
  ) -> List[Dict[str, Any]]:
    """
    Extract frames using ffmpeg and return:
      [{"data": "<base64-encoded-jpeg>"}, ...]

    Modes:
      - use_keyframes=True: extract TRUE keyframes (I-frames)
      - use_keyframes=False: sample every N frames using select filter
    """
    if max_frames < 1:
      return []

    if not os.path.isfile(video_path):
      raise ValueError(f"Video file not found: {video_path}")

    if sample_every_n < 1:
      sample_every_n = 1

    # Map jpeg_quality (1..100) -> ffmpeg mjpeg qscale (2..31), where 2 is best quality
    qscale = int(round(31 - (np.clip(jpeg_quality, 1, 100) / 100.0) * 29))
    qscale = int(np.clip(qscale, 2, 31))

    vf_parts: List[str] = []

    # If not keyframes, use select filter to sample frames
    if not use_keyframes:
      # keep frames where n % sample_every_n == 0
      vf_parts.append(f"select='not(mod(n\\,{sample_every_n}))'")
    else:
      log.info("Using key frames")

    # Optional downscale: keep aspect ratio, cap longest side
    if max_side is not None and max_side > 0:
      vf_parts.append(
        f"scale='if(gte(iw,ih),min(iw,{max_side}),-2)':'if(lt(iw,ih),min(ih,{max_side}),-2)'"
      )

    vf = ",".join(vf_parts) if vf_parts else None

    frames: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="frames_") as tmpdir:
      out_pattern = os.path.join(tmpdir, "frame_%06d.jpg")

      cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
      ]

      # Keyframes mode: only decode keyframes
      if use_keyframes:
        cmd += ["-skip_frame", "nokey"]

      cmd += ["-i", video_path]

      if vf:
        cmd += ["-vf", vf]

      cmd += [
        "-vsync", "vfr",
        "-frames:v", str(max_frames),
        "-q:v", str(qscale),
        out_pattern,
      ]

      try:
        subprocess.run(cmd, check=True)
      except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg in the container/host.")
      except subprocess.CalledProcessError as e:
        mode = "keyframes" if use_keyframes else f"sample_every_n={sample_every_n}"
        raise RuntimeError(f"ffmpeg failed extracting frames ({mode}): {e}")

      # Read extracted frames back into base64
      for i in range(1, max_frames + 1):
        fpath = os.path.join(tmpdir, f"frame_{i:06d}.jpg")
        if not os.path.exists(fpath):
          break
        with open(fpath, "rb") as f:
          frames.append({"data": base64.b64encode(f.read()).decode("utf-8")})

    return frames
