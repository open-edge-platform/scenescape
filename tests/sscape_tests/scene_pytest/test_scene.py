#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import pytest
import numpy as np

from scene_common.timestamp import get_epoch_time
from scene_common.geometry import Region, Point

from tests.sscape_tests.scene_pytest.config import *

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

@pytest.mark.parametrize("detectionType, jdata, when", [(thing_type, jdata, when)])
def test_visible(scene_obj, camera_obj, detectionType, jdata, when):
  """!
  Test visible property of the MovingObjects returned by scene._updateVisible().

  NOTE: scene._updateVisible() returns all cameras that detect the object
  regardless of relative locations of the camera and object.
  """
  scene_obj.cameras[camera_obj.cameraID] = camera_obj
  detected_objects = jdata['objects'][thing_type]
  mobj = scene_obj.tracker.createObject(detectionType, detected_objects[0], when, camera_obj)
  moving_objects = []
  moving_objects.append(mobj)
  scene_obj._updateVisible(moving_objects)
  assert moving_objects[0].visibility[0] == camera_obj.cameraID

  return

def test_isIntersecting(scene_obj):
  """! Verifies the 'Scene.isIntersecting' method.

  @param    scene_obj    Scene class object
  """
  # Create a region with volumetric set to True
  region_data = {
    'uid': 'test_region',
    'name': 'Test Region',
    'points': [[0, 0], [10, 0], [10, 10], [0, 10]],
    'volumetric': True,
    'height': 1.0,
    'buffer_size': 0.0
  }
  region = Region('test_region', 'Test Region', region_data)

  # Create a mock object that intersects with the region
  class MockObject:
    def __init__(self):
      self.sceneLoc = None
      self.size = None
      self.mesh = None
      self.rotation = None

  # Create an object with mesh that intersects
  intersecting_obj = MockObject()
  # Assuming a simple box object at position inside the region
  intersecting_obj.sceneLoc = Point(1.0, 1.0, 0.0)
  intersecting_obj.size = [4.0, 4.0, 1.0]
  intersecting_obj.rotation = [0, 0, 0, 1]

  assert scene_obj.isIntersecting(intersecting_obj, region) is True

  # Test case: Object doesn't intersect with region
  non_intersecting_obj = MockObject()
  non_intersecting_obj.sceneLoc = Point(20.0, 20.0, 0.0)
  non_intersecting_obj.size = [4.0, 4.0, 1.0]
  non_intersecting_obj.rotation = [0, 0, 0, 1]

  assert scene_obj.isIntersecting(non_intersecting_obj, region) is False

  # Test case: compute_intersection is False
  region.compute_intersection = False
  assert scene_obj.isIntersecting(intersecting_obj, region) is False

  region.compute_intersection = True
  error_obj = MockObject()
  error_obj.sceneLoc = None
  assert scene_obj.isIntersecting(error_obj, region) is False

  return

@pytest.mark.parametrize("objects,expected_main_bbox,expected_sub_bbox", [
  # Empty objects list
  ([], False, False),

  # Single object with bbox_px
  ([{'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80}}], True, False),

  # Object without bbox_px
  ([{'id': 'obj1', 'type': 'person'}], False, False),

  # Object with sub_detections
  ([{
    'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80},
    'sub_detections': ['faces'],
    'faces': [{'bounding_box_px': {'x': 110, 'y': 210, 'width': 20, 'height': 25}}]
  }], True, True),

  # Object with sub_detections but no main bbox_px
  ([{
    'id': 'obj1',
    'sub_detections': ['faces'],
    'faces': [{'bounding_box_px': {'x': 110, 'y': 210, 'width': 20, 'height': 25}}]
  }], False, True),
])
def test_convert_pixel_bbox(scene_obj, objects, expected_main_bbox, expected_sub_bbox):
  """! Verifies convertPixelBoundingBoxesToMeters function """
  intrinsics_matrix = np.eye(3)
  distortion_matrix = np.zeros(5)

  scene_obj._convertPixelBoundingBoxesToMeters(objects, intrinsics_matrix, distortion_matrix)

  if len(objects) > 0 and expected_main_bbox:
    assert 'bounding_box' in objects[0]
    assert 'x' in objects[0]['bounding_box']
    assert 'y' in objects[0]['bounding_box']
    assert 'width' in objects[0]['bounding_box']
    assert 'height' in objects[0]['bounding_box']
  elif len(objects) > 0:
    assert 'bounding_box' not in objects[0]

  if expected_sub_bbox and len(objects) > 0:
    assert 'bounding_box' in objects[0]['faces'][0]
    assert 'x' in objects[0]['faces'][0]['bounding_box']
    assert 'y' in objects[0]['faces'][0]['bounding_box']
    assert 'width' in objects[0]['faces'][0]['bounding_box']
    assert 'height' in objects[0]['faces'][0]['bounding_box']

  return
