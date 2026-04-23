#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException

MAX_ATTEMPTS = 10

def click_generate_mesh(browser, timeout=30):
  el = WebDriverWait(browser, timeout).until(
      EC.presence_of_element_located((By.ID, "generate_mesh"))
  )

  browser.execute_script("arguments[0].scrollIntoView({block:'center'});", el)

  el = WebDriverWait(browser, timeout).until(
      EC.visibility_of_element_located((By.ID, "generate_mesh"))
  )

  try:
    ActionChains(browser).move_to_element(el).pause(0.1).click(el).perform()
  except Exception:
    browser.execute_script("arguments[0].click();", el)

def create_mesh_from_cameras(browser):
  """ Create mesh from cameras and verify success alert.
  @param    browser     The Selenium WebDriver instance.
  """
  click_generate_mesh(browser)
  try:
    alert = WebDriverWait(browser, 60).until(EC.alert_is_present())
    alert_text = alert.text
    print(alert_text)
    assert alert_text == 'Mesh generated successfully! The scene map has been updated.'
    alert.accept()
  except TimeoutException:
    raise AssertionError("Timed out waiting for mesh generation success alert from cameras")
  return

def create_mesh_from_video(browser, video_file):
  """ Create mesh from video file and verify success alert.
  @param    browser     The Selenium WebDriver instance.
  @param    video_file  The path to the video file to be used for mesh creation.
  """
  browser.refresh()
  browser.find_element(By.ID, "id_map").send_keys(video_file)
  click_generate_mesh(browser)
  try:
    alert = WebDriverWait(browser, 60 * 10).until(EC.alert_is_present())
    alert_text = alert.text
    assert alert_text == 'Mesh generated successfully! The scene map has been updated.'
    alert.accept()
  except TimeoutException:
    raise AssertionError("Timed out waiting for mesh generation success alert from video")
  return

def test_mesh_creation(params, record_xml_attribute):
  """ Test case to verify mesh creation from cameras and video file.
  @param    params                  Test parameters.
  @param    record_xml_attribute     Function to record test attributes in XML report.
  """
  TEST_NAME = "NEX-T10470"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  try:
    print("Executing: " + TEST_NAME)
    browser = Browser()
    video_file = "/workspace/sample_data/apriltag-cam1.mp4"
    assert common.check_page_login(browser, params)
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)
    assert common.delete_camera(browser, "camera3")
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)

    browser.find_element(By.ID, "scene-edit").click()
    browser.refresh()
    for attempt in range(MAX_ATTEMPTS):
      found = common.wait_for_elements(browser, "generate_mesh", findBy=By.ID)
      if found:
        break
      browser.refresh()
      time.sleep(1)

    assert found, "generate_mesh button not found after retries"
    create_mesh_from_cameras(browser)
    create_mesh_from_video(browser, video_file)
    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return
