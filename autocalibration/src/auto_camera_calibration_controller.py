# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from abc import ABC, abstractmethod
from datetime import datetime
from pytz import timezone

from scene_common import log

TIMEZONE = "UTC"

class CameraCalibrationController(ABC):
  """
  This Class is the CameraCalibration controller, which controls the whole of
  camera calibration processes occuring in the container.
  """
  cam_calib_objs = {}

  def __init__(self, calibration_data_interface):
    self.frame_count = {}
    self.calibration_data_interface = calibration_data_interface
    self.socketio = None
    self.socket_scene_clients = None

  def notifySceneRegistration(self, scene_id, response):
    if not self.socket_scene_clients:
      return

    socket_id = self.socket_scene_clients.get(scene_id)
    if socket_id:
      if self.socketio:
        self.socketio.emit("register_result", {"scene_id": scene_id, "data": response}, to=socket_id)
        log.info(f"Sent WebSocket result to {socket_id} for {scene_id}")
    return

  @abstractmethod
  def processSceneForCalibration(self, sceneobj, map_update=False):
    """! The following tasks are done in this function:
         1) Create CamCalibration Object.
         2) If Scene is not updated, use data stored in database.
            If Scene is updated, identify all the apriltags in the scene
            and store data to database.
    @param   sceneobj     Scene object
    @param   map_update   was the scene map updated

    @return  None
    """
    raise NotImplementedError

  @abstractmethod
  def resetScene(self, scene):
    """! Function resets map_processed and calibration data.
    @param   scene             Scene database object.

    @return  None
    """
    raise NotImplementedError

  @abstractmethod
  def isMapUpdated(self, sceneobj):
    """! function used to check if the map is updated and reset the scene when map is None.
    @param   sceneobj      scene object.

    @return  True/False
    """
    raise NotImplementedError

  def isMapProcessed(self, sceneobj):
    """! function used to check if the map is processed.
    @param   sceneobj      scene object.

    @return  True/False
    """
    if not sceneobj.map or not getattr(sceneobj.map, 'path', None):
      return False

    try:
      map_path = sceneobj.map.path
      map_mtime = datetime.fromtimestamp(os.path.getmtime(map_path), tz=timezone(TIMEZONE))
    except (FileNotFoundError, ValueError, TypeError) as e:
      log.warning(f"Map file missing or invalid for scene {sceneobj.id}: {e}")
      return False

    if sceneobj.map_processed is None:
      return False

    return sceneobj.map_processed < map_mtime

  def saveToDatabase(self, scene):
    """! Function stores baseapriltag data into db.
    @param   scene             Scene database object.

    @return  None
    """
    raise NotImplementedError

  @abstractmethod
  def generateCalibration(self, sceneobj, camera_intrinsics, msg):
    """! Generates the camera pose.
    @param   sceneobj           Scene object
    @param   camera_intrinsics  Camera Intrinsics
    @param   msg                Payload with camera frame data

    @return  None
    """
    raise NotImplementedError
