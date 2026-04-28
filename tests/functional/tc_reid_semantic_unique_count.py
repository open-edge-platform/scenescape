#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Import the shared unique-count expectation and validation behavior.
from tests.functional.tc_reid_unique_count import get_scene_count_bounds, run_test
from scene_common import log

def test_reid_semantic_unique_count(params, record_xml_attribute):
  """! Tests the unique count for each scene when RE-ID with
  semantic classification (age-gender) is enabled.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T19882"
  record_xml_attribute("name", TEST_NAME)
  log.info("Executing: " + TEST_NAME)
  log.info("Test the unique count for each scene when RE-ID with semantic classification is enabled.")

  minimum, maximum = get_scene_count_bounds()
  scene_config = {
    "302cf49a-97ec-402d-a324-c5077b280b7b": {
      "error": False,
      "current": 0,
      "minimum": minimum,
      "maximum": maximum
    }
  }

  run_test(TEST_NAME, "Test the unique count for each scene when RE-ID with semantic classification is enabled.", scene_config, params)
