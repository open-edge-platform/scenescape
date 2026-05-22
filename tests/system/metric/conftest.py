#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import os
from scene_common.options import TYPE_2
from pathlib import Path
import sys

# Import controller module
_controller_src = Path(__file__).resolve().parent.parent.parent.parent / "controller" / "src"
if str(_controller_src) not in sys.path:
  sys.path.insert(0, str(_controller_src))

# Import common test utils module
_common_test_utils_src = Path(__file__).resolve().parent.parent.parent.parent
if str(_common_test_utils_src) not in sys.path:
  sys.path.insert(0, str(_common_test_utils_src))


from controller.controller_mode import ControllerMode

@pytest.fixture(scope='session', autouse=True)
def initialize_controller_mode():
  """Initialize ControllerMode before any tests run."""
  ControllerMode.initialize(analytics_only=False)
  yield
  ControllerMode.reset()

TRACKER_CONFIGS = [
  "tracker-config.json",
  "tracker-config-time-chunking.json",
]

# Default thresholds per metric type
METRIC_THRESHOLDS = [
  ("msoce", 0.05),
  ("idc-error", 0.05),
  ("velocity", 0.15),
]

_ALL_PARAMS = [
  (tc, m, t)
  for tc in TRACKER_CONFIGS
  for m, t in METRIC_THRESHOLDS
]

def pytest_addoption(parser):
  """! Function to add command line arguments for test

  @param   parser                    Dict of parameters needed for test
  @returns result                    The putest parser object
  """
  parser.addoption("--metric", action="store", help="metric type (filters parametrized metrics)")
  parser.addoption("--threshold", action="store", help="threshold as the % of the distance error")
  parser.addoption("--camera_frame_rate", action="store", help="enables tests with input camera running on this frame rate")
  return

@pytest.fixture(
  params=_ALL_PARAMS,
  ids=["{}-{}".format(tc, m) for tc, m, _ in _ALL_PARAMS],
)
def params(request):
  """! Fixture function to set up parameters needed for metric test

  @param   request                   Param used to get the parser values
  @returns params                    Dict of parameters
  """
  tracker_config, metric, threshold = request.param

  cli_metric = request.config.getoption("--metric")
  if cli_metric and metric != cli_metric:
    pytest.skip("metric '{}' not selected (--metric={})".format(metric, cli_metric))

  cli_threshold = request.config.getoption("--threshold")
  if cli_threshold:
    threshold = cli_threshold

  dir = os.path.dirname(os.path.abspath(__file__))
  input_cam_1 = os.path.join(dir, "dataset/Cam_x1_0.json")
  input_cam_2 = os.path.join(dir, "dataset/Cam_x2_0.json")
  params = {}
  params["metric"] = metric
  params["threshold"] = str(threshold)
  params["camera_frame_rate"] = request.config.getoption("--camera_frame_rate")
  params["default_camera_frame_rate"] = 30
  params["input"] = [input_cam_1, input_cam_2]
  params["config"] = os.path.join(dir, "dataset/config.json")
  params["ground_truth"] = os.path.join(dir, "dataset/gtLoc.json")
  params["rootca"] = "/run/secrets/certs/scenescape-ca.pem"
  params["auth"] = "/run/secrets/controller.auth"
  params["mqtt_broker"] = "broker.scenescape.intel.com"
  params["mqtt_port"] = 1883
  params["trackerconfig"] = os.path.join(dir, "dataset", tracker_config)

  if "time-chunking" in tracker_config:
    params["trackerconfig_name"] = "time-chunking"
  else:
    params["trackerconfig_name"] = "event-based"
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
