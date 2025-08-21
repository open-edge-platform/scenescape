#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def create_user(browser, user_name, pwd):
  """! This function uses the admin page to create a Scenescape web UI user.
  @param    browser   Object wrapping the Selenium driver.
  @param    user_name   Name of the user to be created.
  @param    pwd         Password for the created user.
  @return  BOOL      Boolean representing a successful reset.
  """
  print("Creating User")
  original_window = browser.current_window_handle
  browser.find_element(By.XPATH, "//a[@href = '/admin']").click()

  time.sleep(5)
  # Checking that we have only two windows open
  assert len(browser.window_handles) == 2

  admin_page_title = 'Site administration | Django site admin'
  browser.switch_to.window(browser.window_handles[-1])
  print("Switched page to:", browser.title)
  if browser.title != admin_page_title:
    print("Unable to create test user")
    return False

  add_user_btn_xpath = "//a[@href = '/admin/auth/user/add/']"
  browser.find_element(By.XPATH, add_user_btn_xpath).click()

  username = browser.find_element(By.ID, "id_username")
  username.clear()
  username.send_keys(user_name)

  password = browser.find_element(By.ID, "id_password1")
  password.clear()
  password.send_keys(pwd)

  confirm_password = browser.find_element(By.ID, "id_password2")
  confirm_password.clear()
  confirm_password.send_keys(pwd)

  save_xpath = "//input[@value = 'Save']"
  browser.find_element(By.XPATH, save_xpath).click()
  print("Added test user")
  browser.close()
  browser.switch_to.window(original_window)
  return True

def test_crud_operations(params, record_xml_attribute):
  """! Checks that while an admin can perform CRUD functions
  on scenes, cameras, and sensors via the web UI a regular user cannot.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10418"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  try:
    print("Executing: " + TEST_NAME)
    browser = Browser()
    wait = WebDriverWait(browser, 5)
    assert common.check_page_login(browser, params)
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)

    #scene edit and delete
    edit_demo_xpath = "//a[@title = 'Edit Demo']"
    admin_edit_demo_btn = browser.find_elements(By.XPATH, edit_demo_xpath)
    delete_demo_xpath = "//a[@title = 'Delete Demo']"
    admin_del_demo_btn = browser.find_elements(By.XPATH, delete_demo_xpath)

    #cameras manage and delete
    cameras_tab_xpath = "//a[@title = 'Cameras Tab']"
    browser.find_element(By.XPATH, cameras_tab_xpath).click()
    admin_new_camera_btn = browser.find_elements(By.LINK_TEXT, '+ New Camera')
    manage_camera1_xpath = "//a[@title = 'Manage camera1']"
    admin_manage_camera1_btn = browser.find_elements(By.XPATH, manage_camera1_xpath)
    delete_camera1_btn = "//a[@title = 'Delete camera1']"
    admin_delete_camera1_btn = browser.find_elements(By.XPATH, delete_camera1_btn)

    # Sensors Regions Tripwire Creation btns
    browser.find_element(By.ID, "sensors-tab").click()
    admin_new_sensor_btn = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, '+ New Sensor')))
    admin_new_sensor_btn = browser.find_elements(By.LINK_TEXT, '+ New Sensor')
    browser.find_element(By.ID, "regions-tab").click()
    admin_new_region_btn = browser.find_elements(By.ID, 'new-roi')
    browser.find_element(By.ID, "tripwires-tab").click()
    admin_new_tripwire_btn = browser.find_elements(By.ID, 'new-tripwire')

    admin_privileged_link = browser.find_elements(By.XPATH, "//a[@href = '/admin']")

    print("Edit Demo (icon), Delete Demo (icon), Manage camera1 (icon), Delete camera1"
          " (icon), +New Sensor, +New Region, +New Tripwire")

    # Adding testuser
    user_cred = {
      'user': 'testuser',
      'password': '#dummy_pwd123',
      'weburl': params['weburl']
    }

    assert create_user(browser, user_cred['user'], user_cred['password'])
    print("Logging Out...")
    browser.find_element(By.LINK_TEXT, 'Log Out').click()
    assert common.check_page_login(browser, user_cred)

    print("Logged in as an unpriviledged test user.")
    assert common.navigate_to_scene(browser, common.TEST_SCENE_NAME)

    #scene edit and delete
    edit_demo_xpath = "//a[@title = 'Edit Demo']"
    edit_demo_btn = browser.find_elements(By.XPATH, edit_demo_xpath)
    delete_demo_xpath = "//a[@title = 'Delete Demo']"
    delete_demo_btn = browser.find_elements(By.XPATH, delete_demo_xpath)

    #cameras manage and delete
    cameras_tab_xpath = "//a[@title = 'Cameras Tab']"
    browser.find_element(By.XPATH, cameras_tab_xpath).click()
    new_camera_btn = browser.find_elements(By.LINK_TEXT, '+ New Camera')
    manage_camera1_xpath = "//a[@title = 'Manage camera1']"
    manage_camera1_btn = browser.find_elements(By.XPATH, manage_camera1_xpath)
    delete_camera1_btn = "//a[@title = 'Delete camera1']"
    delete_camera1_btn = browser.find_elements(By.XPATH, delete_camera1_btn)

    # Sensors Regions Tripwire Creation btns
    browser.find_element(By.ID, "sensors-tab").click()
    new_sensor_btn = browser.find_elements(By.LINK_TEXT, '+ New Sensor')
    browser.find_element(By.ID, "regions-tab").click()
    new_region_btn = browser.find_elements(By.LINK_TEXT, '+ New Region')
    browser.find_element(By.ID, "tripwires-tab").click()
    new_tripwire_btn = browser.find_elements(By.LINK_TEXT, '+ New Tripwire')

    admin_unprivileged_link = browser.find_elements(By.XPATH, "//a[@href = '/admin']")

    # All of the below elements must be 0 as the test
    # user is not expected to have these elements
    assert not len(edit_demo_btn) and not len(delete_demo_btn) \
      and not len(new_camera_btn) and not len(manage_camera1_btn) \
      and not len(delete_camera1_btn) and not len(new_sensor_btn) \
      and not len(new_region_btn) and not len(new_tripwire_btn) \
      and not len(admin_unprivileged_link)

    # All of the below elements must be non-zero for the admin user
    assert len(admin_edit_demo_btn) and len(admin_del_demo_btn) \
      and len(admin_new_camera_btn) and len(admin_manage_camera1_btn) \
      and len(admin_delete_camera1_btn) and len(admin_new_sensor_btn) \
      and len(admin_new_region_btn) and len(admin_new_tripwire_btn) \
      and len(admin_privileged_link)

    print("Edit Demo (icon), Delete Demo (icon), Manage camera1 (icon), Delete camera1"
          " (icon), +New Sensor, +New Region, +New Tripwire")
    print("Test user does not have the above mentioned elements as Expected")
    exit_code = 0

  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
