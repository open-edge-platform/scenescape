#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.ui.browser import By
from tests.ui import UserInterfaceTest
from tests.ui import common

def wait_for_calibration(browser, wait_time):
  """! Waits for the auto calibration to initialize.
  @param    browser                 Object wrapping the Selenium driver.
  @param    wait_time               Int seconds to wait.
  @return   autocal_button          Web Element auto calibration button.
  """
  iter_time = 1
  time_passed = 0
  iterations = int(round(wait_time/iter_time))
  for x in range(iterations):
    autocal_button = browser.find_element(By.ID, "auto-autocalibration")
    time.sleep(iter_time)
    time_passed += iter_time
    if autocal_button.is_enabled():
      break
  print()
  print("---------------------------------------------")
  print("After {} seconds autocal enabled: {}".format(time_passed, autocal_button.is_enabled()))
  print("---------------------------------------------")
  return autocal_button

def wait_for_image(browser, wait_time, image_id):
  """! Waits images to load.
  @param    browser                 Object wrapping the Selenium driver.
  @param    wait_time               Int seconds to wait.
  @return   BOOL                    True if image loaded.
  """
  iter_time = 1
  iterations = int(round(wait_time/iter_time))
  for x in range(iterations):
    cam_img = browser.find_element(By.ID, image_id)
    if not cam_img.is_displayed(): # it means that there is no image on UI with "No camera"
      return True
    time.sleep(iter_time)
  return False

class AprilTagCalibrationTest(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    return

  def click_button_by_id(self, button_id):
    """! Finds a button by ID and clicks it.
    @param    button_id    String ID of the button to click.
    @return   None.
    """
    wait = WebDriverWait(self.browser, 10)
    button = wait.until(EC.element_to_be_clickable((By.ID, button_id)))
    button.click()
    return

  def assert_points_within_tolerance(self, actual_points, expected_points, tolerance=0.1):
    """! Validates that calibration points are within tolerance of expected values.
    Order of points is not guaranteed, so points are matched by finding closest pairs.
    @param    actual_points     Dict of actual calibration points.
    @param    expected_points   Dict of expected calibration points.
    @param    tolerance         Float tolerance as percentage (0.1 = 10%).
    @return   None              Raises AssertionError if validation fails.
    """
    # Allow at most one missing point
    missing_count = len(expected_points) - len(actual_points)
    assert missing_count <= 1, \
      f"Too many missing points: expected {len(expected_points)}, got {len(actual_points)}"

    actual_list = list(actual_points.values())
    expected_list = list(expected_points.values())

    # Match each actual point to the closest expected point
    used_expected_indices = set()
    for actual_coords in actual_list:
      # Find the closest expected point that hasn't been used yet
      best_match_idx = None
      best_distance = float('inf')

      for idx, expected_coords in enumerate(expected_list):
        if idx in used_expected_indices:
          continue
        # Calculate Euclidean distance
        distance = ((actual_coords[0] - expected_coords[0])**2 + (actual_coords[1] - expected_coords[1])**2)**0.5
        if distance < best_distance:
          best_distance = distance
          best_match_idx = idx

      assert best_match_idx is not None, "Could not find a match for actual point"
      used_expected_indices.add(best_match_idx)
      expected_coords = expected_list[best_match_idx]

      # Validate each coordinate is within tolerance
      for i in range(2):  # x and y coordinates
        actual = actual_coords[i]
        expected = expected_coords[i]
        coord_tolerance = abs(expected * tolerance)
        assert abs(actual - expected) <= coord_tolerance, \
          f"Point {actual_coords} coordinate[{i}]: {actual} not within {tolerance*100}% of {expected}"

    print(f"✓ {len(actual_list)} calibration points validated within {tolerance*100}% tolerance")
    return

  def checkForMalfunctions(self, cam_url, scene_name, wait_time):
    """! Executes april tag test case.
    @param    cam_url                 String cam calibration url.
    @param    scene_name              String scene name.
    @param    wait_time               Int seconds to wait.
    @return   exit_code               Indicates test success or failure.
    """
    print()
    print("#####    " + scene_name + " Test Case    ####")
    print()

    time.sleep(1)
    cam_list_url = "/cam/list/"
    self.navigateDirectlyToPage(cam_list_url)

    self.navigateDirectlyToPage(cam_url)
    print(f"Navigated to cam calibration page {cam_url}")

    time.sleep(1)

    assert wait_for_image(self.browser, wait_time, "camera_img")
    assert wait_for_image(self.browser, wait_time, "map_img")

    autocal_button = wait_for_calibration(self.browser, wait_time)
    assert autocal_button.is_enabled()
    self.click_button_by_id("reset_points")
    time.sleep(wait_time)
    autocal_button.click()
    time.sleep(wait_time)
    self.click_button_by_id("top_save")
    time.sleep(wait_time)
    self.navigateDirectlyToPage(cam_url)
    time.sleep(wait_time)
    points = get_calibration_points_from_js(self.browser, "camera")
    print("Actual points:", points)

    expected_points = {
        'p0': [42.74131548684735, 663.6953887756321],
        'p1': [244.56545098806737, 615.208280012257],
        'p2': [562.6995395869819, 324.7693256122194],
        'p3': [1061.0969448580838, 653.5331261796596],
        'p4': [197.19155139690756, 202.56618588566755],
        'p5': [997.5488664337493, 238.69529323145943]
    }

    self.assert_points_within_tolerance(points, expected_points, tolerance=0.1)

    return True

  def execute_test(self):
    """! Checks that a user can setup a scene with april tags. """
    MAX_WAIT_TIME = 15
    assert self.login()

    cam_url = "/cam/calibrate/4"
    test_case_1 = self.checkForMalfunctions(cam_url, "Queuing", MAX_WAIT_TIME)

    if test_case_1:
      self.exitCode = 0

def get_calibration_points_from_js(browser, canvas_type):
  """! Gets calibration points directly from JavaScript.
  @param    browser                 Object wrapping the Selenium driver.
  @param    canvas_type             String "camera" or "map".
  @return   dict                    Dictionary of calibration points.
  """
  if canvas_type == "camera":
    script = """
        return window.camera_calibration?.camCanvas?.getCalibrationPoints() || {};
    """
  else:  # map/viewport
    script = """
        return window.camera_calibration?.viewport?.getCalibrationPoints(true) || {};
    """

  points = browser.execute_script(script)
  print(f"Calibration points from {canvas_type}:", points)
  return points

@common.mock_display
def test_april_tag(request, record_xml_attribute):
  """! Checks that a user can setup a scene with april tags.
  @param    request                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T15710"
  record_xml_attribute("name", TEST_NAME)

  test = AprilTagCalibrationTest(TEST_NAME, request, record_xml_attribute)
  test.execute_test()

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_april_tag(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
