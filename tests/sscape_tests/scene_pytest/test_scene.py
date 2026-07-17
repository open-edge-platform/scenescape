#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import cv2
import pytest
import numpy as np
import copy
from types import SimpleNamespace
from unittest.mock import Mock

import controller.scene as scene_module
from controller.moving_object import ChainData
from controller.tracking import Tracking

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
  assert scene_obj.background is not None
  assert (scene_obj.background == cv2.imread(mapFile)).all()
  assert scene_obj.scale is None
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
  mobj = Tracking.createObject(detectionType, detected_objects[0], when, camera_obj)
  moving_objects = [mobj]
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
      for sub_obj, original_sub_obj in zip(obj[key], original_obj[key]):
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

def _make_chain_data():
  return ChainData(
    regions={},
    persist={},
    publishedLocations=[],
  )

def test_processCameraData_unknown_camera_returns_false(scene_obj):
  payload = {
    'id': 'unknown-camera',
    'timestamp': '2023-05-16T21:22:58.388Z',
    'objects': {'person': []}
  }
  assert scene_obj.processCameraData(payload) is False

def test_processCameraData_camera_without_pose_returns_true(scene_obj):
  scene_obj.cameras['camera1'] = SimpleNamespace(cameraID='camera1')
  payload = {
    'id': 'camera1',
    'timestamp': '2023-05-16T21:22:58.388Z',
    'objects': {'person': []}
  }
  assert scene_obj.processCameraData(payload) is True

def test_processCameraData_intrinsics_present_skips_bbox_conversion(scene_obj, camera_obj, monkeypatch):
  scene_obj.cameras[camera_obj.cameraID] = camera_obj
  convert_mock = Mock()
  monkeypatch.setattr(scene_obj, '_convertPixelBoundingBoxesToMeters', convert_mock)
  monkeypatch.setattr(scene_obj, '_createMovingObjectsForDetection', lambda *args, **kwargs: [])
  monkeypatch.setattr(scene_obj, '_finishProcessing', lambda *args, **kwargs: None)
  payload = {
    'id': camera_obj.cameraID,
    'timestamp': '2023-05-16T21:22:58.388Z',
    'intrinsics': {'fx': 1.0},
    'objects': {'person': []}
  }
  assert scene_obj.processCameraData(payload) is True
  convert_mock.assert_not_called()

def test_processCameraData_ignore_time_flag_uses_now(scene_obj, camera_obj, monkeypatch):
  scene_obj.cameras[camera_obj.cameraID] = camera_obj
  captured = {}

  def _capture_create(detection_type, detections, when_value, camera):
    captured['when'] = when_value
    return []

  monkeypatch.setattr(scene_obj, '_createMovingObjectsForDetection', _capture_create)
  monkeypatch.setattr(scene_obj, '_finishProcessing', lambda *args, **kwargs: None)
  payload = {
    'id': camera_obj.cameraID,
    'timestamp': 'not-used',
    'objects': {'person': []}
  }
  assert scene_obj.processCameraData(payload, when=None, ignoreTimeFlag=True) is True
  assert 'when' in captured
  assert isinstance(captured['when'], float)

def test_updateTracker_only_reconfigures_on_change(scene_obj, monkeypatch):
  set_tracker_mock = Mock()
  monkeypatch.setattr(scene_obj, '_setTracker', set_tracker_mock)

  scene_obj.updateTracker(scene_obj.max_unreliable_time,
                          scene_obj.non_measurement_time_dynamic,
                          scene_obj.non_measurement_time_static)
  set_tracker_mock.assert_not_called()

  scene_obj.trackerType = scene_module.Scene.DEFAULT_TRACKER
  scene_obj.updateTracker(scene_obj.max_unreliable_time + 1.0,
                          scene_obj.non_measurement_time_dynamic,
                          scene_obj.non_measurement_time_static)
  set_tracker_mock.assert_called_once_with(scene_obj.trackerType)

