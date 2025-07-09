# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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

def verify_image_set(files_list, basefilename):
  """! Check if rgb, depth and camera folders exist and the number of
       files in them match.

  @param    file_list      List of file names in the uploaded zip file.
  @param    basefilename   Root folder name of the zip file uploaded.
  @return   boolean
  """
  if len(list(filter(lambda v: re.match(f"{basefilename}/keyframes", v),
                     files_list))) == 0:
    return False
  images_list = [file for file in files_list if basefilename + "/keyframes/images" in
                 file and file.endswith(".jpg")]
  depth_list = [file for file in files_list if basefilename + "/keyframes/depth" in
                file and file.endswith(".png")]
  camera_json_list = [file for file in files_list if basefilename + "/keyframes/cameras"
                      in file and file.endswith(".json")]
  return (len(images_list) == len(depth_list) == len(camera_json_list))

def poly_datasets(filenames):
  """! Filter for polycam dataset folders"""
  folders = {filename.split('/')[0] for filename in filenames}
  return [folder for folder in folders if '-poly' in folder]

def is_polycam_dataset(basefilename, filenames):
  """! Verify required polycam dataset structure.

  @param  basefilename   Dataset files path prefix
  @param  filenames      List of files in the dataset zip file
  @return boolean        Is the input a valid polycam dataset
  """
  return (basefilename + "/raw.glb" in filenames and
    basefilename + "/mesh_info.json" in filenames and
    verify_image_set(filenames, basefilename))

def validate_zip_file(value):
  """! Validate the polycam zip file uploaded via Scene update.

  @param  value   Django File Field.
  @return value   Django File Field after validation or Validation error.
  """
  ext = os.path.splitext(value.name)[1].lower()
  if ext == ".zip":
    filenames = ZipFile(value, "r").namelist()
    datasets = poly_datasets(filenames)
    if len(datasets)==0:
      raise ValidationError('Zip file contains no polycam dataset')
    if len(datasets)>1:
      raise ValidationError("Zip file contains multiple polycam datasets")
    if not is_polycam_dataset(datasets[0], filenames):
      raise ValidationError("Invalid or unexpected dataset format.")

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
