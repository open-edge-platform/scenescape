#!/usr/bin/env python3

# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

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