def test_createMovingObjectsForDetection_propagates_scene_mesh(scene_obj):
  scene_obj.map_triangle_mesh = 'mesh'
  scene_obj.mesh_translation = [1, 2, 3]
  scene_obj.mesh_rotation = [0, 0, 0, 1]
  scene_obj.persist_attributes = {'person': {'foo': 'bar'}}
  created = SimpleNamespace()
  scene_obj.tracker = SimpleNamespace(createObject=lambda *args: created)

  result = scene_obj._createMovingObjectsForDetection('person', [{'id': 'x'}], 1.23, SimpleNamespace())
  assert len(result) == 1
  assert result[0].map_triangle_mesh == 'mesh'
  assert result[0].map_translation == [1, 2, 3]
  assert result[0].map_rotation == [0, 0, 0, 1]

def test_processSceneData_rejects_lat_long_alt_plus_translation(scene_obj, monkeypatch):
  finish_mock = Mock()
  monkeypatch.setattr(scene_obj, '_finishProcessing', finish_mock)
  child = SimpleNamespace(name='child', retrack=True)
  camera_pose = SimpleNamespace(pose_mat=np.eye(4))
  payload = {'objects': [{'lat_long_alt': [0, 0, 0], 'translation': [1, 2, 3]}]}

  assert scene_obj.processSceneData(payload, child, camera_pose, 'person', when=1.0) is True
  finish_mock.assert_not_called()

def test_processSceneData_splits_retracked_vs_child_objects(scene_obj, monkeypatch):
  calls = []

  def _create_object(detection_type, info, when, child_obj, persist):
    assert 'reid' not in info
    return SimpleNamespace(oid='oid-1', sceneLoc=Point(1.0, 2.0, 0.0), chain_data=_make_chain_data())

  def _capture_finish(detection_type, when, objects, child_objects):
    calls.append((objects, child_objects))

  scene_obj.tracker = SimpleNamespace(createObject=_create_object)
  monkeypatch.setattr(scene_obj, '_finishProcessing', _capture_finish)
  child = SimpleNamespace(name='child', retrack=False)
  camera_pose = SimpleNamespace(pose_mat=np.eye(4))
  payload = {'objects': [{'translation': [1, 2, 3], 'reid': [0.1, 0.2]}]}

  assert scene_obj.processSceneData(payload, child, camera_pose, 'person', when=1.0) is True
  assert len(calls) == 1
  assert len(calls[0][0]) == 0
  assert len(calls[0][1]) == 1

def test_finishProcessing_tracks_when_not_analytics_only(scene_obj, monkeypatch):
  update_visible_mock = Mock()
  track_mock = Mock()
  monkeypatch.setattr(scene_module.ControllerMode, 'isAnalyticsOnly', lambda: False)
  monkeypatch.setattr(scene_obj, '_updateVisible', update_visible_mock)
  scene_obj.tracker = SimpleNamespace(trackObjects=track_mock)

  scene_obj._finishProcessing('person', 10.0, [], [])
  update_visible_mock.assert_called_once()
  track_mock.assert_called_once()

def test_finishProcessing_skips_tracker_in_analytics_only(scene_obj, monkeypatch):
  track_mock = Mock()
  monkeypatch.setattr(scene_module.ControllerMode, 'isAnalyticsOnly', lambda: True)
  monkeypatch.setattr(scene_obj, '_updateVisible', lambda objects: None)
  scene_obj.tracker = SimpleNamespace(trackObjects=track_mock)

  scene_obj._finishProcessing('person', 10.0, [], [])
  track_mock.assert_not_called()

