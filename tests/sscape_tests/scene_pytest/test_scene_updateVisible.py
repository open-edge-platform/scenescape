#!/usr/bin/env python3


# Copyright (C) 2021-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
