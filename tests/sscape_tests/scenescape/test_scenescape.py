#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
