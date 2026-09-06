#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import patch, MagicMock

from scene_common.scene_model import SceneModel as Scene
from controller.scene import Scene
from scene_common.camera import Camera
from controller.tracking import Tracking
import controller.scene as scene_module

################################################################
# Methods
################################################################
class _StubTracking(Tracking):
  """Lightweight tracker that skips robot_vision dependency."""

  def __init__(self, *args, reid_config_data=None, **kwargs):
    # Skip Tracking.__init__ to avoid spawning UUIDManager threads.
    # Only initialize the attributes that Scene/tests actually access.
    self.trackers = {}
    self.all_tracker_objects = self.curObjects = []
    self.already_tracked_objects = []
    self.reid_config_data = reid_config_data if reid_config_data else {}

  def trackObjects(self, objects, already_tracked_objects, when, categories,
                   ref_camera_frame_rate=None, max_unreliable_time=None,
                   non_measurement_time_dynamic=None, non_measurement_time_static=None,
                   use_tracker=True):
    """No-op tracking: store objects per category without spawning threads."""
    for category in (categories or []):
      if category not in self.trackers:
        self.trackers[category] = _StubTracking(reid_config_data=self.reid_config_data)
      cat_objects = [obj for obj in objects if obj.category == category]
      self.trackers[category].curObjects = cat_objects
      self.trackers[category].all_tracker_objects = cat_objects

  def trackCategory(self, objects, when, tracks):
    self.all_tracker_objects = list(objects)

  def trackCategoryBatched(self, objects_per_camera, when, tracks):
    self.all_tracker_objects = []
    for camera_objects in objects_per_camera:
      self.all_tracker_objects.extend(camera_objects)

  def updateReidConfig(self, reid_config_data=None):
    self.reid_config_data = reid_config_data if reid_config_data else {}

  def join(self):
    pass

def _mock_set_tracker(self, trackerType):
  """Install a stub tracker to avoid robot_vision dependency."""
  if trackerType not in self.available_trackers:
    return
  self.trackerType = trackerType
  self.tracker = _StubTracking(reid_config_data=self.reid_config_data)

@pytest.fixture(scope='session', autouse=True)
def mock_tracker_init():
  """Mock _setTracker to avoid robot_vision.tracking dependency."""
  with patch.object(Scene, '_setTracker', _mock_set_tracker):
    yield

@pytest.fixture(scope='session', autouse=True)
def mock_rv_tracking():
  """Mock rv.tracking.compute_pixels_to_meter_plane_batch."""
  def fake_compute(bboxes, intrinsics, distortion):
    return [(b[0] / 100.0, b[1] / 100.0, b[2] / 100.0, b[3] / 100.0) for b in bboxes]
  mock_tracking = MagicMock()
  mock_tracking.compute_pixels_to_meter_plane_batch = fake_compute
  with patch.object(scene_module, 'rv', MagicMock(tracking=mock_tracking)):
    yield

@pytest.fixture(scope='session', autouse=True)
def mock_ilabs_rv():
  """Mock robot_vision usage inside controller.ilabs_tracking."""
  with patch("controller.ilabs_tracking.rv", MagicMock()):
    yield

def camera_param():
  """!
  Returns predefined Camera object parameter DICT.
  @return param: DICT of camera object parameters.
  """
  sParam = {}
  sParam['cameraID'] = "camera1"
  sParam['scale'] = 100.0
  sParam['width'] = 640
  sParam['height'] = 480
  sParam['camPts'] = [[278, 61], [621, 132], [559, 460], [66, 289]]
  sParam['mapPts'] = [[0.1, 5.38, 0], [3.04, 5.35, 0], [3.05, 2.42, 0], [0.1, 2.45, 0]]
  return sParam

def get_cent_mass(bBox):
  """!
  Given a bounding box DICT returns a center of mass DICT.
  @param bBox: DICT detected object bounding box.
  @return centMass: DICT detected object center of mass bounding box.
  """
  centMass = {}
  centMass['width'] = bBox['width']/3
  centMass['height'] = bBox['height']/4
  centMass['x'] = bBox['x'] + centMass['width']
  centMass['y'] = bBox['y'] + centMass['height']
  return centMass

def fps():
  """! Defines FPS """
  return 15.0

####################################################
# Fixtures
####################################################
@pytest.fixture()
def camera_obj():
  """!
  Creates a FIXTURE Camera object.
  @return: FIXTURE Camera object.
  """
  param = camera_param()
  cameraInfo = {
    'width': param['width'],
    'height': param['height'],
    'camera points': param['camPts'],
    'map points': param['mapPts'],
    'intrinsics': 70,
  }
  return Camera(param['cameraID'], cameraInfo)

@pytest.fixture()
def scene_obj():
  """!
  Creates a FIXTURE Scene object.
  @return: FIXTURE Scene object.
  """
  return Scene("test", "sample_data/HazardZoneSceneLarge.png")

@pytest.fixture(scope='module')
def scene_obj_with_scale():
  """!
  Returns a scene object with scale value set.
  """
  return Scene("test", "sample_data/HazardZoneSceneLarge.png", 1000)
