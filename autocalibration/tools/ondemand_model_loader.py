#!/usr/bin/env python3
"""
On-demand NetVLAD model loader for SceneScape autocalibration.
This script downloads the NetVLAD model only when needed, reducing Docker image size.
Handles race conditions and partial downloads safely.
"""

import os
import sys
import time
import fcntl
import requests
import logging
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configuration
MINIMAL_MODEL_SIZE_MB = 500
NETVLAD_MODEL_URL = "https://cvg-data.inf.ethz.ch/hloc/netvlad/Pitts30K_struct.mat"
NETVLAD_MODEL_NAME = "VGG16-NetVLAD-Pitts30K.mat"
MODEL_DIR = os.getenv("NETVLAD_MODEL_DIR", "/usr/local/lib/python3.10/dist-packages/third_party/netvlad")
NETVLAD_MODEL_MIN_SIZE_MB = MINIMAL_MODEL_SIZE_MB

def get_model_path() -> Path:
  """Get the full path to the NetVLAD model file."""
  model_dir = Path(MODEL_DIR)
  model_dir.mkdir(parents=True, exist_ok=True)
  return model_dir / NETVLAD_MODEL_NAME

def get_lock_path() -> Path:
  model_dir = Path(MODEL_DIR)
  model_dir.mkdir(parents=True, exist_ok=True)
  return model_dir / f"{NETVLAD_MODEL_NAME}.lock"

def acquire_download_lock(lock_path: Path, timeout: int = 300) -> Optional[object]:
  try:
    lock_file = open(lock_path, 'w')
    start_time = time.time()
    while time.time() - start_time < timeout:
      try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info("Acquired download lock")
        return lock_file
      except (IOError, OSError):
        logger.info("Another process is downloading the model, waiting...")
        time.sleep(1)
    lock_file.close()
    logger.error("Timeout waiting for download lock")
    return None
  except Exception as e:
    logger.error(f"Error acquiring lock: {e}")
    return None

def release_download_lock(lock_file: object, lock_path: Path):
  try:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()
    lock_path.unlink(missing_ok=True)
    logger.info("Released download lock")
  except Exception as e:
    logger.warning(f"Error releasing lock: {e}")

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
    temp_destination = destination.with_suffix('.tmp')

    with open(temp_destination, 'wb') as f:
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
    if total_size > 0 and downloaded != total_size:
      logger.error(f"Download incomplete: {downloaded}/{total_size} bytes")
      temp_destination.unlink(missing_ok=True)
      return False
    temp_destination.rename(destination)
    logger.info(f"Download complete: {destination}")
    return True

  except requests.exceptions.RequestException as e:
    logger.error(f"Failed to download model: {e}")
    temp_destination.unlink(missing_ok=True)
    return False
  except Exception as e:
    logger.error(f"Unexpected error during download: {e}")
    temp_destination.unlink(missing_ok=True)
    return False

def ensure_model_exists() -> Optional[Path]:
  """
  Ensure the NetVLAD model exists, downloading it if necessary.

  Returns:
    Path to the model file if successful, None otherwise
  """
  model_path = get_model_path()
  lock_path = get_lock_path()
  # First, check if we have a valid model
  if model_path.exists() and check_model_integrity(model_path):
    logger.info(f"NetVLAD model already exists and is valid at {model_path}")
    return model_path
  # Check for partial/corrupted file
  if model_path.exists():
    file_size = model_path.stat().st_size
    min_size_bytes = NETVLAD_MODEL_MIN_SIZE_MB * 1024 * 1024
    if file_size < min_size_bytes:
      logger.warning(f"Found partial/corrupted model file ({file_size} bytes), removing it")
      model_path.unlink()
    else:
      logger.warning(f"Model file exists but failed integrity check, removing it")
      model_path.unlink()
  # Try to acquire download lock
  lock_file = acquire_download_lock(lock_path)
  if lock_file is None:
    logger.info("Waiting for another process to complete download...")
    max_wait = 300
    start_time = time.time()
    while time.time() - start_time < max_wait:
      time.sleep(2)
      if model_path.exists() and check_model_integrity(model_path):
        logger.info("Model was downloaded by another process")
        return model_path
    logger.error("Timeout waiting for model download")
    return None
  try:
    if model_path.exists() and check_model_integrity(model_path):
      logger.info("Model was downloaded by another process while waiting for lock")
      return model_path
    logger.info(f"NetVLAD model not found. Starting download...")
    if download_file(NETVLAD_MODEL_URL, model_path):
      if check_model_integrity(model_path):
        return model_path
      else:
        logger.error("Downloaded model failed integrity check")
        model_path.unlink(missing_ok=True)
        return None
    else:
      logger.error("Failed to download NetVLAD model")
      return None
  finally:
    release_download_lock(lock_file, lock_path)

def check_model_integrity(model_path: Path) -> bool:
  """
  Basic integrity check for the downloaded model.

  Args:
    model_path: Path to the model file

  Returns:
    True if model appears valid, False otherwise
  """
  try:
    if not model_path.exists():
      return False

    # Check file size (should be around 554MB)
    file_size = model_path.stat().st_size
    if file_size < NETVLAD_MODEL_MIN_SIZE_MB * 1024 * 1024:
      logger.warning(f"Model file seems too small: {file_size} bytes")
      return False

    logger.info(f"Model integrity check passed: {file_size} bytes")
    return True

  except Exception as e:
    logger.error(f"Error checking model integrity: {e}")
    return False

def main():
  """Main function for standalone execution."""
  logger.info("NetVLAD On-Demand Model Loader")

  model_path = ensure_model_exists()
  if model_path is None:
    logger.error("Failed to ensure model exists")
    sys.exit(1)

  logger.info("NetVLAD model is ready for use")
  return model_path

if __name__ == "__main__":
  main()
