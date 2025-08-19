# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from auto_camera_calibration_controller import CameraCalibrationController
from markerless_camera_calibration import \
    CameraCalibrationMonocularPoseEstimate
from polycam_to_images import transformDataset
from pytz import timezone

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

TIMEZONE = "UTC"

class MarkerlessCameraCalibrationController(CameraCalibrationController):
  """
  This Class is the extends the CameraCalibrationController class from
  auto_camera_calibration_controller for Markerless Camera Calibration
  Strategy.
  """

  def generateCalibration(self, sceneobj, camera_intrinsics, cam_frame_data):
    """! Generates the camera pose.
    @param   sceneobj   Scene object
    @param   camera_intrinsics  Camera Intrinsics
    @param   msg        Payload with camera frame data

    @return  dict       Dictionary containing publish topic and data to publish
    """
    cur_cam_calib_obj = self.cam_calib_objs[sceneobj.id]
    log.info("Calibration configuration:", cur_cam_calib_obj.config)
    if camera_intrinsics is None:
      raise TypeError(f"Intrinsics not found for camera {cam_frame_data['id']}!")
    pub_data = cur_cam_calib_obj.localize(cam_frame_data=cam_frame_data,
                                          camera_intrinsics=camera_intrinsics,
                                          sceneobj=sceneobj)
    if bool(pub_data):
      if pub_data.get('error') == 'True':
        log.error(pub_data.get('message', 'Weak or insufficient matches'))
      publish_topic = PubSub.formatTopic(PubSub.DATA_AUTOCALIB_CAM_POSE,
                                         camera_id=cam_frame_data['id'])
      log.info(f"Generated camera pose for camera {cam_frame_data['id']}")
      return {'publish_topic': publish_topic,
              'publish_data': json.dumps(pub_data)}

  def processSceneForCalibration(self, sceneobj, map_update=False):
    """! The following tasks are done in this function:
         1) Pre-process the uploaded polycam zip file.
         2) Using the global feature matching algorithm, performs feature
            matching on all the images in the dataset from the above zip.
         3) Incase of a scene update, this process will be triggered again.
    @param   sceneobj     Scene object
    @param   map_update   Flag is set when there is a map update in scene object.

    @return  mqtt_response
    """
    response_dict = {'status': "success"}
    log.info("processing markerless scene for calibration")
    try:
      preprocess = self.preprocessPolycamDataset(sceneobj)
    except FileNotFoundError as fnfe:
      log.error(fnfe)
      response_dict['status'] = str(fnfe)
      return response_dict

    response_dict['status'] = preprocess['status']
    if preprocess['status'] != "success":
      return response_dict

    if sceneobj is None:
      log.error("Topic Structure mismatch")
      response_dict['status'] = "Topic Structure mismatch"
      return response_dict

    if sceneobj.id not in self.cam_calib_objs or map_update:
      try:
        self.cam_calib_objs[sceneobj.id] = \
          CameraCalibrationMonocularPoseEstimate(sceneobj,
                                                 preprocess['dataset_dir'],
                                                 preprocess['output_dir'])
      except ValueError as ve:
        response_dict['status'] = str(ve)
        return response_dict

    if sceneobj.map_processed is None or map_update:
      try:
        with self.cam_calib_objs[sceneobj.id].cam_calib_lock:
          sceneobj = self.cam_calib_objs[sceneobj.id].registerDataset(sceneobj)
          self.saveToDatabase(sceneobj)
          log.info("Dataset registered")
      except FileNotFoundError as e:
        if "global-feats-netvlad.h5" in str(e):
          response_dict = {"status" : "re-register"}
        else:
          log.error("Failed to register dataset")
          response_dict['status'] = str(e)
        return response_dict
    else:
      try:
        sceneobj = self.cam_calib_objs[sceneobj.id].registerDataset(sceneobj)
        log.info("Dataset registered", self.cam_calib_objs[sceneobj.id].config)
      except FileNotFoundError as e:
        if "global-feats-netvlad.h5" in str(e):
          response_dict = {"status" : "re-register"}
        else:
          log.error("Failed to register dataset")
          response_dict['status'] = str(e)
        return response_dict

    return response_dict

  def isPolycamDataProcessed(self, sceneobj):
    """! function used to check if the polycam data is processed.
    @param   sceneobj      scene object.

    @return  True/False
    """
    return (sceneobj.map_processed < datetime.fromtimestamp(
      os.path.getmtime(sceneobj.polycam_data),tz=timezone(TIMEZONE)))

  def isMapUpdated(self, sceneobj):
    """! function used to check if the map is updated and reset the scene when map is None.
    @param   sceneobj      scene object.

    @return  True/False
    """
    if not sceneobj.map or not sceneobj.polycam_data:
      return False
    elif (sceneobj.map_processed is None) or (self.isMapProcessed(sceneobj)) or (
           self.isPolycamDataProcessed(sceneobj)):
      return True

  def saveToDatabase(self, scene):
    """! Function updates polycam processed timestamp data into db.
    @param   scene             Scene database object.

    @return  None
    """
    self.calibration_data_interface.updateMapProcessed(scene.id, get_iso_time())
    return

  def resetScene(self, scene):
    self.cam_calib_objs.pop(scene.id, None)
    if (hasattr(scene, 'output_dir') and os.path.exists(scene.output_dir)
        and os.path.isdir(scene.output_dir)):
      shutil.rmtree(scene.output_dir)
    return

  def preprocessPolycamDataset(self, scene_obj):
    """! Preprocess the polycam zip file uploaded via UI, extracts data
    appropriately and organizes the dataset for markerless camera
    calibration registerdataset function.

    @param   sceneobj     Scene object

    @return  mqtt_response
    """
    response_dict = {"status": "success"}
    if not scene_obj.polycam_data:
      raise FileNotFoundError("Polycam zip file not found")
    base_dataset_path = Path(os.getcwd()) / "datasets" / scene_obj.name
    with zipfile.ZipFile(scene_obj.polycam_data) as zf:
      zf.extractall(base_dataset_path)
      extracted_files = zf.namelist()
    file_name = self._find_dataset_dir(extracted_files)
    if not file_name:
      file_name = self.restructure_dataset_dir(extracted_files, base_dataset_path, scene_obj.polycam_data)
    dataset_dir = base_dataset_path / file_name
    if dataset_dir.is_file():
      dataset_dir = dataset_dir.parent
    output_dir = base_dataset_path / "output_dir"
    transformDataset(str(dataset_dir), str(output_dir))
    response_dict["dataset_dir"] = str(dataset_dir)
    response_dict["output_dir"] = str(output_dir)
    log.info("Polycam dataset preprocessing complete", response_dict)

    return response_dict

  def _find_dataset_dir(self, extracted_files):
    for file_path in extracted_files:
      parts = file_path.split('/')
      if len(parts) > 1 and parts[0] and parts[0] != "keyframes":
        return parts[0]
    return ""

  def restructure_dataset_dir(self, extracted_files, base_dataset_path, polycam_data_path):
    zip_base_name = Path(polycam_data_path).stem
    target_dir = base_dataset_path / zip_base_name
    target_dir.mkdir(exist_ok=True)

    for file_path in extracted_files:
      src_path = base_dataset_path / file_path
      if src_path.is_file():
        dst_path = target_dir / file_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
    return zip_base_name
