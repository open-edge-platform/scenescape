# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser, By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
	profile=FULL_STACK,
	require_password=True, auth="",
)

PANEL_WAIT_SEC = 100
CAMERA_NAME = "testcam"
DELETE_CAMERA_BUTTON_ID = "new-camera-delete-camera"
ADD_CAMERA_BUTTON_XPATH = (
	"//div[@id='panel-3d-controls']//div[contains(@class,'name') "
	"and normalize-space()='add camera']/ancestor::button[1]"
)


def cleanup_camera(browser):
	"""Remove the saved test camera if the test exits before its deletion step."""
	if browser is None:
		return

	try:
		if not browser.find_elements(By.ID, f"{CAMERA_NAME}-control-panel"):
			return
		if common.click_when_clickable(browser, (By.ID, DELETE_CAMERA_BUTTON_ID)):
			alert = WebDriverWait(browser, 10).until(EC.alert_is_present())
			alert.accept()
			WebDriverWait(browser, PANEL_WAIT_SEC).until(
				EC.invisibility_of_element_located((By.ID, f"{CAMERA_NAME}-control-panel"))
			)
	except Exception as error:  # Best-effort cleanup must not mask the test failure.
		log.warning(f"Unable to clean up camera '{CAMERA_NAME}': {error}")


@common.mock_display
@pytest.mark.test_name("NEX-T10560")
def test_3d_ui_camera_deletion(params, result_recorder):
	"""! Verify canceling camera deletion preserves it and confirming deletes it.
	@param    params                  Dict of test parameters.
	@param    result_recorder         Pytest fixture recording the test result.
	"""
	browser = None

	try:
		log.info("Executing: NEX-T10560")
		log.info("Test camera deletion confirmation in the 3D UI.")

		browser = Browser(headless=False, webgl=True)
		assert common.check_page_login(browser, params)

		log.info("1. Navigate to the Scene detail page and open the camera controls.")
		assert common.navigate_directly_to_page(
			browser, f"/scene/detail/{common.TEST_SCENE_ID}/"
		)
		assert common.wait_for_elements(
			browser,
			"camera1-control-panel",
			findBy=By.ID,
			maxWait=PANEL_WAIT_SEC,
			refreshPage=False,
		), "Camera 1 control panel was not found"
		assert common.click_when_clickable(
			browser, (By.ID, "camera1-control-panel"), timeout_s=PANEL_WAIT_SEC
		), "Camera 1 control panel did not become clickable"

		log.info("2. Add a camera, name it testcam, and save it.")
		assert common.click_when_clickable(
			browser, (By.XPATH, ADD_CAMERA_BUTTON_XPATH), timeout_s=PANEL_WAIT_SEC
		), "3D UI add camera button did not become clickable"
		assert common.wait_for_elements(
			browser,
			"new-camera-control-panel",
			findBy=By.ID,
			maxWait=PANEL_WAIT_SEC,
			refreshPage=False,
		), "Temporary new-camera control panel was not created"
		assert common.click_when_clickable(
			browser, (By.ID, "new-camera-control-panel"), timeout_s=PANEL_WAIT_SEC
		), "Temporary new-camera control panel did not become clickable"

		name_input = browser.find_element(By.ID, "new-camera-name")
		name_input.clear()
		name_input.send_keys(CAMERA_NAME)
		assert common.click_when_clickable(
			browser, (By.ID, "new-camera-save-camera"), timeout_s=PANEL_WAIT_SEC
		), "Save camera button did not become clickable"

		camera_panel_id = f"{CAMERA_NAME}-control-panel"
		assert common.wait_for_elements(
			browser,
			camera_panel_id,
			findBy=By.ID,
			maxWait=PANEL_WAIT_SEC,
			refreshPage=False,
		), f"Saved camera control panel was not found: {camera_panel_id}"

		log.info("3. Cancel camera deletion and verify the camera remains.")
		assert common.click_when_clickable(
			browser, (By.ID, DELETE_CAMERA_BUTTON_ID), timeout_s=PANEL_WAIT_SEC
		), "Delete camera button did not become clickable"
		cancel_alert = WebDriverWait(browser, PANEL_WAIT_SEC).until(EC.alert_is_present())
		assert cancel_alert.text == f'Are you sure you want to remove "{CAMERA_NAME}"?'
		cancel_alert.dismiss()
		assert browser.find_elements(By.ID, camera_panel_id), (
			"Camera was removed after canceling the deletion confirmation"
		)

		log.info("4. Confirm camera deletion and verify the camera is removed.")
		assert common.click_when_clickable(
			browser, (By.ID, DELETE_CAMERA_BUTTON_ID), timeout_s=PANEL_WAIT_SEC
		), "Delete camera button did not become clickable after canceling"
		confirm_alert = WebDriverWait(browser, PANEL_WAIT_SEC).until(EC.alert_is_present())
		assert confirm_alert.text == f'Are you sure you want to remove "{CAMERA_NAME}"?'
		confirm_alert.accept()
		WebDriverWait(browser, PANEL_WAIT_SEC).until(
			EC.invisibility_of_element_located((By.ID, camera_panel_id))
		)

		result_recorder.success()

	finally:
		if browser is not None:
			cleanup_camera(browser)
			browser.quit()
