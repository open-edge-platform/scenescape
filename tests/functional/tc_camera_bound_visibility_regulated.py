#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time

import pytest
from scene_common import log
from tests.functional.common_camera_bounds import CameraBounds, test_wait_time, check_interval


class CameraBoundVisibilityRegulated(CameraBounds):
  def check_camera_bound_visibility(self):
    start_time = time.time()

    while time.time() - start_time < test_wait_time:
      with self.message_lock:
        if self.visibility_topic == "regulated":
          if self.regulated_has_camera_bounds and not self.unregulated_has_camera_bounds:
            log.info(
                "PASS: camera_bounds for the tracked objects are published only into regulated topic")
            return
        else:
          raise ValueError(f"Unknown visibility_topic: {self.visibility_topic}")

      log.info(
          f"Waiting for validation "
          f"(visibility={self.visibility_topic})..."
      )
      time.sleep(check_interval)

    # Fail conditions — only reached on timeout
    if self.visibility_topic == "regulated":
      raise AssertionError("Expected camera_bounds ONLY in regulated topic")


@pytest.mark.parametrize("test_name", ["NEX-T10582"])
def test_camera_bound_visibility(
        params, pytestconfig, record_xml_attribute, test_name):
  record_xml_attribute("name", test_name)

  visibility_topic = pytestconfig.getoption("visibility_topic")
  test = CameraBoundVisibilityRegulated()
  exit_code = test.run(params, visibility_topic, test_name)

  assert exit_code == 0
  return exit_code
