#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import enum
import cv2
import pytest
import numpy as np
import copy

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

@pytest.mark.parametrize("objects", [
  # None objects
  (None),

  # Empty objects list
  ([]),

  # Single object with bbox_px
  ([{'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80}}]),

  # Object without bbox_px
  ([{'id': 'obj1', 'type': 'person'}]),

  # Object with sub_detections
  ([{
    'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80},
    'sub_detections': ['faces'],
    'faces': [{'bounding_box_px': {'x': 110, 'y': 210, 'width': 20, 'height': 25}}]
  }]),

  # Object with sub_detections but no main bbox_px
  ([{
    'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80},
    'sub_detections': ['faces'],
    'faces': [{'bounding_box_px': {'x': 110, 'y': 210, 'width': 20, 'height': 25}}]
  }]),

  # Objects with mixed presence of bbox_px
  ([
    {'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80}},
    {'id': 'obj2', 'type': 'vehicle'},
    {
      'bounding_box_px': {'x': 150, 'y': 250, 'width': 60, 'height': 90},
      'sub_detections': ['license_plates', 'faces'],
      'license_plates': [{'bounding_box_px': {'x': 160, 'y': 260, 'width': 30, 'height': 15}},
                          {'id': 'lp2', 'type': 'license_plate'}],
      'faces': [{'bounding_box_px': {'x': 170, 'y': 270, 'width': 40, 'height': 45}},
                 {'id': 'face1', 'type': 'face'}]
    }
  ]),

  # Objects with already present bounding_box (should be ignored)
  ([
    {'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80},
     'bounding_box': {'x': 1.0, 'y': 2.0, 'width': 0.05, 'height': 0.08}},
    {'id': 'obj2', 'type': 'vehicle',
     'bounding_box': {'x': 1.5, 'y': 2.5, 'width': 0.06, 'height': 0.09}},
    {'bounding_box_px': {'x': 150, 'y': 250, 'width': 60, 'height': 90},
     'bounding_box': {'x': 1.5, 'y': 2.5, 'width': 0.06, 'height': 0.09}}
  ]),

  # Object with sub_detections having bounding_box (should be ignored)
  ([{
    'bounding_box_px': {'x': 100, 'y': 200, 'width': 50, 'height': 80},
    'sub_detections': ['faces'],
    'faces': [
      {'bounding_box_px': {'x': 110, 'y': 210, 'width': 20, 'height': 25},
       'bounding_box': {'x': 1.1, 'y': 2.1, 'width': 0.02, 'height': 0.025}},
      {'bounding_box_px': {'x': 120, 'y': 220, 'width': 30, 'height': 35}},
      {'bounding_box': {'x': 1.5, 'y': 2.5, 'width': 0.06, 'height': 0.09}},
      {'id': 'face2', 'type': 'face'}
    ]
  }]),
])
def test_convert_pixel_bbox(scene_obj, objects):
  """! Verifies convertPixelBoundingBoxesToMeters function """
  intrinsics_matrix = np.eye(3)
  distortion_matrix = np.zeros(5)

  # Create a deep copy of the objects to compare later
  original_objects = copy.deepcopy(objects)

  # Call the method to convert pixel bounding boxes to meters (this modifies 'objects' in place)
  scene_obj._convertPixelBoundingBoxesToMeters(objects, intrinsics_matrix, distortion_matrix)

  # Verify bounding boxes for main objects and sub_detections
  for obj, original_obj in zip(objects or [], original_objects or []):
    assert_bounding_box(obj, original_obj)
    # Verify bounding boxes for sub_detections
    for key in obj.get('sub_detections', []):
      for sub_obj, original_sub_obj in zip(enumerate(obj[key]), enumerate(original_obj[key])):
        assert_bounding_box(sub_obj, original_sub_obj)
  return

def assert_bounding_box(obj, original_obj):
  """Helper function to assert the presence and immutability of bounding box fields."""
  if 'bounding_box' in original_obj:
    # Assert that the bounding_box was not changed
    assert obj['bounding_box'] == original_obj['bounding_box'], f"Bounding box was modified for object: {obj}"
  elif 'bounding_box_px' in obj:
    assert 'bounding_box' in obj, f"'bounding_box' missing for object: {obj}"
    assert 'x' in obj['bounding_box'], f"'x' missing in bounding box for object: {obj}"
    assert 'y' in obj['bounding_box'], f"'y' missing in bounding box for object: {obj}"
    assert 'width' in obj['bounding_box'], f"'width' missing in bounding box for object: {obj}"
    assert 'height' in obj['bounding_box'], f"'height' missing in bounding box for object: {obj}"
  else:
    assert 'bounding_box' not in obj, f"Unexpected 'bounding_box' in object: {obj}"
