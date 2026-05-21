#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from tests.functional.test_mqtt_sensor_roi import SensorMqttRoi
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

# This test exercises the case for long delay between sensor updates
TEST_NAME = "NEX-T10461"
SENSOR_DELAY = 60

def test_slow_sensor_roi_mqtt(scenescape_env, demo_scene, request, record_xml_attribute):
  test = SensorMqttRoi(TEST_NAME, request, SENSOR_DELAY, record_xml_attribute)
  test.runROIMqtt()
  assert test.exitCode == 0
