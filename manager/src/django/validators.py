# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import re
import tempfile
import uuid
from zipfile import ZipFile

from django.core.exceptions import ValidationError
import open3d as o3d
from PIL import Image

def validate_glb(value):
  with tempfile.NamedTemporaryFile(suffix=".glb") as glb_file:
    glb_file.write(value.read())
    mesh = o3d.io.read_triangle_model(glb_file.name)
    if len(mesh.meshes) == 0 or mesh.materials[0].shader is None:
      raise ValidationError("Only valid glTF binary (.glb) files are supported for 3D assets.")
    return value

def validate_image(value):
  with Image.open(value) as img:
    try:
      img.verify()
    except Exception as e:
      raise ValidationError(f'Failed to read image file.{e}')
    header = img.format.lower()
    extension = os.path.splitext(value.name)[1].lower()[1:]
    extension = "jpeg" if extension == "jpg" else extension
    if header != extension:
      raise ValidationError(f"Mismatch between file extension {extension} and file header {header}")
  return value

def validate_map_file(value):
  ext = os.path.splitext(value.name)[1].lower()[1:]
  if ext == "glb":
    validate_glb(value)
  elif ext == "zip":
    validate_zip_file(value)
  elif ext in ["jpg", "jpeg", "png"]:
    validate_image(value)
  return

def add_form_error(error, form):
  error = error.args[0]
  key = error[error.find('(') + 1: error.find(')')]
  form.add_error(key, "Sensor with this {} already exists.".format(key.capitalize()))
  return form

def poly_datasets(filenames, is_map_glb):
  """! Filter for polycam dataset folders"""
  if not filenames:
    return [], ["Empty zip file"]
  folders = set()
  for f in filenames:
    if '/' in f:
      tf = f.split('/')[0]
    if tf != "keyframes":
      folders.add(tf)

  valid_datasets, error = [], None
  if not folders:
    folders = {""}
  for folder in folders:
    is_valid, error_msg = is_polycam_dataset(folder, filenames, is_map_glb)
    if is_valid:
      valid_datasets.append(folder)
    elif error_msg:
      error = f"{folder}: {error_msg}"
      return [], [error]
  return valid_datasets, error

def is_polycam_dataset(basefilename, filenames, is_map_glb):
  """! Verify required polycam dataset structure.

  @param  basefilename   Dataset files path prefix
  @param  filenames      List of files in the dataset zip file
  @return boolean        Is the input a valid polycam dataset
  """
  prefix = f"{basefilename}/" if basefilename else ""

  if f"{prefix}mesh_info.json" not in filenames:
    return False, f"Missing {prefix}mesh_info.json file"

  if not is_map_glb and f"{prefix}raw.glb" not in filenames:
    return False, f"Missing {prefix}raw.glb file. This is required unless map is a glb file."

  keyframes = [f for f in filenames if f.startswith(f"{prefix}keyframes/")]
  if not keyframes:
    return False, "Missing keyframes folder"

  images = [f for f in keyframes if "/images/" in f and f.endswith(".jpg")]
  depth = [f for f in keyframes if "/depth/" in f and f.endswith(".png")]
  cameras = [f for f in keyframes if "/cameras/" in f and f.endswith(".json")]

  counts = [len(images), len(depth), len(cameras)]
  if not (counts[0] == counts[1] == counts[2] > 0):
    return False, f"Image count mismatch: {counts[0]} images, {counts[1]} depth, {counts[2]} cameras"

  return True, None

def validate_zip_file(value, is_map_glb=False):
  """! Validate the polycam zip file uploaded via Scene update.

  @param  value   Django File Field.
  @return value   Django File Field after validation or Validation error.
  """
  ext = os.path.splitext(value.name)[1].lower()
  if ext == ".zip":
    filenames = ZipFile(value, "r").namelist()
    error = "Zip file contains no polycam dataset"
    datasets, error = poly_datasets(filenames, is_map_glb)
    if not datasets:
      raise ValidationError(error)
    if len(datasets) > 1:
      raise ValidationError(f"Zip file contains multiple polycam datasets")
  return value

def validate_uuid(value):
  try:
    check_uuid = uuid.UUID(value)
    return True
  except ValueError:
    return False

def validate_map_corners_lla(value):
  """
  Validates that map_corners_lla is an array containing exactly 4 corner coordinates.
  Each corner should be [latitude, longitude, altitude] where:
  - latitude: -90 to 90 degrees
  - longitude: -180 to 180 degrees
  - altitude: any numeric value (meters)
  """
  if value is None:
    return  # Allow None values since field is nullable
  if not isinstance(value, list):
    raise ValidationError("map_corners_lla must be a JSON array of coordinates.")
  if len(value) != 4:
    raise ValidationError("map_corners_lla must contain exactly 4 corner coordinates.")

  for i, corner in enumerate(value):
    if not isinstance(corner, list) or len(corner) != 3:
      raise ValidationError(f"Corner {i+1} must be an array of [latitude, longitude, altitude].")
    try:
      lat, lon, alt = float(corner[0]), float(corner[1]), float(corner[2])
    except (ValueError, TypeError):
      raise ValidationError(f"Corner {i+1} coordinates must be numeric values.")
    if not (-90 <= lat <= 90):
      raise ValidationError(f"Corner {i+1} latitude ({lat}) must be between -90 and 90 degrees.")
    if not (-180 <= lon <= 180):
      raise ValidationError(f"Corner {i+1} longitude ({lon}) must be between -180 and 180 degrees.")

  return value
