# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser, By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  require_password=True, auth="",
)

PANEL_WAIT_SEC = 100
SCENE_NAME = "Queuing"
CAMERA_NAME = "atag-qcam2"
POSE_AXES = ("posX", "posY", "posZ", "rotX", "rotY", "rotZ")
POSE_TOLERANCE = 0.01
POSITION_CHANGE = 0.25
ROTATION_CHANGE_DEG = 5.0


def read_camera_pose(browser):
  """Read camera position and rotation values from the expanded Pose controls."""
  return {
    axis: float(browser.find_element(By.ID, f"{CAMERA_NAME}-{axis}").get_attribute("value"))
    for axis in POSE_AXES
  }


def set_pose_value(browser, field_id, value):
  """Enter and commit a numeric camera Pose value through its UI field."""
  field = browser.find_element(By.ID, f"{CAMERA_NAME}-{field_id}")
  field.click()
  field.send_keys(Keys.CONTROL, "a")
  field.send_keys(f"{value:.4f}")
  field.send_keys(Keys.TAB)


@common.mock_display
@pytest.mark.test_name("NEX-T10470")
def test_3d_ui_camera_position_management(scenescape_env, params, result_recorder):
  """! Verify 3D camera transform controls and persistence of extrinsics.
  @param    scenescape_env          Test stack and uploaded scene identifiers.
  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  browser = None

  try:
    log.info("Executing: NEX-T10470")
    scene_uids = getattr(scenescape_env, "scene_uids", None) or {}
    scene_uid = scene_uids.get(SCENE_NAME)
    assert scene_uid, f"The '{SCENE_NAME}' scene was not uploaded for this test profile"

    browser = Browser(headless=False, webgl=True)
    assert common.check_page_login(browser, params)

    log.info("1. Open the 3D UI for the Queuing scene.")
    assert common.navigate_directly_to_page(browser, f"/scene/detail/{scene_uid}/")
    assert common.wait_for_elements(
      browser,
      f"{CAMERA_NAME}-control-panel",
      findBy=By.ID,
      maxWait=PANEL_WAIT_SEC,
      refreshPage=False,
    ), f"Camera control panel for '{CAMERA_NAME}' was not found"

    log.info("2. Expand atag-qcam2 settings and its Pose controls.")
    assert common.click_when_clickable(
      browser, (By.ID, f"{CAMERA_NAME}-control-panel"), timeout_s=PANEL_WAIT_SEC
    ), f"Camera control panel for '{CAMERA_NAME}' did not become clickable"
    assert common.click_when_clickable(
      browser, (By.ID, f"{CAMERA_NAME}-transform"), timeout_s=PANEL_WAIT_SEC
    ), f"Pose folder for '{CAMERA_NAME}' did not become clickable"

    initial_pose = read_camera_pose(browser)
    toggle = browser.find_element(By.ID, f"{CAMERA_NAME}-toggle-rotate-translate")
    assert toggle.is_selected(), "Camera should initially be in rotate mode"

    log.info("3. Toggle between rotate and translate modes and verify the mode state.")
    assert common.click_when_clickable(
      browser,
      (By.ID, f"{CAMERA_NAME}-toggle-rotate-translate"),
      timeout_s=PANEL_WAIT_SEC,
    ), "Rotate/translate toggle did not become clickable"
    assert WebDriverWait(browser, PANEL_WAIT_SEC).until(
      lambda driver: not driver.find_element(
        By.ID, f"{CAMERA_NAME}-toggle-rotate-translate"
      ).is_selected()
    ), "Toggle did not switch the transform control to translate mode"
    assert common.click_when_clickable(
      browser,
      (By.ID, f"{CAMERA_NAME}-toggle-rotate-translate"),
      timeout_s=PANEL_WAIT_SEC,
    ), "Rotate/translate toggle did not become clickable a second time"
    assert WebDriverWait(browser, PANEL_WAIT_SEC).until(
      lambda driver: driver.find_element(
        By.ID, f"{CAMERA_NAME}-toggle-rotate-translate"
      ).is_selected()
    ), "Toggle did not switch the transform control back to rotate mode"

    log.info("4. Use the selected camera's Pose controls to update its extrinsics.")

    log.info("5. Rotate the camera and change its position using the Pose controls.")
    expected_pose = initial_pose.copy()
    expected_pose["rotZ"] += ROTATION_CHANGE_DEG
    expected_pose["posX"] += POSITION_CHANGE
    set_pose_value(browser, "rotZ", expected_pose["rotZ"])
    set_pose_value(browser, "posX", expected_pose["posX"])

    for field_id in ("rotZ", "posX"):
      current_value = float(
        browser.find_element(By.ID, f"{CAMERA_NAME}-{field_id}").get_attribute("value")
      )
      assert abs(current_value - expected_pose[field_id]) < POSE_TOLERANCE, (
        f"{field_id} did not update: expected {expected_pose[field_id]}, got {current_value}"
      )

    log.info("6. Save the changed camera extrinsics.")
    assert common.click_when_clickable(
      browser, (By.ID, f"{CAMERA_NAME}-save-camera"), timeout_s=PANEL_WAIT_SEC
    ), "Save camera button did not become clickable after changing Pose values"
    assert WebDriverWait(browser, PANEL_WAIT_SEC).until(
      EC.text_to_be_present_in_element(
        (By.CSS_SELECTOR, "#toast-area .alert-success"),
        "Camera setting has been updated!",
      )
    ), "Camera update success notification was not shown"

    log.info("7. Reload the scene and verify the changed Pose values persisted.")
    browser.refresh()
    assert common.wait_for_elements(
      browser,
      f"{CAMERA_NAME}-control-panel",
      findBy=By.ID,
      maxWait=PANEL_WAIT_SEC,
      refreshPage=False,
    ), f"Camera control panel for '{CAMERA_NAME}' was not found after reload"
    assert common.click_when_clickable(
      browser, (By.ID, f"{CAMERA_NAME}-control-panel"), timeout_s=PANEL_WAIT_SEC
    ), f"Camera control panel for '{CAMERA_NAME}' did not open after reload"
    assert common.click_when_clickable(
      browser, (By.ID, f"{CAMERA_NAME}-transform"), timeout_s=PANEL_WAIT_SEC
    ), f"Pose folder for '{CAMERA_NAME}' did not open after reload"

    saved_pose = read_camera_pose(browser)
    for field_id in ("rotZ", "posX"):
      assert abs(saved_pose[field_id] - expected_pose[field_id]) < POSE_TOLERANCE, (
        f"Saved {field_id} did not persist: expected {expected_pose[field_id]}, "
        f"got {saved_pose[field_id]}"
      )

    result_recorder.success()
  finally:
    if browser is not None:
      browser.quit()
