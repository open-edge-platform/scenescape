# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
from addict import Dict
from hloc import (extract_features, match_dense, match_features,
                  pairs_from_retrieval)
from hloc.pipelines.SceneScape import localize_scenescape
from scipy.spatial.transform import Rotation

from scene_common import log
from scene_common.transform import convertToTransformMatrix, getPoseMatrix

DEPTH_SCALE = 6553.5
DEPTH_MAX = 10
CAMERA_MODEL = 'SIMPLE_PINHOLE'
CAMERA_SCALE = [1.0, 1.0, 1.0]

class CameraCalibrationMonocularPoseEstimate:
  """! Class peforms the Camera Calibration without any markers based on
  feature matching algorithms.
  """
  config = {}
  cam_calib_lock = Lock()

  def __init__(self, sceneobj, dataset_dir, output_dir,
               scene_pose_mat=None):
    """! Initializes the class with data necessary for preprocessing.
    @param sceneobj              Object of the Current Scene Model.
    @param dataset_dir           Path of the raw rgbd dataset.
    @param output_dir            Path of the directory containing the h5.
    @param scene_pose_mat        Scene pose stored in database.

    @return None
    """
    self.name = sceneobj.name
    self.dataset_dir = dataset_dir
    self.output_dir = output_dir
    self.config = Dict(self.generateMarkerlessConfig(sceneobj))
    self.scene_pose_mat = scene_pose_mat
    self.hloc_config = self.config['hloc']

  def decodeImage(self, img_data):
    """! Converts image from string format to numpy format.
    @param   img_data     Encoded image from MQTT.

    @return  image_new    Image in numpy/cv2 format
    """
    image_array = np.frombuffer(base64.b64decode(img_data), dtype=np.uint8)

    return cv2.imdecode(image_array, flags=1)

  def generateMarkerlessConfig(self, sceneobj):
    """! Gernerate reloc config data based on Scene object data
         stored in database.
    @param sceneobj     Object of Scene Model.

    @return config      Dictionary with reloc config data.
    """
    config = {}
    config['data'] = {"rgb_ext": ".jpg", "depth_ext": ".png"}
    config['data']['mesh_file'] = f"{self.dataset_dir}/raw.glb"
    config['data']['depth_scale'] = DEPTH_SCALE
    config['data']['depth_max'] = DEPTH_MAX
    config['hloc'] = {
      'num_loc': sceneobj.number_of_localizations,
      'global_feature': sceneobj.global_feature,
      'local_feature': sceneobj.local_feature,
      'matcher': sceneobj.matcher,
      'min_matches': sceneobj.minimum_number_of_matches,
      'inlier_threshold': sceneobj.inlier_threshold
    }
    config['dataset_dir'] = self.dataset_dir
    config['output_dir'] = self.output_dir

    return config

  def featureExtract(self, dataset_dir, output_dir, image_list):
    """! Create a list of file Paths of all the extracted features
         performed by the models and stored in different files.
    @param dataset_dir     Path of the dataset with rbg and depth images.
    @param output_dir      Path of the directory containing extracted features.
    @param image_list      List of images along with their rotation and
                           translation features.

    @return feature_paths  List of files paths of .h5 files which contain
                           the extracted features from feature matching models.
    """
    self.hloc_config.global_descriptor_file = str(extract_features.main(
      self.hloc_config.retrieval_conf, dataset_dir, output_dir,
      image_list=image_list))

    feature_paths = []
    for dense_matching, local_feature in zip(self.hloc_config.is_match_dense,
                                             self.hloc_config.local_feature):
      if not dense_matching:
        feature_config = extract_features.confs[local_feature]
        feature_paths.append(str(extract_features.main(feature_config,
                                                       dataset_dir,
                                                       output_dir)))
      else:
        feature_paths.append(".")

    return feature_paths

  def featureExtractLocalize(self, workdir, query_dir, output_dir, loc_pairs, query):
    """! Creates a list of file Paths for the features that have been matched by
         the query image to be localized.

    @param workdir         Path of the dataset with rbg and depth images.
    @param query_dir       Path of dir containing the rgb images.
    @param output_dir      Path of the directory containing extracted features.
    @param loc_pairs       Localized pairs of images.
    @param query           Query message for camera calibration.

    @return List of files paths of .h5 files which contain the extracted
            features and matching features correponding to the image.
    """
    feature_paths = []
    match_paths = []
    for dense_matching, local_feature, feature_ref, matcher in zip(
        self.hloc_config.is_match_dense, self.hloc_config.local_feature,
        self.hloc_config.feature_paths, self.hloc_config.matcher):
      if dense_matching:
        matcher_config = match_dense.confs[matcher] | self.hloc_config.matcher[matcher]
        feature_path, match_path = match_dense.main(
          conf=matcher_config, pairs=loc_pairs, export_dir=workdir, reassign=False,
          image_cache={query.name: query.image_data},
          image_dir=(query_dir, Path(self.config.dataset_dir)))
      else:
        feature_config = (extract_features.confs[local_feature] |
                          self.hloc_config.local_feature[local_feature])
        feature_path = workdir / f"features-{local_feature}.h5"
        extract_features.main(feature_config, query_dir, output_dir, image_list=query,
                              feature_path=feature_path)
        matcher_config = match_features.confs[matcher] | self.hloc_config.matcher[matcher]
        match_path = workdir / f"matches-{local_feature}-{matcher}.h5"
        match_features.main(matcher_config, loc_pairs, feature_path, output_dir, match_path,
                            Path(feature_ref))
      feature_paths.append(feature_path)
      match_paths.append(match_path)

    return feature_paths, match_paths

  def registerDataset(self, sceneobj=None):
    """!Extract features from the dataset and store them in scene
        object in database.
    @param  sceneobj    Object of Scene Model

    @return sceneobj    Updated Scene OBject
    """
    self.scene_pose_mat = getPoseMatrix(sceneobj)
    log.info("Camera pose recomputed.")
    if len(self.hloc_config.local_feature) != len(self.hloc_config.matcher):
      raise ValueError("Specify a local feature for each matcher!")
    self.hloc_config.is_match_dense = tuple(lf == "-" for lf in
                                            self.hloc_config.local_feature)
    dataset_dir = Path(self.dataset_dir)
    output_dir = Path(self.output_dir)
    self.hloc_config.output = str(output_dir / ("-".join(
      ("SceneScape", self.hloc_config.global_feature, str(self.hloc_config.num_loc),
       *self.hloc_config.local_feature, *self.hloc_config.matcher)) + ".txt"))
    self.hloc_config.retrieval_conf = extract_features.confs[
      self.hloc_config.global_feature]
    image_list = [
      p.relative_to(dataset_dir)
      for p in (dataset_dir).glob(f"**/*{self.config.data.rgb_ext}")
    ]
    feature_paths = self.featureExtract(dataset_dir, output_dir, image_list)
    self.hloc_config.feature_paths = feature_paths
    if sceneobj:
      sceneobj.output = self.config['hloc']['output']
      sceneobj.retrieval_conf = self.config['hloc']['retrieval_conf']
      sceneobj.global_descriptor_file = self.config['hloc']['global_descriptor_file']

    return sceneobj

  def generateQueryForLocalization(self, percebro_cam_data):
    """!Generate the query format necessary for localization.

    @param   percebro_cam_data  Mqtt Message from percebro

    @return  Dict               Camera Intrinsics and Query in desired format.
    """
    rw_cam_int = (np.array(percebro_cam_data['intrinsics']))
    query = {
      "timestamp": datetime.now().isoformat(),
      "camera_id": percebro_cam_data['id'],
      'image_data': percebro_cam_data['image']
    }
    image_data = self.decodeImage(query['image_data'])
    camera_intrinsics = Dict({
      'id': percebro_cam_data['id'], 'model': CAMERA_MODEL,
      'width': image_data.shape[1], 'height': image_data.shape[0],
      'params': np.array([rw_cam_int[0, 0], rw_cam_int[0, 2], rw_cam_int[1, 2]])
    })
    log.info("Camera Intrinsics", camera_intrinsics)
    query = Dict(query)
    if "name" not in query:
      query.name = f"{query.camera_id}-{query.timestamp}"
    self.workdir = Path(tempfile.mkdtemp(prefix=f"{query.name}-"))
    self.loc_pairs = self.workdir / "pairs.txt"
    self.global_feature_path = self.workdir / "global_features.h5"
    self.query_dir = self.dataset_dir + "/rgb"
    if self.query_dir is not None:
      self.query_dir = Path(self.query_dir)

    return query, camera_intrinsics

  def localize(self, percebro_cam_data, sceneobj=None):
    """!Based on query image, obtain the camera calibration.
    @param  percebro_cam_data    Mqtt Message from percebro

    @return sceneobj    Updated Scene Object
    """
    self.scene_pose_mat = getPoseMatrix(sceneobj)
    query, camera_intrinsics = self.generateQueryForLocalization(percebro_cam_data)
    extract_features.main(
      self.hloc_config.retrieval_conf, self.query_dir, self.output_dir, image_list=query,
      feature_path=self.global_feature_path
    )
    pairs_from_retrieval.main(
      self.global_feature_path, self.loc_pairs, self.hloc_config.num_loc,
      query_list=(query.name,),
      db_descriptors=self.hloc_config.global_descriptor_file
    )
    feature_paths, match_paths = self.featureExtractLocalize(
      self.workdir, self.query_dir, self.output_dir, self.loc_pairs, query
    )
    results_path = f"{self.workdir}/results.txt"
    results = localize_scenescape.main(
      Path(self.config.dataset_dir), self.hloc_config.feature_paths,
      self.loc_pairs, camera_intrinsics, feature_paths, match_paths,
      results_path, skip_matches=self.hloc_config.min_matches,
      match_dense=self.hloc_config.is_match_dense, data_config=self.config.data
    )
    shutil.rmtree(self.workdir)
    self.workdir = None

    if not self.evaluateMatchQuality(results):
      return {
        "timestamp": query.timestamp,
        "name": percebro_cam_data['id'],
        "camera_id": query.camera_id,
        "error": "True",
        "success": False,
        "message": "Weak or insufficient matches. This camera might not belong to this scene."
      }

    results.success = True

    cam_to_world_y_down = convertToTransformMatrix(self.scene_pose_mat, results.qvec.tolist(),
                                                        results.tvec.tolist())
    quat = Rotation.from_matrix(cam_to_world_y_down[0:3, 0:3]).as_quat()
    trans = np.ravel(cam_to_world_y_down[0:3, 3:4].flatten())

    return {
      "timestamp": query.timestamp,
      "name": percebro_cam_data['id'],
      "camera_id": query.camera_id,
      "error": "False" if results.success else "True",
      "success": results.success,
      "quaternion": quat.tolist(),
      "scale": CAMERA_SCALE,
      "translation": trans.tolist()
    }

  def evaluateMatchQuality(self, results):
    """! Check the quality of matches.
    @param results   Localization results containing matches.

    @return bool     True if matches are sufficient, False otherwise.
    """
    if results.num_matches == 0 or results.n_inliers == -1:
      return False

    min_required_matches = self.hloc_config.min_matches
    if results.num_matches < min_required_matches:
      return False

    inlier_ratio = results.n_inliers / results.num_matches
    inlier_threshold = self.hloc_config.inlier_threshold
    return inlier_ratio >= inlier_threshold

  def convertYUpToYDown(self, rotation, translation):
    """!Convert pose from Y-up to Y-down to align with SceneScape coordinate system.

    @param  rotation      Rotation values of an object.
    @param  translation   Translation values of an object.

    @return updated matrix in accordance with scenescape convention.
    """
    y_up_to_y_down = np.array([[1, 0, 0, 0],
                               [0, -1, 0, 0],
                               [0, 0, -1, 0],
                               [0, 0, 0, 1]])

    cam_to_world_y_up = convertToTransformMatrix(self.scene_pose_mat, rotation, translation)
    # rotates angles not translation.
    cam_to_world_y_down = cam_to_world_y_up @ y_up_to_y_down
    cam_to_world_y_down = self.scene_pose_mat @ cam_to_world_y_down

    return cam_to_world_y_down

