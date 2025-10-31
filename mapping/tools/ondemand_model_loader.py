#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand model loader for SceneScape 3D mapping service.
This script downloads the MapAnything and VGGT models only when needed, reducing Docker image size.
Combines model download coordination and individual model management.
"""

import sys
from typing import Dict

from scene_common import log

from download_mapanything import ensureMapanythingModel
from download_vggt import ensureVGGTModel

def ensureAllModels() -> Dict[str, bool]:
  """
  Ensure all required models exist, downloading them if necessary.

  Returns:
    Dictionary with model names as keys and success status as values
  """
  log.info("3D Mapping Models On-Demand Loader")
  log.info("==================================")

  results = {}

  # Download MapAnything model
  log.info("Checking MapAnything model...")
  results["mapanything"] = ensureMapanythingModel()

  # Download VGGT model
  log.info("Checking VGGT model...")
  results["vggt"] = ensureVGGTModel()

  return results

def main():
  """Main function for standalone execution."""
  results = ensureAllModels()

  success_count = sum(1 for success in results.values() if success)
  total_models = len(results)

  log.info(f"\nModel Download Summary:")
  log.info(f"======================")

  for model_name, success in results.items():
    status = "✓ SUCCESS" if success else "✗ FAILED"
    log.info(f"  - {model_name.capitalize()}: {status}")

  if success_count == total_models:
    log.info(f"\nAll {total_models} models initialized successfully!")
    return 0
  else:
    log.error(f"\nFailed to initialize {total_models - success_count} out of {total_models} models")
    for model_name, success in results.items():
      if not success:
        log.error(f"  - {model_name}: FAILED")
    return 1

if __name__ == "__main__":
  sys.exit(main())
