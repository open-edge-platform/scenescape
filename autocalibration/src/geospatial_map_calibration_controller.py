# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
import threading

import cv2
import numpy as np

from scene_common import log
from scene_common.timestamp import get_iso_time

from auto_camera_calibration_controller import CameraCalibrationController
from geospatial_map_calibration import GeoMapPrior, GeospatialMapCalibration, is_raster_map

GEOSPATIAL_MAP = "GeospatialMap"
NEEDS_PRIOR = "needs_prior"


class GeospatialMapCalibrationController(CameraCalibrationController):
  """
  Calibrates a camera against the scene's metric top-down (geospatial / ortho)
  map image. Needs no polycam dataset or markers; an optional operator prior
  (map point and/or heading) disambiguates low-confidence solves.
  """

  def __init__(self, calibration_data_interface):
    super().__init__(calibration_data_interface)
    self._calibrators = {}
    self._calibrators_lock = threading.Lock()

  @staticmethod
  def supports_scene(sceneobj):
    return is_raster_map(getattr(sceneobj, "map", None))

  def _get_calibrator(self, sceneobj, reload=False):
    """Return the cached map calibrator, reloading when the map file or scale changes."""
    if not self.supports_scene(sceneobj):
      raise ValueError("Geospatial map calibration requires a PNG or JPEG scene map")
    if not os.path.isfile(sceneobj.map):
      raise FileNotFoundError(f"Scene map not found: {sceneobj.map}")
    key = (sceneobj.map, os.path.getmtime(sceneobj.map), float(sceneobj.scale))
    with self._calibrators_lock:
      cached = self._calibrators.get(sceneobj.id)
      if reload or cached is None or cached[0] != key:
        cached = (key, GeospatialMapCalibration.from_file(sceneobj.map, sceneobj.scale))
        self._calibrators[sceneobj.id] = cached
    return cached[1]

  def process_scene_for_calibration(self, sceneobj, map_update=False):
    """! Loads the scene map for calibration and records it as processed.
    @param   sceneobj     Scene object
    @param   map_update   Flag is set when there is a map update in scene object.

    @return  dict with registration status
    """
    response_dict = {"status": "success"}
    try:
      self._get_calibrator(sceneobj, reload=map_update)
    except (FileNotFoundError, ValueError) as e:
      log.error(f"Geospatial map registration failed for scene {sceneobj.id}: {e}")
      response_dict = {"status": "error", "message": str(e)}
      self.notify_scene_registration(sceneobj.id, response_dict)
      return response_dict

    if sceneobj.map_processed is None or map_update:
      self.save_to_database(sceneobj)
    self.notify_scene_registration(sceneobj.id, response_dict)
    return response_dict

  def is_map_updated(self, sceneobj):
    if not self.supports_scene(sceneobj):
      return False
    return sceneobj.map_processed is None

  def reset_scene(self, scene):
    with self._calibrators_lock:
      self._calibrators.pop(scene.id, None)

  def save_to_database(self, scene):
    self.calibration_data_interface.update_map_processed(scene.id, get_iso_time())

  def generate_calibration(self, sceneobj, camera_intrinsics, cam_frame_data):
    """! Estimates the camera pose against the scene map.
    @param   sceneobj           Scene object
    @param   camera_intrinsics  3x3 camera matrix
    @param   cam_frame_data     Payload with camera frame data and optional prior

    @return  dict containing calibration result or error info
    """
    camera_id = cam_frame_data["id"]
    try:
      if camera_intrinsics is None:
        raise ValueError(f"Intrinsics not found for camera {camera_id}")
      calibrator = self._get_calibrator(sceneobj)
      frame = cv2.imdecode(
        np.frombuffer(base64.b64decode(cam_frame_data["image"]), dtype=np.uint8), cv2.IMREAD_COLOR)
      if frame is None:
        raise ValueError("Unable to decode camera image")
      prior = GeoMapPrior.from_request(cam_frame_data.get("prior"))
      result = calibrator.calibrate(frame, camera_intrinsics, prior)
    except (FileNotFoundError, ValueError) as e:
      log.error(f"Geospatial map calibration failed for camera {camera_id}: {e}")
      return {"status": "error", "message": str(e)}

    response = {
      "camera_id": camera_id,
      "scene_name": sceneobj.name,
      "message": result["reason"],
      "candidates": result["candidates"],
      "confidence": {
        "score": result.get("score"),
        "needs_prior": result["needs_prior"],
        "reason": result["reason"],
      },
    }
    if result["needs_prior"]:
      log.info(f"Geospatial map calibration for camera {camera_id} needs a prior: {result['reason']}")
      response["status"] = NEEDS_PRIOR
      response["message"] = (f"{result['reason']}. Provide a prior "
                             "(camera map point and/or heading) and retry.")
      return response

    log.info(f"Geospatial map calibration succeeded for camera {camera_id}")
    response.update({
      "status": "success",
      "quaternion": result["quaternion"],
      "translation": result["translation"],
      "calibration_points_3d": result["calibration_points_3d"],
      "calibration_points_2d": result["calibration_points_2d"],
    })
    return response
