#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.utils.log import get_logger
from tests.ui.browser import Browser, By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec
from tests.utils.profiles import FULL_STACK
log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

def test_camera_deletion_main(params, record_xml_attribute):
  """! Attach an orphan camera to a scene, delete it from the scene, and verify
  it is removed from the cameras list.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10403"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  try:
    log.info("Executing: " + TEST_NAME)
    browser = Browser()
    wait = WebDriverWait(browser, common.BROWSER_WAIT)
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)
    scene_name = common.TEST_SCENE_NAME
    camera_name = "Automated_Camera1"
    camera_id = "Automated_ID_Camera1"

    assert common.create_orphan_camera(browser, camera_name, camera_id)
    log.info(f"Adding orphan camera: {camera_name} to scene {scene_name}")
    # Orphan cameras expose Edit → Django cam_update (scene picker is #id_scene)
    browser.find_element(By.ID, "nav-cameras").click()
    orphan_row = wait.until(
      EC.presence_of_element_located(
        (
          By.XPATH,
          f"//tr[td[normalize-space()='{camera_name}'] and td[normalize-space()='--']]",
        )
      )
    )
    orphan_row.find_element(By.CSS_SELECTOR, "a[title='Edit']").click()
    wait.until(EC.visibility_of_element_located((By.ID, "id_scene")))
    Select(browser.find_element(By.ID, "id_scene")).select_by_visible_text(
      scene_name
    )
    browser.find_element(
      By.CSS_SELECTOR, "input[type='submit'][value='Update Camera']"
    ).click()
    wait.until(
      EC.presence_of_element_located(
        (By.XPATH, f"//h2[@id='scene_name' and text()='{scene_name}']")
      )
    )

    available_cameras = browser.find_elements(
      By.CSS_SELECTOR, ".card.count-item.camera-card > .card-header"
    )
    camera_names_list = [name.text.replace("--\n", "") for name in available_cameras]
    log.info(f"Available cameras before deletion: {camera_names_list}")
    assert camera_name in "".join(camera_names_list)
    browser.find_element(By.XPATH, f"//a[@title = 'Delete {camera_name}']").click()
    log.info(f"Deleted {camera_name} from the {scene_name}")
    common.confirm_ss_dialog(browser, "Delete")

    log.info("Navigating to cameras menu to verify after deletion.")
    browser.find_element(By.ID, "nav-cameras").click()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody")))
    camera_names_list = []
    rows = browser.find_elements(By.CSS_SELECTOR, "tbody > tr")
    for row in rows:
      cells = row.find_elements(By.TAG_NAME, "td")
      if cells:
        camera_names_list.append(cells[0].text.strip())
    log.info(f"Available cameras after deletion: {camera_names_list}")
    assert camera_name not in camera_names_list
    exit_code = 0
  finally:
    browser.close()
    common.record_test_result(TEST_NAME, exit_code)
  assert exit_code == 0
  return exit_code
