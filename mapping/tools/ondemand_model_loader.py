#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
On-demand model loader for SceneScape 3D mapping service.
This script downloads the MapAnything and VGGT models only when needed, reducing Docker image size.
Combines model download coordination and individual model management.
"""

import os
import re
import sys

from scene_common import log

from download_mapanything import ensureMapanythingModel
from download_vggt import ensureVGGTModel

def _sanitize_no_proxy():
  """Fix malformed no_proxy entries where host:port syntax used a dot-prefix
  domain as the port (e.g. '.svc.cluster.local:.scenescape.intel.com').
  Such entries cause urllib3 to raise 'Invalid port' errors.
  """
  for var in ('no_proxy', 'NO_PROXY'):
    value = os.environ.get(var, '')
    if not value:
      continue
    cleaned = re.sub(r'([^,]+):(\.[^,]+)', r'\1,\2', value)
    if cleaned != value:
      os.environ[var] = cleaned

def ensureModel() -> bool:
  """
  Ensure all required models exist, downloading them if necessary.

  Returns:
    Dictionary with model names as keys and success status as values
  """
  log.info("3D Mapping Models On-Demand Loader")
  log.info("==================================")

  model_type = os.environ.get("MODEL_TYPE", "").lower()

  if model_type == "mapanything":
    return ensureMapanythingModel()
  elif model_type == "vggt":
    return ensureVGGTModel()
  else:
    return False

def main():
  """Main function for standalone execution."""
  _sanitize_no_proxy()
  success = ensureModel()
  if success:
    log.info("Required model is available.")
  else:
    log.error("Failed to ensure required model availability.")
  return 0 if success else 1

if __name__ == "__main__":
  sys.exit(main())
