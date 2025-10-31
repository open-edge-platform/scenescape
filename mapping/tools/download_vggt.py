#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand VGGT model loader for SceneScape 3D mapping service.
"""

import sys

from scene_common import log

from model_utils import getModelWeightsDir, ensureCacheDirectories, checkModelExists, createSuccessMarker

MODEL_NAME = "vggt"

def downloadVGGTModel() -> bool:
  """
  Download VGGT model using the installed package.

  Returns:
    True if download successful, False otherwise
  """
  try:
    log.info("Downloading VGGT model...")

    # Add VGGT to Python path
    vggt_path = "/workspace/vggt"
    sys.path.insert(0, str(vggt_path))

    import torch
    from vggt.models.vggt import VGGT

    # Initialize model (this may trigger some setup)
    model = VGGT()

    # Download model weights
    _URL = 'https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt'
    log.info('Downloading VGGT weights from HuggingFace...')

    weights = torch.hub.load_state_dict_from_url(_URL, map_location='cpu')

    # Save weights locally for faster future access
    weights_path = getModelWeightsDir() / 'vggt_model.pt'
    torch.save(weights, weights_path)

    # Create success marker
    success_message = 'VGGT model downloaded successfully'
    if not createSuccessMarker(MODEL_NAME, success_message):
      return False

    log.info('VGGT model downloaded and cached successfully!')
    return True

  except Exception as e:
    log.error(f'Failed to download VGGT model: {e}')
    return False

def ensureVGGTModel() -> bool:
  """
  Ensure VGGT model exists, downloading if necessary.

  Returns:
    True if model is available, False otherwise
  """
  # Ensure cache directories exist
  ensureCacheDirectories()

  # Check if model already exists
  if checkModelExists(MODEL_NAME):
    log.info("VGGT model already downloaded.")
    return True

  # Download the model
  return downloadVGGTModel()

def main():
  """Main function for standalone execution."""
  log.info("VGGT Model Loader")
  log.info("================")

  success = ensureVGGTModel()

  if success:
    log.info("VGGT model is ready for use!")
    return 0
  else:
    log.error("Failed to ensure VGGT model is available")
    return 1

if __name__ == "__main__":
  sys.exit(main())
