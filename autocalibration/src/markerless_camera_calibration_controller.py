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
import zipfile
from datetime import datetime

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

  def generateCalibration(self, sceneobj, msg):
    """! Generates the camera pose.
    @param   sceneobj   Scene object
    @param   msg        Payload with camera data from percebro

    @return  dict       Dictionary containing publish topic and data to publish
    """
    cur_cam_calib_obj = self.cam_calib_objs[sceneobj.id]
    log.info("Calibration configuration:", cur_cam_calib_obj.config)
    percebro_cam_data = json.loads(msg)
    pub_data = cur_cam_calib_obj.localize(percebro_cam_data=percebro_cam_data,
                                          sceneobj = sceneobj)
    if bool(pub_data):
      if pub_data.get('error') == 'True':
        log.error(pub_data.get('message', 'Weak or insufficient matches'))
      publish_topic = PubSub.formatTopic(PubSub.DATA_AUTOCALIB_CAM_POSE,
                                         camera_id=percebro_cam_data['id'])
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
      log.error(FileNotFoundError)
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
    if os.path.exists(scene.output_dir) and os.path.isdir(scene.output_dir):
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
    with zipfile.ZipFile(scene_obj.polycam_data) as zf:
      zf.extractall(f"{os.getcwd()}/datasets/{scene_obj.name}")
      extracted_files = zf.namelist()
    log.info("Dataset zip file extracted")
    file_name = extracted_files[0].split("/")[0]
    dataset_dir = f"{os.getcwd()}/datasets/{scene_obj.name}/{file_name}"
    if os.path.isfile(dataset_dir):
      dataset_dir = os.path.split(dataset_dir)[0]
    output_dir = f"{os.getcwd()}/datasets/{scene_obj.name}/output_dir"
    transformDataset(dataset_dir, output_dir)
    response_dict["dataset_dir"] = dataset_dir
    response_dict["output_dir"] = output_dir
    log.info("Polycam dataset preprocessing complete", response_dict)

    return response_dict
