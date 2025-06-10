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

import time

from tests.ui.browser import By
from tests.ui import UserInterfaceTest

class CalPt():
  """! Class to parse calibration point location. """
  def __init__(self, pt_str):
    """! Init CalPt class.
    @param    pt_str                String of point x,y location in image.
    @return   None.
    """
    x_str, y_str = pt_str.split(",")
    self.x = round(float(x_str), 2)
    self.y = round(float(y_str), 2)
    return None

  def value(self):
    """! Return point x,y location as a tuple. """
    return (self.x, self.y)

class CalPtLoc():
  """! Class containing and manipulating calibration point locations. """

  def __init__(self, pt_type) -> None:
    """! Init CalPtLoc class.
    @param    pt_type               String cam or map point type.
    @return   None.
    """
    self.pt_1 = None
    self.pt_2 = None
    self.pt_3 = None
    self.pt_4 = None
    self.pt_type = pt_type
    self.pt_list = None
    return None

  def update_pts(self, browser):
    """! Get the current locations of the calibration points.
    @param    browser                 Object wrapping the Selenium driver.
    @return   None.
    """
    self.pt_1 = CalPt(browser.find_element(By.ID, "id_" + self.pt_type + "_coord1").get_attribute("value"))
    self.pt_2 = CalPt(browser.find_element(By.ID, "id_" + self.pt_type + "_coord2").get_attribute("value"))
    self.pt_3 = CalPt(browser.find_element(By.ID, "id_" + self.pt_type + "_coord3").get_attribute("value"))
    self.pt_4 = CalPt(browser.find_element(By.ID, "id_" + self.pt_type + "_coord4").get_attribute("value"))
    self.pt_list = [self.pt_1.value(), self.pt_2.value(), self.pt_3.value(), self.pt_4.value()]
    return None

  def loc_diff(self, other_loc):
    """! Returns true if at least one calibration point location differs.
    @param    other_loc             CalPtLoc calibration point locations to compare against self.
    @return   Bool                  True if at least one location of self and other_loc points differs, otherwise False.
    """
    for x in range(len(self.pt_list)):
      if self.pt_list[x] != other_loc.pt_list[x]:
        return True
    return False

def get_calibration_pt_locs(browser):
  """! Get calibration points in the map and camera frame.
  @param    browser                 Object wrapping the Selenium driver.
  @return   List                    List of calibration point locations.
  """
  map_pts = CalPtLoc("map")
  map_pts.update_pts(browser)
  cam_pts = CalPtLoc("cam")
  cam_pts.update_pts(browser)
  return [map_pts, cam_pts]

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
    autocal_button = browser.find_element(By.ID, "auto-camcalibration")
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
    if cam_img.is_displayed() and (cam_img.get_attribute('alt') != "Camera Offline"):
      return True
    time.sleep(iter_time)
  return False

class WillOurShipGo(UserInterfaceTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
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
    time.sleep(1)

    assert wait_for_image(self.browser, wait_time, "camera_img")
    assert wait_for_image(self.browser, wait_time, "map_img")
    if scene_name == "Queuing":

      autocal_button = wait_for_calibration(self.browser, wait_time)
      assert autocal_button.is_enabled()

      reset_points_button = self.browser.find_element(By.ID, "reset_points")
      reset_points_button.click()
      time.sleep(1)
      map_pts_1, cam_pts_1 = get_calibration_pt_locs(self.browser)
      autocal_button.click()
      time.sleep(3) # FIXME: should check when the mqtt message is received. Not random sleep.
      map_pts_2, cam_pts_2 = get_calibration_pt_locs(self.browser)
      assert map_pts_1.loc_diff(map_pts_2)
      assert cam_pts_1.loc_diff(cam_pts_2)

    else:
      autocal_button = wait_for_calibration(self.browser, 4)
      assert autocal_button.is_enabled() is False

    return True

  def execute_test(self):
    """! Checks that a user can setup a scene with april tags. """
    MAX_WAIT_TIME = 15
    try:
      assert self.login()

      good_scene_name = "Queuing"
      cam_url = "/cam/calibrate/4"
      test_case_1 = self.checkForMalfunctions(cam_url, good_scene_name, MAX_WAIT_TIME)

      bad_scene_name = "Retail"
      cam_url = "/cam/calibrate/2"
      test_case_2 = self.checkForMalfunctions(cam_url, bad_scene_name, MAX_WAIT_TIME)

      if test_case_1 and test_case_2:
        self.exitCode = 0

    finally:
      self.recordTestResult()


def test_april_tag(request, record_xml_attribute):
  """! Checks that a user can setup a scene with april tags.
  @param    request                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10477"
  record_xml_attribute("name", TEST_NAME)

  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.execute_test()

  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_april_tag(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
