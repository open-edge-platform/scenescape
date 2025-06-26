#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
from tests.sscape_tests.scene_pytest.config import *

@pytest.mark.parametrize("detectionType, jdata, when", [(thing_type, jdata, when)])
def test_visible(scene_obj, camera_obj, detectionType, jdata, when):
  """!
  Test visible property of the MovingObjects returned by scene.updateVisible().

  NOTE: scene.UpdateVisible() returns all cameras that detect the object
  regardless of relative locations of the camera and object.
  """
  scene_obj.cameras[camera_obj.cameraID] = camera_obj
  detected_objects = jdata['objects'][thing_type]
  mobj = scene_obj.tracker.createObject(detectionType, detected_objects[0], when, camera_obj)
  moving_objects = []
  moving_objects.append(mobj)
  scene_obj.updateVisible(moving_objects)
  assert moving_objects[0].visibility[0] == camera_obj.cameraID

  return
