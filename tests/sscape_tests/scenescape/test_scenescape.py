#!/usr/bin/env python3

# Copyright (C) 2021-2025 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import os

from scene_common.scene_model import SceneModel as Scene
from scene_common.camera import Camera
from scene_common.geometry import Region, Tripwire
from scene_common.scenescape import SceneLoader

sscape_tests_path = os.path.dirname(os.path.realpath(__file__))
CONFIG_FULLPATH = os.path.join(sscape_tests_path, "config.json")
CAMERA_NAME = "Cam_x2_2"
SCENE_NAME = "Demo"

def test_init(manager):
  assert manager.configFile == CONFIG_FULLPATH
  assert type(manager.scene) == Scene
  assert type(manager.scene.cameras[CAMERA_NAME]) == Camera
  assert type(manager.scene.regions[CAMERA_NAME]) == Region
  assert type(manager.scene.tripwires[CAMERA_NAME]) == Tripwire

  return

def test_sceneWithName():
  SceneLoader.addScene(SceneLoader.scene)
  scene = SceneLoader.sceneWithName(SCENE_NAME)

  assert scene
  assert type(scene) == Scene
  assert scene.name == SCENE_NAME
  return

def test_addScene():
  SceneLoader.addScene(SceneLoader.scene)

  assert SceneLoader.scenes[SCENE_NAME] == SceneLoader.scene
  return
