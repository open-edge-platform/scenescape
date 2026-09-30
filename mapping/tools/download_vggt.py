#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand VGGT model loader for Scenescape 3D mapping service.
"""

import sys

from scene_common import log

from model_utils import (
    get_model_weights_dir,
    ensure_cache_directories,
    check_model_exists,
    create_success_marker,
    retry_with_exponential_backoff,
)

MODEL_NAME = "vggt"
MODEL_WEIGHTS_URL = 'https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt'

def download_vggt_model() -> bool:
  """
  Download VGGT model using the installed package with automatic retries.

  Returns:
    True if download successful, False otherwise
  """
  def _download_attempt():
    log.info("Downloading VGGT model...")

    # Add VGGT to Python path (guard against duplicates across retry attempts)
    vggt_path = "/workspace/vggt"
    if vggt_path not in sys.path:
      sys.path.insert(0, vggt_path)

    import torch
    from vggt.models.vggt import VGGT

    # Initialize model (this may trigger some setup)
    VGGT()

    log.info('Downloading VGGT weights from HuggingFace...')
    weights = torch.hub.load_state_dict_from_url(MODEL_WEIGHTS_URL, map_location='cpu')

    log.info('VGGT model downloaded successfully!')
    return weights

  try:
    # Retries cover the network download only; saving weights and marker creation
    # below are local filesystem writes and aren't worth re-downloading to retry.
    weights = retry_with_exponential_backoff(_download_attempt)
  except Exception as e:
    log.error(f'Failed to download VGGT model after retries: {e}')
    return False

  weights_path = get_model_weights_dir() / 'vggt_model.pt'

  import torch
  torch.save(weights, weights_path)
  log.info('VGGT model cached successfully!')

  return create_success_marker(MODEL_NAME, 'VGGT model downloaded successfully')

def ensure_vggt_model() -> bool:
  """
  Ensure VGGT model exists, downloading if necessary.

  Returns:
    True if model is available, False otherwise
  """
  # Ensure cache directories exist
  ensure_cache_directories()

  # Check if model already exists
  if check_model_exists(MODEL_NAME):
    log.info("VGGT model already downloaded.")
    return True

  # Download the model
  return download_vggt_model()

def main():
  """Main function for standalone execution."""
  log.info("VGGT Model Loader")
  log.info("================")

  success = ensure_vggt_model()

  if success:
    log.info("VGGT model is ready for use!")
    return 0
  else:
    log.error("Failed to ensure VGGT model is available")
    return 1

if __name__ == "__main__":
  sys.exit(main())
