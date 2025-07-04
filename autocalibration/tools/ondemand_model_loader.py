#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

"""
On-demand NetVLAD model loader for SceneScape autocalibration.
This script downloads the NetVLAD model only when needed, reducing Docker image size.
"""

import os
import sys
import requests
import logging
from pathlib import Path
from typing import Optional
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configuration
MINIMAL_MODEL_SIZE_MB = 500
NETVLAD_MODEL_URL = "https://cvg-data.inf.ethz.ch/hloc/netvlad/Pitts30K_struct.mat"
NETVLAD_MODEL_NAME = "VGG16-NetVLAD-Pitts30K.mat"
MODEL_DIR = os.getenv("NETVLAD_MODEL_DIR", "/usr/local/lib/python3.10/dist-packages/third_party/netvlad")
NETVLAD_MODEL_MIN_SIZE_MB = MINIMAL_MODEL_SIZE_MB

EXPECTED_SHA256 = "a67d9d897d3b7942f206478e3a22a4c4c9653172ae2447041d35f6cb278fdc67"

def get_model_path() -> Path:
  """Get the full path to the NetVLAD model file."""
  model_dir = Path(MODEL_DIR)
  model_dir.mkdir(parents=True, exist_ok=True)
  return model_dir / NETVLAD_MODEL_NAME

def download_file(url: str, destination: Path, chunk_size: int = 8192) -> bool:
  """
  Download file with progress bar and error handling.

  Args:
    url: URL to download from
    destination: Path where to save the file
    chunk_size: Size of chunks to download

  Returns:
    True if download successful, False otherwise
  """
  try:
    logger.info(f"Downloading NetVLAD model from {url}")
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0

    with open(destination, 'wb') as f:
      for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:
          f.write(chunk)
          downloaded += len(chunk)

          # Show progress
          if total_size > 0:
            progress = (downloaded / total_size) * 100
            sys.stdout.write(f"\rDownloading: {progress:.1f}% ({downloaded}/{total_size} bytes)")
            sys.stdout.flush()

    print()  # New line after progress
    logger.info(f"Download complete: {destination}")
    return True

  except requests.exceptions.RequestException as e:
    logger.error(f"Failed to download model: {e}")
    return False
  except Exception as e:
    logger.error(f"Unexpected error during download: {e}")
    return False

def ensure_model_exists() -> Optional[Path]:
  """
  Ensure the NetVLAD model exists, downloading it if necessary.

  Returns:
    Path to the model file if successful, None otherwise
  """
  model_path = get_model_path()

  # Check if model already exists
  if model_path.exists():
    logger.info(f"NetVLAD model already exists at {model_path}")
    return model_path

  # Download the model
  logger.info(f"NetVLAD model not found. Starting download...")
  if download_file(NETVLAD_MODEL_URL, model_path):
    return model_path
  else:
    logger.error("Failed to download NetVLAD model")
    return None

def sha256sum(filename: Path) -> str:
  h = hashlib.sha256()
  with filename.open('rb') as f:
    for chunk in iter(lambda: f.read(4096), b""):
      h.update(chunk)
  return h.hexdigest()

def check_model_integrity(model_path: Path) -> bool:
  try:
    if not model_path.exists():
      return False
    actual_sha256 = sha256sum(model_path)
    if actual_sha256 != EXPECTED_SHA256:
      logger.warning(f"Model checksum mismatch: {actual_sha256} (expected: {EXPECTED_SHA256})")
      # Delete the corrupted file so it can be re-downloaded
      model_path.unlink(missing_ok=True)
      return False
    logger.info(f"Model integrity check passed: {actual_sha256}")
    return True
  except Exception as e:
    logger.error(f"Error checking model integrity: {e}")
    # Optionally try to delete the file on error as well
    try:
      model_path.unlink(missing_ok=True)
    except Exception:
      pass
    return False

def main():
  """Main function for standalone execution."""
  logger.info("NetVLAD On-Demand Model Loader")

  model_path = ensure_model_exists()
  if model_path is None:
    logger.error("Failed to ensure model exists")
    sys.exit(1)

  if not check_model_integrity(model_path):
    logger.error("Model integrity check failed")
    sys.exit(1)

  logger.info("NetVLAD model is ready for use")
  return model_path

if __name__ == "__main__":
  main()
