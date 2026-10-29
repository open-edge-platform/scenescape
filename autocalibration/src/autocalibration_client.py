# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from urllib.parse import urljoin

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
    # PATCH: POST on this route starts a new registration instead.
    full_path = urljoin(self.url, f"scenes/{sceneId}/registration")
    headers = {'Authorization': f"Token {self.token}"}
    reply = self.session.patch(full_path, json=data, headers=headers, verify=self.verify_ssl)
    return self.decodeReply(reply, HTTPStatus.OK)

  def calibrateCamera(self, cameraId, data):
    """Calibrate a camera."""
    return self._create(f"cameras/{cameraId}/calibration", data)

  def getCameraCalibrationStatus(self, cameraId):
    """Gets camera calibration status."""
    return self._get(f"cameras/{cameraId}/calibration", None)

  def localizePerceptualSensor(self, sensorId, data):
    """Localize a perceptual sensor against a scene."""
    return self._create(f"perceptual-sensors/{sensorId}/localization", data)

  def getPerceptualSensorLocalizationStatus(self, sensorId):
    """Gets perceptual sensor localization status."""
    return self._get(f"perceptual-sensors/{sensorId}/localization", None)
