#!/usr/bin/env python3

# Copyright (C) 2022-2024 Intel Corporation
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
from tests.ui.browser import Browser
import tests.ui.common_ui_test_utils as common

def test_delete_sensor_main(params, record_xml_attribute):
  """! Checks that sensors can be deleted from scenes.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10399"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    print("Test deleting sensors")
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    sensor_id_1 = "Sensor1"
    sensor_id_2 = "Sensor2"
    scene_name_1 = "Scene-1"
    scene_name_2 = "Scene-2"
    sensor_name_1 = "Sensor_1"
    sensor_name_2 = "Sensor_2"
    scale = 1000
    map_image = os.path.join(common.TEST_MEDIA_PATH, "SampleJpegMap.jpeg")

    print("Creating Scenes: " + scene_name_1 + ", " + scene_name_2)
    common.create_scene(browser, scene_name_1, scale, map_image)
    common.create_scene(browser, scene_name_2, scale, map_image)
    common.create_sensor_from_scene(browser, sensor_id_1, sensor_name_1, scene_name_1)
    common.create_sensor_from_scene(browser, sensor_id_2, sensor_name_2, scene_name_2)

    ### After deleting the Scene-2, Sensor_2 must be orphan ###
    common.delete_scene(browser, scene_name_2)
    assert common.delete_sensor(browser, sensor_name_1)
    print(sensor_name_1 + " was assigned to " + scene_name_1 + " and can be deleted")
    assert common.delete_sensor(browser, sensor_name_2)
    print(sensor_name_2 + " was orphaned(--) and can be deleted")
    common.delete_scene(browser, scene_name_1)
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
