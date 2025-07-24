#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest

import tests.common_test_utils as common
from scene_common.scene_model import SceneModel as Scene
from controller.scene import Scene
from scene_common.camera import Camera

TEST_NAME = "NEX-T10451"
################################################################
# Methods
################################################################
def pytest_sessionstart():
  """! Executes at the beginning of the session. """
  print(f"Executing: {TEST_NAME}")
  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """
  common.record_test_result(TEST_NAME, exitstatus)
  return

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
  sParam['mapPts'] = [[10, 105], [304, 108], [305, 401], [10, 398]]
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