def test_deserialize_sets_core_fields(monkeypatch):
  monkeypatch.setattr(scene_module.ControllerMode, 'isAnalyticsOnly', lambda: False)
  data = {
    'uid': 'scene-1',
    'name': 'scene-name',
    'map': 'sample_data/HazardZoneSceneLarge.png',
    'scale': 123,
    'children': [{'name': 'child-1'}],
    'use_tracker': True,
    'tracker_config': [1.0, 2.0, 3.0],
  }
  scene = scene_module.Scene.deserialize(data)
  assert scene.uid == 'scene-1'
  assert scene.name == 'scene-name'
  assert scene.scale == 123
  assert scene.children == ['child-1']

def test_updateScene_updates_fields_and_invokes_helpers(scene_obj, monkeypatch):
  update_children_mock = Mock()
  update_cameras_mock = Mock()
  update_regions_mock = Mock()
  update_tripwires_mock = Mock()
  update_tracker_mock = Mock()
  invalidate_mock = Mock()

  monkeypatch.setattr(scene_obj, '_updateChildren', update_children_mock)
  monkeypatch.setattr(scene_obj, 'updateCameras', update_cameras_mock)
  monkeypatch.setattr(scene_obj, '_updateRegions', update_regions_mock)
  monkeypatch.setattr(scene_obj, '_updateTripwires', update_tripwires_mock)
  monkeypatch.setattr(scene_obj, 'updateTracker', update_tracker_mock)
  monkeypatch.setattr(scene_obj, '_invalidate_trs_xyz_to_lla', invalidate_mock)

  scene_obj._trs_xyz_to_lla = np.array([1])
  scene_data = {
    'name': 'new-name',
    'children': [],
    'cameras': [],
    'regions': [],
    'tripwires': [],
    'sensors': [],
    'use_tracker': False,
    'tracker_config': [4.0, 5.0, 6.0],
    'scale': 321,
    'regulated_rate': 12,
    'external_update_rate': 34,
    'output_lla': False,
    'map_corners_lla': None,
  }
  scene_obj.updateScene(scene_data)

  assert scene_obj.name == 'new-name'
  assert scene_obj.scale == 321
  assert scene_obj.regulated_rate == 12
  assert scene_obj.external_update_rate == 34
  assert scene_obj.use_tracker is False
  update_children_mock.assert_called_once()
  update_cameras_mock.assert_called_once()
  assert update_regions_mock.call_count == 2
  update_tripwires_mock.assert_called_once()
  update_tracker_mock.assert_called_once_with(4.0, 5.0, 6.0)
  invalidate_mock.assert_called_once()

def test_updateRegions_preserves_sensor_cache_and_state(scene_obj):
  class FakeRegion:
    def __init__(self):
      self.name = 'old-name'
      self.value = 10
      self.lastValue = None
      self.lastWhen = 99.0
      self.entered = {'person': []}
      self.exited = {'person': []}
      self.objects = {'person': []}
      self.when = 98.0
      self.singleton_type = 'environmental'

    def updatePoints(self, region_data):
      self.points = region_data['points']

    def updateSingletonType(self, region_data):
      self.singleton_type = region_data.get('singleton_type', None)

    def updateVolumetricInfo(self, region_data):
      self.volumetric = region_data.get('volumetric', False)

  existing = {'region-1': FakeRegion()}
  new_regions = [{
    'uid': 'region-1',
    'name': 'new-name',
    'points': [[0, 0], [1, 0], [1, 1], [0, 1]],
    'singleton_type': 'attribute',
  }]

  scene_obj._updateRegions(existing, new_regions)
  region = existing['region-1']
  assert region.name == 'new-name'
  assert region.value == 10
  assert region.lastValue is None
  assert region.lastWhen == 99.0
  assert region.entered == {'person': []}
  assert region.exited == {'person': []}
  assert region.objects == {'person': []}
  assert region.when == 98.0

def test_updateRegions_removes_deleted_region_without_error(scene_obj):
  """Deleting a region must not raise, even though Scene has no analytics_state."""
  scene_obj._updateRegions(scene_obj.regions, [{
    'uid': 'r1',
    'name': 'r1',
    'points': [[0, 0], [1, 0], [1, 1], [0, 1]],
  }])
  assert 'r1' in scene_obj.regions

  scene_obj._updateRegions(scene_obj.regions, [])
  assert 'r1' not in scene_obj.regions

