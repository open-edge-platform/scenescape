#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import time
from scene_common import log
import tests.ui.common_ui_test_utils as common
from tests.ui.browser import By, Browser

@common.mock_display
def test_scene_control_panel(params, record_xml_attribute):
  """! Test the Scene Control Panel in the 3D UI.
  @param    params                  List of test parameters.
  @param    record_xml_attribute    Function for recording test name.
  @return   exit_code               Boolean representing whether the test passed or failed.
  """
  TEST_NAME = "NEX-T10474"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  WAIT_SEC = 1

  try:
    log.info("Executing: " + TEST_NAME)
    log.info("Test for scene control panel in 3D UI")

    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    interaction_page = common.InteractWith3DScene(browser)
    common.navigate_directly_to_page(browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    log.info("Turn off tracked objects and hide stats graph.")
    time.sleep(WAIT_SEC)
    common.selenium_wait_for_elements(browser, (By.ID, "camera1-control-panel"), 100)
    browser.find_element(By.ID, "tracked-objects-button").click()
    interaction_page.hide_stats()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take first floor plane screenshot.")
    time.sleep(WAIT_SEC)
    plane_view_1 = interaction_page.get_page_screenshot()

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Toggle floor plane off.")
    time.sleep(WAIT_SEC)
    browser.find_element(By.ID, 'plane-view-label').click()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take second floor plane screenshot.")
    time.sleep(WAIT_SEC)
    plane_view_2 = interaction_page.get_page_screenshot()

    log.info("AC(1) Check if floor plane screenshots are different.")
    assert common.compare_images(plane_view_1, plane_view_2, 80.0)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Toggle floor plane on.")
    time.sleep(WAIT_SEC)
    plane_view = browser.find_element(By.ID, "plane-view-label")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(plane_view).click(card_title).click(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take first 3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_3d_1 = interaction_page.get_page_screenshot()

    log.info("AC(1) Check if floor plane screenshot is identical after toggling back on.")
    assert not common.compare_images(plane_view_1, screen_3d_1, 8)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Change map perspective.")
    time.sleep(WAIT_SEC)
    common.change_map_perspective(browser)

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take second 3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_3d_2 = interaction_page.get_page_screenshot()

    log.info("AC(4) Check if 3D screenshots are different.")
    assert common.compare_images(screen_3d_1, screen_3d_2, 25)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Reset 3D view.")
    reset = browser.find_element(By.ID, "reset")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(reset).move_to_element(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take third 3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_3d_3 = interaction_page.get_page_screenshot()

    log.info("AC(5) Check if 3D screenshots are identical.")
    assert not common.compare_images(screen_3d_1, screen_3d_3, 0)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Click 2D view.")
    button_2d = browser.find_element(By.ID, "2d-button")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(button_2d).move_to_element(card_title).perform()

    log.info("Take first 2D screenshot.")
    time.sleep(WAIT_SEC)
    screen_2d_1 = interaction_page.get_page_screenshot()

    log.info("Change map perspective.")
    time.sleep(WAIT_SEC)
    common.change_map_perspective(browser)

    log.info("Take second 2D screenshot.")
    time.sleep(WAIT_SEC)
    screen_2d_2 = interaction_page.get_page_screenshot()

    log.info("AC(3) Check if 2D screenshots are identical.")
    assert not common.compare_images(screen_2d_1, screen_2d_2, 0)

    log.info("Click 3D view.")
    button_3d = browser.find_element(By.ID, "3d-button")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(button_3d).move_to_element(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take first 2D/3D screenshot.")
    time.sleep(WAIT_SEC)
    screen_2d_3d_1 = interaction_page.get_page_screenshot()

    log.info("Change map perspective.")
    time.sleep(WAIT_SEC)
    common.change_map_perspective(browser)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Click 2D view.")
    time.sleep(WAIT_SEC)
    button_2d = browser.find_element(By.ID, "2d-button")
    card_title = browser.find_element(By.CLASS_NAME, "card-title")
    action = browser.actionChains()
    action.click(button_2d).move_to_element(card_title).perform()

    log.info("Hide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.hide_control_panels()

    log.info("Take second 2D/3D screenshot.")
    time.sleep(WAIT_SEC)

    screen_2d_3d_2 = interaction_page.get_page_screenshot()

    log.info("AC(3) Check if 2D and 3D screenshots are similar (2D perspective is slightly different).")
    assert not common.compare_images(screen_2d_3d_1, screen_2d_3d_2, 2)

    log.info("Unhide 3D panels.")
    time.sleep(WAIT_SEC)
    interaction_page.unhide_control_panels()

    log.info("Navigate to scene details.")
    browser.find_element(By.ID, "scene-detail-button").click()

    log.info("AC(2) Check if URL has changed to scene details.")
    time.sleep(WAIT_SEC)
    assert browser.current_url.split("/")[-2] == "1"

    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
