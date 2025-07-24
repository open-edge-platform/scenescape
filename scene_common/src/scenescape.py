# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import sys
import json

from scene_common.geometry import Region, Tripwire
from scene_common.scene_model import SceneModel
from scene_common.camera import Camera

class SceneLoader:
  """This class is used to load the configuration file and create the scene"""

  configFile = None
  config = None
  scenes = {}

  def __init__(self, path, scene_model=SceneModel):
    sys.stdout.flush()
    SceneLoader.configFile = path
    if os.path.exists(SceneLoader.configFile) \
       and os.path.getsize(SceneLoader.configFile):
      with open(SceneLoader.configFile) as f:
        SceneLoader.config = json.load(f)
    else:
      SceneLoader.config = {'map': 'LabMap.png'}
    mpath = SceneLoader.config['map']
    if SceneLoader.configFile is not None \
       and not os.path.exists(mpath) and not os.path.isabs(mpath):
      mpath = os.path.join(os.path.dirname(SceneLoader.configFile), mpath)
    SceneLoader.scene = scene_model(SceneLoader.config['name'], mpath,
                                        SceneLoader.config.get("scale", None))
    if 'sensors' in SceneLoader.config:
      idx = 0
      for name in SceneLoader.config['sensors']:
        info = SceneLoader.config['sensors'][name]
        if 'map points' in info:
          if SceneLoader.scene.areCoordinatesInPixels(info['map points']):
            info['map points'] = SceneLoader.scene.mapPixelsToMetric(info['map points'])
        camera = Camera(name, info)
        SceneLoader.scene.cameras[name] = camera
        idx += 1

    if 'regions' in SceneLoader.config:
      for region in SceneLoader.config['regions']:
        points = region['points']
        if SceneLoader.scene.areCoordinatesInPixels(points):
          region['points'] = SceneLoader.scene.mapPixelsToMetric(points)
        region = Region(region['uuid'], region['name'], {'points': region['points']})
        SceneLoader.scene.regions[region.name] = region
    if 'tripwires' in SceneLoader.config:
      for tripwire in SceneLoader.config['tripwires']:
        points = tripwire['points']
        if SceneLoader.scene.areCoordinatesInPixels(points):
          points = SceneLoader.scene.mapPixelsToMetric(points)
        tripwire = Tripwire(tripwire['uuid'], tripwire['name'], {'points': points})
        SceneLoader.scene.tripwires[tripwire.name] = tripwire

    if 'asset3d' in SceneLoader.config:
      for name in SceneLoader.config['asset3d']:
        if name in SceneLoader.object_classes.keys():
          objClass = {'class' : SceneLoader.object_classes[name]['class']}
          objClass.update(SceneLoader.config['asset3d'][name])
          SceneLoader.object_classes[name] = objClass

    return

  @staticmethod
  def sceneWithName(name):
    return SceneLoader.scenes.get(name, None)

  @staticmethod
  def addScene(scene):
    SceneLoader.scenes[scene.name] = scene
    return