def test_updateTripwires_removes_deleted_tripwire_without_error(scene_obj):
  """Deleting a tripwire must not raise, even though Scene has no analytics_state."""
  scene_obj._updateTripwires([{
    'uid': 'tw1',
    'name': 'tw1',
    'points': [[0, 0], [10, 0]],
  }])
  assert 'tw1' in scene_obj.tripwires

  scene_obj._updateTripwires([])
  assert 'tw1' not in scene_obj.tripwires




def test_trs_xyz_to_lla_is_cached_and_invalidate_resets(scene_obj, monkeypatch):
  calls = {'count': 0}

  def _fake_calc(mesh_corners, map_corners_lla):
    calls['count'] += 1
    return np.array([[1.0]])

  monkeypatch.setattr(scene_module, 'getMeshAxisAlignedProjectionToXY', lambda mesh: np.array([[0, 0, 0]]))
  monkeypatch.setattr(scene_module, 'calculateTRSLocal2LLAFromSurfacePoints', _fake_calc)
  scene_obj.output_lla = True
  scene_obj.map_corners_lla = [[0, 0, 0], [1, 1, 1]]

  first = scene_obj.trs_xyz_to_lla
  second = scene_obj.trs_xyz_to_lla
  assert calls['count'] == 1
  assert np.array_equal(first, second)

  scene_obj._invalidate_trs_xyz_to_lla()
  _ = scene_obj.trs_xyz_to_lla
  assert calls['count'] == 2

def test_setTracker_invalid_type_keeps_existing_tracker(scene_obj):
  original_tracker = scene_obj.tracker
  original_tracker_type = scene_obj.trackerType

  scene_obj._setTracker('missing-tracker')

  assert scene_obj.tracker is original_tracker
  assert scene_obj.trackerType == original_tracker_type

def test_processCameraData_processes_each_detection_type(scene_obj, camera_obj, monkeypatch):
  scene_obj.cameras[camera_obj.cameraID] = camera_obj
  converted = []
  created = []
  finished = []

  def _capture_convert(detections, intrinsics_matrix, distortion_matrix):
    converted.append(detections)

  def _capture_create(detection_type, detections, when, camera):
    created.append((detection_type, detections, camera.cameraID))
    return [detection_type]

  def _capture_finish(detection_type, when, objects, child_objects=[]):
    finished.append((detection_type, objects, child_objects))

  monkeypatch.setattr(scene_obj, '_convertPixelBoundingBoxesToMeters', _capture_convert)
  monkeypatch.setattr(scene_obj, '_createMovingObjectsForDetection', _capture_create)
  monkeypatch.setattr(scene_obj, '_finishProcessing', _capture_finish)

  payload = {
    'id': camera_obj.cameraID,
    'timestamp': '2023-05-16T21:22:58.388Z',
    'objects': {
      'person': [{'id': 'p-1'}],
      'vehicle': [{'id': 'v-1'}],
    }
  }

  assert scene_obj.processCameraData(payload) is True
  assert converted == [payload['objects']['person'], payload['objects']['vehicle']]
  assert [call[0] for call in created] == ['person', 'vehicle']
  assert [call[0] for call in finished] == ['person', 'vehicle']
  assert finished[0][1] == ['person']
  assert finished[1][1] == ['vehicle']


def test_isIntersecting_createObjectMesh_value_error_returns_false(scene_obj, monkeypatch):
  def _raise_value_error(obj):
    raise ValueError('invalid object geometry')

  monkeypatch.setattr(scene_module, 'createObjectMesh', _raise_value_error)
  region = SimpleNamespace(compute_intersection=True, mesh=object())
  obj = SimpleNamespace()

  assert scene_obj.isIntersecting(obj, region) is False
