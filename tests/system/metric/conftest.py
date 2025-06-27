#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
import os
from scene_common.options import TYPE_2

def pytest_addoption(parser):
  """! Function to add command line arguments for test

  @param   parser                    Dict of parameters needed for test
  @returns result                    The putest parser object
  """
  parser.addoption("--metric", action="store", help="metric type")
  parser.addoption("--threshold", action="store", help="threshold as the % of the distance error")
  parser.addoption("--camera_frame_rate", action="store", help="enables tests with input camera running on this frame rate")
  return

@pytest.fixture
def params(request):
  """! Fixture function to set up parameters needed for metric test

  @param   request                   Param used to get the parser values
  @returns params                    Dict of parameters
  """
  dir = os.path.dirname(os.path.abspath(__file__))
  input_cam_1 = os.path.join(dir, "test_data/Cam_x1_0.json")
  input_cam_2 = os.path.join(dir, "test_data/Cam_x2_0.json")
  params = {}
  params["metric"] = request.config.getoption("--metric")
  params["threshold"] = request.config.getoption("--threshold")
  params["camera_frame_rate"] = request.config.getoption("--camera_frame_rate")
  params["default_camera_frame_rate"] = 30
  params["input"] = [input_cam_1, input_cam_2]
  params["config"] = os.path.join(dir, "test_data/config.json")
  params["ground_truth"] = os.path.join(dir, "test_data/gtLoc.json")
  params["rootca"] = "/run/secrets/certs/scenescape-ca.pem"
  params["auth"] = "/run/secrets/percebro.auth"
  params["mqtt_broker"] = "broker.scenescape.intel.com"
  params["mqtt_port"] = 1883
  params["trackerconfig"] = os.path.join(dir, "test_data/tracker-config.json")
  return params

@pytest.fixture
def assets():
  """! Fixture function that returns Object Library assets

  @returns params                    Tuple of dict
  """
  asset_1 = {
    'name': 'person',
    'tracking_radius': 2.0,
    'x_size': 0.5,
    'y_size': 0.5,
    'z_size': 2.0
  }
  asset_2 = {
    'name': 'person',
    'tracking_radius': 2.0,
    'x_size': 10.0,
    'y_size': 10.0,
    'z_size': 2.0
  }
  asset_3 = {
    'name': 'person',
    'tracking_radius': 0.1,
    'x_size': 0.5,
    'y_size': 0.5,
    'z_size': 2.0
  }
  asset_4 = {
    'name': 'FW190D',
    'shift_type': TYPE_2
  }
  return (asset_1, asset_2, asset_3, asset_4)
