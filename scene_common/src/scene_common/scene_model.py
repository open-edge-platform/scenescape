# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import os
from copy import copy
from threading import RLock

from scene_common import log
from scene_common.camera import Camera
from scene_common.mesh_util import extractTriangleMesh
from scene_common.options import POSE_CONFIGURED, POSE_OBSERVATION
from scene_common.transform import CameraPose, validate_camera_extrinsics


class SceneModel:
  def __init__(self, name, map_file, scale=None):
    self.name = name
    self.background = None
    self.map_triangle_mesh = None
    self.map_file = map_file
    if map_file:
      # FIXME: get the image binary data using url rather than this hack
      if 'http' in map_file:
        map_file = map_file.replace('https://web.scenescape.intel.com', '/home/scenescape/Scenescape')
      if os.path.exists(map_file):
        self.background = cv2.imread(map_file)
        self.extractMapTriangleMesh(map_file, scale)
    self.children = []
    self.cameras = {}
    self._camera_lock = RLock()
    self.regions = {}
    self.tripwires = {}
    self.sensors = {}
    self.events = {}
    self.output_lla = False
    self.map_corners_lla = None
    self.use_tracker = True

    self.mesh_translation = None
    self.mesh_rotation = None
    self.scale = scale
    return

  def extractMapTriangleMesh(self, mapFile, scale):
    map_info = []
    supported_types = ["png", "jpg", "jpeg"]
    if os.path.basename(mapFile).split(".")[-1].lower() in supported_types:
      if not scale:
        log.error("Scale not provided with a map image")
        return
      map_info.append(mapFile)
      map_info.append(scale)
    else:
      map_info.append(mapFile)

    self.map_triangle_mesh, _ = extractTriangleMesh(map_info)

    return

  def cameraWithID(self, anID):
    if anID in self.cameras:
      return self.cameras[anID]
    return None

  def updateCameras(self, newCameras):
    with self._camera_lock:
      cameras = {}
      for cameraData in newCameras:
        camera_id = cameraData['uid']
        camera = Camera(camera_id, cameraData, resolution=cameraData['resolution'])
        previous = self.cameras.get(camera_id)
        self._retainObservedPose(camera, previous)
        cameras[camera_id] = camera
      self.cameras = cameras

  @staticmethod
  def _retainObservedPose(camera, previous):
    if (getattr(camera, 'pose_policy', POSE_OBSERVATION) == POSE_OBSERVATION
        and getattr(previous, 'pose_policy', None) == POSE_OBSERVATION
        and getattr(previous, 'pose_source', None) == POSE_OBSERVATION
        and getattr(camera, 'pose', None) is not None):
      camera.pose = CameraPose(previous.pose.pose_mat.copy(), camera.pose.intrinsics)
      camera.pose_source = POSE_OBSERVATION

  def updateCameraPose(self, camera_id, extrinsics):
    """Replace an observation-authorized pose without changing durable calibration."""
    with self._camera_lock:
      current = self.cameras.get(camera_id)
      if (current is None or getattr(current, 'pose', None) is None
          or getattr(current, 'pose_policy', POSE_OBSERVATION) == POSE_CONFIGURED
          or extrinsics is None):
        return
      pose = CameraPose(validate_camera_extrinsics(extrinsics), current.pose.intrinsics)
      camera = copy(current)
      camera.pose = pose
      camera.pose_policy = POSE_OBSERVATION
      camera.pose_source = POSE_OBSERVATION
      self.cameras[camera_id] = camera

  def cameraSnapshot(self, camera_id=None, extrinsics=None):
    """Apply an observation and capture stable camera entries under one lock."""
    with self._camera_lock:
      if camera_id is not None:
        try:
          self.updateCameraPose(camera_id, extrinsics)
        except (TypeError, ValueError) as exc:
          log.warning(f"Ignoring invalid camera metadata for {camera_id}: {exc}")
      observation = copy(self)
      observation.cameras = dict(self.cameras)
      return observation

  def serialize(self):
    data = {
      'uid': self.name,
      'name': self.name,
      'output_lla': self.output_lla,
      'map_corners_lla': self.map_corners_lla,
      'use_tracker': self.use_tracker
    }

    # children
    # current objects/things

    if self.cameras:
      data['cameras'] = {x: self.cameras[x].serialize() for x in self.cameras}
    if self.sensors:
      data['sensors'] = {x: self.sensors[x].serialize() for x in self.sensors}
    if self.regions:
      data['regions'] = {x: self.regions[x].serialize() for x in self.regions}
    if self.tripwires:
      data['tripwires'] = {x: self.tripwires[x].serialize() for x in self.tripwires}

    return data

  def areCoordinatesInPixels(self, pixelCoords):
    if self.background is None or self.scale is None:
      return False
    bgRes = self.background.shape[1::-1]
    maxMetersX = bgRes[0] / self.scale
    maxMetersY = bgRes[1] / self.scale
    for pt in pixelCoords:
      if pt[0] is not None and pt[1] is not None \
         and (pt[0] > 2 * maxMetersX or pt[1] > 2 * maxMetersY):
        return True
    return False

  def mapPixelsToMetric(self, pixelCoords):
    if self.background is None:
      return pixelCoords
    bgRes = self.background.shape[1::-1]
    points = [[c[0] / self.scale, (bgRes[1] - c[1]) / self.scale] for c in pixelCoords]
    return points
