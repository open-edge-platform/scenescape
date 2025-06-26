#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import pytest
import time

from tests.sscape_tests.scene_pytest.config import *
from scene_common.timestamp import get_epoch_time

name = "test"
mapFile = "sample_data/HazardZoneSceneLarge.png"
scale = 1000
detections = frame['objects']

def test_init(scene_obj, scene_obj_with_scale):
  """! Verifies the output of 'Scene.init()' method.

  @param    scene_obj    Scene class object
  @param    scene_obj_with_scale     Scene class object with scale value set
  """

  assert scene_obj.name == name
  assert (scene_obj.background == cv2.imread(mapFile)).all()
  assert scene_obj.scale == None
  assert scene_obj_with_scale.scale == scale
  return

@pytest.mark.parametrize("jdata", [(jdata)])
def test_processCameraData(scene_obj, camera_obj, jdata):
  """! Verifies the output of 'Scene.processCameraData' method.

  @param    scene_obj     Scene class object with cameras['camera3']
  @param    jdata     the json data representing a MovingObject
  """
  scene_obj.cameras[camera_obj.cameraID] = camera_obj
  scene_obj.lastWhen = get_epoch_time()
  return_processCameraData = scene_obj.processCameraData(jdata)
  assert return_processCameraData

  # Calls join to end the tracking thread gracefully
  scene_obj.tracker.join()

  return
