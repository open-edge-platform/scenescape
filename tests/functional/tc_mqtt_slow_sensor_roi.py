#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from tests.functional.tc_mqtt_sensor_roi import SensorMqttRoi

# This test exercises the case for long delay between sensor updates
TEST_NAME = "NEX-T10461"
SENSOR_DELAY = 60

def test_slow_sensor_roi_mqtt(request, record_xml_attribute):
  test = SensorMqttRoi(TEST_NAME, request, SENSOR_DELAY, record_xml_attribute)
  test.runROIMqtt()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_slow_sensor_roi_mqtt(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
