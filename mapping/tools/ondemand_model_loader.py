#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand model loader for Scenescape 3D mapping service.
This script downloads the MapAnything and VGGT models only when needed, reducing Docker image size.
Combines model download coordination and individual model management.
"""

import os
import sys

from scene_common import log

from download_mapanything import ensure_mapanything_model
from download_vggt import ensure_vggt_model

def ensure_model() -> bool:
  """
  Ensure all required models exist, downloading them if necessary.

  Returns:
    Dictionary with model names as keys and success status as values
  """
  log.info("3D Mapping Models On-Demand Loader")
  log.info("==================================")

  model_type = os.environ.get("MODEL_TYPE", "").lower()

  if model_type == "mapanything":
    return ensure_mapanything_model()
  elif model_type == "vggt":
    return ensure_vggt_model()
  else:
    return False

def main():
  """Main function for standalone execution."""
  success = ensure_model()
  if success:
    log.info("Required model is available.")
  else:
    log.error("Failed to ensure required model availability.")
  return 0 if success else 1

if __name__ == "__main__":
  sys.exit(main())
