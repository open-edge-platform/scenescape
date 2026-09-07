#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Import the shared test infrastructure from test_reid_unique_count
from tests.functional.test_reid_unique_count import run_test, get_scene_count_bounds
from tests.functional.reid_backend import get_reid_profile_module
from tests.utils.spec import FuncTestSpec
from tests.utils.log import get_logger
import pytest

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=get_reid_profile_module(semantic=True),
)

@pytest.mark.test_name("NEX-T19882")
def test_reid_semantic_unique_count(params):
  """! Tests the unique count for each scene when RE-ID with
  semantic classification (age-gender) is enabled.
  @param    params                  Dict of test parameters.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T19882"
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
