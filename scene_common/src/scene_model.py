# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import os

from scene_common import log
from scene_common.mesh_util import extractTriangleMesh


class SceneModel:
  def __init__(self, name, map_file, scale=None):
    self.name = name
    self.background = None
    self.map_triangle_mesh = None
    self.map_file = map_file
    if map_file:
      # FIXME: get the image binary data using url rather than this hack
      if 'http' in map_file:
        map_file = map_file.replace('https://web.scenescape.intel.com', '/home/scenescape/SceneScape')
      if os.path.exists(map_file):
        self.background = cv2.imread(map_file)
        self.extractMapTriangleMesh(map_file, scale)
    self.children = []
    self.cameras = {}
    self.regions = {}
    self.tripwires = {}
    self.sensors = {}
    self.events = {}
    self.output_lla = False
    self.map_corners_lla = None

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

  def serialize(self):
    data = {
      'uid': self.name,
      'name': self.name,
      'output_lla': self.output_lla,
      'map_corners_lla': self.map_corners_lla
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
