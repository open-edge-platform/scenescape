# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from abc import ABC, abstractmethod
from datetime import datetime

from pytz import timezone

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
    return (sceneobj.map_processed < datetime.fromtimestamp(os.path.getmtime(sceneobj.map),
                                                        tz=timezone(TIMEZONE)))

  def saveToDatabase(self, scene):
    """! Function stores baseapriltag data into db.
    @param   scene             Scene database object.

    @return  None
    """
    raise NotImplementedError

  @abstractmethod
  def generateCalibration(self, sceneobj, msg):
    """! Generates the camera pose.
    @param   sceneobj   Scene object
    @param   msg        Payload with camera data from percebro

    @return  None
    """
    raise NotImplementedError

  def loopForever(self):
    raise NotImplementedError
