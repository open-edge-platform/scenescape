#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Per-image resize/crop transforms shared by model preprocessing and
intrinsics restoration. Each model's preprocessing is mirrored here so the
same arithmetic maps intrinsics into model pixels and back out again.
"""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class ImageTransform:
  """Anisotropic resize followed by a crop, from original to model pixels."""
  scale_x: float
  scale_y: float
  crop_left: int
  crop_top: int
  model_width: int
  model_height: int

  def apply_to_intrinsics(self, K: np.ndarray) -> np.ndarray:
    """Original-image intrinsics -> model-input intrinsics."""
    out = np.array(K, dtype=np.float64, copy=True)
    out[0, 0] *= self.scale_x
    out[0, 1] *= self.scale_x
    out[0, 2] = out[0, 2] * self.scale_x - self.crop_left
    out[1, 1] *= self.scale_y
    out[1, 2] = out[1, 2] * self.scale_y - self.crop_top
    return out

  def invert_intrinsics(self, K: np.ndarray) -> np.ndarray:
    """Model-input intrinsics -> original-image intrinsics."""
    out = np.array(K, dtype=np.float64, copy=True)
    out[0, 0] /= self.scale_x
    out[0, 1] /= self.scale_x
    out[0, 2] = (out[0, 2] + self.crop_left) / self.scale_x
    out[1, 1] /= self.scale_y
    out[1, 2] = (out[1, 2] + self.crop_top) / self.scale_y
    return out


def mapanything_transform(original_size: tuple, target_size: tuple) -> ImageTransform:
  """Mirror mapanything.utils.cropping.crop_resize_if_necessary without intrinsics.

  Args:
    original_size: (width, height) of the decoded image
    target_size: (width, height) selected from RESOLUTION_MAPPINGS
  """
  orig_w, orig_h = int(original_size[0]), int(original_size[1])
  target_w, target_h = int(target_size[0]), int(target_size[1])
  if orig_w <= 0 or orig_h <= 0:
    raise ValueError(f"Invalid original size {original_size}")

  # Vendor: scale_final = max(output_resolution / image.size) + 1e-8, then floor.
  scale_final = max(target_w / orig_w, target_h / orig_h) + 1e-8
  resized_w = int(math.floor(orig_w * scale_final))
  resized_h = int(math.floor(orig_h * scale_final))
  crop_left = (resized_w - target_w) // 2
  crop_top = (resized_h - target_h) // 2
  return ImageTransform(
    scale_x=resized_w / orig_w,
    scale_y=resized_h / orig_h,
    crop_left=crop_left,
    crop_top=crop_top,
    model_width=target_w,
    model_height=target_h,
  )


def vggt_transform(original_size: tuple, target: int = 518, patch: int = 14) -> ImageTransform:
  """Mirror VGGTModel._preprocess_images: shorter side -> target, round to patch, center crop."""
  orig_w, orig_h = int(original_size[0]), int(original_size[1])
  if orig_w <= 0 or orig_h <= 0:
    raise ValueError(f"Invalid original size {original_size}")

  scale = target / float(min(orig_w, orig_h))
  resized_w = max(target, int(round((orig_w * scale) / patch) * patch))
  resized_h = max(target, int(round((orig_h * scale) / patch) * patch))
  return ImageTransform(
    scale_x=resized_w / orig_w,
    scale_y=resized_h / orig_h,
    crop_left=(resized_w - target) // 2,
    crop_top=(resized_h - target) // 2,
    model_width=target,
    model_height=target,
  )
