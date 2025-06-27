# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import tempfile

from django.core.exceptions import ValidationError
from PIL import Image
from zipfile import ZipFile
import open3d as o3d
import os
import cv2
import re
import uuid


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
