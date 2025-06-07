# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import json
import os
import shutil
from argparse import ArgumentParser
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

CAMERA_MODEL = "SIMPLE_PINHOLE"
Y_UP_TO_Y_DOWN = np.array([[1, 0, 0, 0],
                           [0, -1, 0, 0],
                           [0, 0, -1, 0],
                           [0, 0, 0, 1]])
IMAGES_TXT_COL_HEADER = "#image_name camera_id qx qy qz qw tx ty tz" + '\n'
CAMERA_TXT_COL_HEADER = "#camera_id model width height params \n"

def prepareCamerasInput(camera_intrinsics, dataset_dir, output_dir):
  """! Creates a cameras.txt file in the dataset storing necessary camera
       intrinsic data.
  @param   camera_intrinsics  Camera Intrinsic values obtained from
                              polycam dataset.
  @param   dataset_dir        Path of the dataset with rbg and depth images.
  @param   output_dir         Path of the directory containing extracted features.

  """
  output_file = Path(output_dir) / "cameras.txt"
  with open(output_file, 'w') as f:
    f.write(CAMERA_TXT_COL_HEADER)
    f.write(' '.join(camera_intrinsics.values()) + '\n')
  shutil.copyfile(output_file, f"{dataset_dir}/cameras.txt")
  shutil.copyfile(output_file, f"{dataset_dir}/rgb/cameras.txt")

  return

def prepareImagesInput(images_dict, output_dir, dataset_dir):
  """! Creates a images.txt file in the dataset based on the cameras.json files.

  @param   images_dict        Dictionary containing the rotation and translation
                              values from the json files.
  @param   dataset_dir        Path of the dataset with rbg and depth images.
  @param   output_dir         Path of the directory containing extracted features.

  """
  output_file = Path(output_dir) / "images.txt"
  rgb_images_path = Path(dataset_dir) / "rgb"
  images = rgb_images_path.glob("*.jpg")
  with open(output_file, 'w') as f:
    f.write(IMAGES_TXT_COL_HEADER)
    for img in images:
      f.write('rgb/' + str(img.stem) + '.jpg' + ' 1 ' +
              ' '.join(images_dict[img.stem]['quaternion']) + ' ' +
              ' '.join(images_dict[img.stem]['translation']) + '\n')
  shutil.copyfile(output_file, f"{dataset_dir}/images.txt")
  shutil.copyfile(output_file, f"{dataset_dir}/rgb/images.txt")

  return

def getGlbToCameraTransform(rw_to_glbw, cam_to_rw):
  """! Get Glb pose in camera coordinate system.

  @param rw_to_glbw   Glb extrinsics in real world.
  @param cam_to_rw    Camera pose in real world.

  @returns quaternions and translation values.
  """
  cam_to_glbw_ydown = rw_to_glbw @ cam_to_rw @ Y_UP_TO_Y_DOWN
  glbw_to_cam_ydown = np.linalg.inv(cam_to_glbw_ydown)
  quaternion = Rotation.from_matrix(glbw_to_cam_ydown[0:3, 0:3]).as_quat()
  translation = np.ravel(glbw_to_cam_ydown[0:3, 3:4].flatten())

  return quaternion, translation

def obtainImagesDataFromJson(mesh_data, camera_json_files):
  """! Prepare image poses and camera intrinsics to be written to
       cameras.txt and images.txt in output_dir.
  @param  mesh_data           Data from mesh_info.json file in polycam dataset.
  @param  camera_json_files   Data from camera.json files in polycam dataset.

  @return Camera_intrinsics and each image's rotaion and translation
          data in dictionary format.
  """
  images_rw_data = {}
  camera_intrinsics = {}
  rw_to_glbw = np.mat(mesh_data['alignmentTransform'])
  rw_to_glbw = rw_to_glbw.reshape(4, 4).T  #  since poses are row-major
  for file in camera_json_files:
    with open(file, 'r') as f:
      data = json.load(f)
      if camera_intrinsics == {}:
        camera_intrinsics['camera_id'] = "1"
        camera_intrinsics['model'] = CAMERA_MODEL
        camera_intrinsics['width'] = str(data.get('width'))
        camera_intrinsics['height'] = str(data.get('height'))
        camera_intrinsics['fx'] = str(data.get('fx'))
        camera_intrinsics['cx'] = str(data.get('cx'))
        camera_intrinsics['cy'] = str(data.get('cy'))

      images_rw_data[file.stem] = {}
      cam_to_rw = np.array([
                           [data['t_00'], data['t_01'],
                            data['t_02'], data['t_03']],
                           [data['t_10'], data['t_11'],
                            data['t_12'], data['t_13']],
                           [data['t_20'], data['t_21'],
                            data['t_22'], data['t_23']],
                           [0, 0, 0, 1]
                           ])
      quaternion, translation = getGlbToCameraTransform(rw_to_glbw,
                                                              cam_to_rw)
      images_rw_data[file.stem]['quaternion'] = list(map(str, quaternion))
      images_rw_data[file.stem]['translation'] = list(map(str, translation))

  return camera_intrinsics, images_rw_data

def transformDataset(polycam_dir, output_dir=None):
  """! Transforms the polycam raw output into required input format for reloc
  @param   polycam_dir  polycam raw output directory
  @param   output_dir   reloc input directory

  @return  None
  """
  key_frames_folder = Path(polycam_dir) / "keyframes"
  if not os.path.exists(Path(polycam_dir) / "depth"):
    shutil.move(Path(key_frames_folder) / "depth",
                Path(polycam_dir))
  if not os.path.exists(Path(polycam_dir) / "rgb"):
    if not os.path.exists(Path(polycam_dir) / "images"):
      shutil.move(Path(key_frames_folder) / "images",
                  Path(polycam_dir) / "rgb")
    elif os.path.exists(Path(polycam_dir) / "images"):
      shutil.move(Path(polycam_dir) / "images",
                  Path(polycam_dir) / "rgb")

  if not os.path.exists(Path(output_dir)):
    os.mkdir(Path(output_dir))
  mesh_info_file = Path(polycam_dir) / "mesh_info.json"
  camera_dir = Path(key_frames_folder) / "cameras"
  camera_json_files = camera_dir.glob("*.json")
  with open(mesh_info_file, 'r') as f:
    mesh_data = json.load(f)

  retain = ["rgb",
            "depth",
            "mesh_info.json",
            "images.txt",
            "cameras.txt",
            "raw.glb",
            "keyframes"]
  for item in os.listdir(Path(polycam_dir)):
    full_path = os.path.join(Path(polycam_dir), item)
    if os.path.exists(full_path) and item not in retain:
      if os.path.isfile(full_path):
        os.remove(full_path)
      else:
        shutil.rmtree(full_path)

  camera_intrinsics, images_dict = obtainImagesDataFromJson(mesh_data,
                                                            camera_json_files)
  prepareCamerasInput(camera_intrinsics, polycam_dir, output_dir)
  prepareImagesInput(images_dict, output_dir, polycam_dir)
  shutil.rmtree(key_frames_folder)

  return

def main():
  parser = ArgumentParser(description=__doc__)
  parser.add_argument(
    "--polycam_dir",
    type=Path,
    help="Path to polycam dataset dirctory")
  parser.add_argument(
    "--output_dir",
    type=Path,
    default=None,
    help="output directory for cameras.txt and images.txt")

  args = parser.parse_args()
  transformDataset(args.polycam_dir, args.output_dir)

  return


if __name__ == "__main__":
  main()
