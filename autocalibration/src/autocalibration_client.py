# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common.rest_client import RESTClient


class AutoCalibrationClient(RESTClient):
  """Client for auto-calibration REST endpoints."""

  def getStatus(self):
    """Gets auto-calibration service status."""
    return self._get("status", None)

  def registerScene(self, sceneId, data):
    """Register a scene for auto-calibration."""
    return self._create(f"scenes/{sceneId}/registration", data)

  def getSceneRegistrationStatus(self, sceneId):
    """Gets scene registration status."""
    return self._get(f"scenes/{sceneId}/registration", None)

  def updateSceneRegistration(self, sceneId, data):
    """Updates scene registration."""
    return self._update(f"scenes/{sceneId}/registration", data)

  def calibrateCamera(self, cameraId, data):
    """Calibrate a camera."""
    return self._create(f"cameras/{cameraId}/calibration", data)

  def getCameraCalibrationStatus(self, cameraId):
    """Gets camera calibration status."""
    return self._get(f"cameras/{cameraId}/calibration", None)

  def registerPointCloud(self, sensorId, data):
    """Register a sensor point cloud against a scene."""
    return self._create(f"point-cloud-sensors/{sensorId}/registration", data)

  def getPointCloudRegistrationStatus(self, sensorId):
    """Gets point cloud registration status for a sensor."""
    return self._get(f"point-cloud-sensors/{sensorId}/registration", None)
