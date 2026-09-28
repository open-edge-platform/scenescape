# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest
from tests.ui.browser import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

PANEL_WAIT_SEC = 100
ROI_NAME = "3D_UI_ROI"
NEW_COLOR_HEX = "#ff0000"
NEW_OPACITY = 0.25
MAX_OPACITY = 1.0
NEW_HEIGHT = 5


class Scene3dRoiUserInterfaceTest(UserInterfaceTest):
  BROWSER_WEBGL = True

  def __init__(self, testName, request, scene_name):
    super().__init__(testName, request, None)
    self.scene_name = scene_name

  def create_roi(self):
    """! Creates an ROI on the 2D scene page so it appears in the 3D control panel."""
    assert common.navigate_to_scene(self.browser, self.scene_name)

    self.executeScript("document.getElementById('scale').type='text'")
    self.executeScript("document.getElementById('id_rois').type='text'")
    self.executeScript("document.getElementById('scene-controls').removeAttribute('id')")

    scale = float(self.browser.find_element(By.ID, "scale").get_attribute("value"))
    svg = self.browser.find_element(By.ID, "svgout")
    cx = svg.size["width"] / (2 * scale)
    cy = svg.size["height"] / (2 * scale)
    dx = cx * 0.25
    dy = cy * 0.25
    roi_points = [
      [cx - dx, cy + dy],
      [cx - dx, cy - dy],
      [cx + dx, cy - dy],
      [cx + dx, cy + dy],
    ]
    roi_data = json.dumps([{
      "uuid": "",
      "title": ROI_NAME,
      "points": roi_points,
    }])
    roi_form = self.browser.find_element(By.ID, "roi-form")
    self.executeScript(
      "const field = document.getElementById('id_rois');"
      "field.value = arguments[0];"
      "document.getElementById('roi-form').submit();",
      roi_data,
    )
    WebDriverWait(self.browser, PANEL_WAIT_SEC).until(EC.staleness_of(roi_form))
    return

  def check_roi_controls(self, result_recorder):
    assert self.login()

    log.info("1. Create an ROI via the 2D scene page so it renders in the 3D control panel.")
    self.create_roi()

    log.info("2. Navigate to the Scene detail (3D) page.")
    common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    title_element = common.get_3d_control_folder_title(self.browser, ROI_NAME, PANEL_WAIT_SEC)
    common.expand_3d_control_folder(self.browser, ROI_NAME, title_element, PANEL_WAIT_SEC)

    initial_state = common.get_3d_scene_object_state(self.browser, ROI_NAME)
    assert initial_state["hooksAvailable"], "Test hooks (window.__testScene) are not exposed"
    assert initial_state["found"], f"ROI '{ROI_NAME}' was not found in the scene graph"


    log.info("3. Change ROI color via the control panel.")
    common.set_3d_control_input_value(
      self.browser,
      common.get_3d_control_input(self.browser, ROI_NAME, "color", "@type='color'"),
      NEW_COLOR_HEX,
    )
    state_after_color = common.wait_for_3d_scene_object_state(
      self.browser, ROI_NAME,
      lambda state: state.get("color") == NEW_COLOR_HEX.lstrip("#")
    )
    assert state_after_color["color"] == NEW_COLOR_HEX.lstrip("#"), (
      f"ROI color did not update: expected {NEW_COLOR_HEX}, got {state_after_color['color']}"
    )
    log.info("ROI color updated correctly.")

    log.info("4. The show toggle controls both the ROI and its child label.")
    show_checkbox = common.get_3d_control_input(self.browser, ROI_NAME, "show", "@type='checkbox'")
    was_checked = show_checkbox.is_selected()
    log.info(f"Toggle 'show' (currently {was_checked}) and verify ROI and label visibility.")
    show_checkbox.click()
    state_after_toggle = common.wait_for_3d_scene_object_state(
      self.browser, ROI_NAME,
      lambda state: (
        state.get("visible") is not was_checked
        and state.get("hasLabel")
        and state.get("labelVisible") is not was_checked
      )
    )
    assert state_after_toggle["visible"] is not was_checked, "ROI visibility did not flip after toggling 'show'"
    assert state_after_toggle["hasLabel"], "ROI label was not found in the scene graph"
    assert state_after_toggle["labelVisible"] is not was_checked, (
      "ROI label visibility did not follow the 'show' toggle"
    )

    show_checkbox = common.wait_for_3d_control_enabled(self.browser, ROI_NAME)
    show_checkbox.click()
    state_restored = common.wait_for_3d_scene_object_state(
      self.browser, ROI_NAME,
      lambda state: (
        state.get("visible") is was_checked
        and state.get("labelVisible") is was_checked
      )
    )
    assert state_restored["visible"] is was_checked, "ROI visibility did not revert after re-toggling 'show'"
    assert state_restored["labelVisible"] is was_checked, "ROI label visibility did not revert after re-toggling 'show'"
    common.wait_for_3d_control_enabled(self.browser, ROI_NAME)
    log.info("ROI and label visibility tracked the 'show' toggle correctly.")

    log.info("5. Change ROI opacity via the control panel.")
    common.set_3d_control_input_value(
      self.browser,
      common.get_3d_control_input(self.browser, ROI_NAME, "opacity", "@type='number'"),
      NEW_OPACITY,
    )
    state_after_opacity = common.wait_for_3d_scene_object_state(
      self.browser, ROI_NAME,
      lambda state: abs(state.get("opacity") - NEW_OPACITY) < 0.01
    )
    assert abs(state_after_opacity["opacity"] - NEW_OPACITY) < 0.01, (
      f"ROI opacity did not update: expected {NEW_OPACITY}, got {state_after_opacity['opacity']}"
    )
    log.info("ROI opacity updated correctly.")

    log.info("Verify ROI opacity accepts its maximum boundary value.")
    common.set_3d_control_input_value(
      self.browser,
      common.get_3d_control_input(self.browser, ROI_NAME, "opacity", "@type='number'"),
      MAX_OPACITY,
    )
    state_at_max_opacity = common.wait_for_3d_scene_object_state(
      self.browser, ROI_NAME,
      lambda state: abs(state.get("opacity") - MAX_OPACITY) < 0.01
    )
    assert abs(state_at_max_opacity["opacity"] - MAX_OPACITY) < 0.01, (
      f"ROI opacity did not accept maximum: expected {MAX_OPACITY}, "
      f"got {state_at_max_opacity['opacity']}"
    )
    log.info("ROI opacity maximum boundary handled correctly.")

    log.info("6. Change ROI height via the control panel.")
    common.set_3d_control_input_value(
      self.browser,
      common.get_3d_control_input(self.browser, ROI_NAME, "height", "@type='number'"),
      NEW_HEIGHT,
    )
    state_after_height = common.wait_for_3d_scene_object_state(
      self.browser, ROI_NAME, lambda state: state.get("height") == NEW_HEIGHT,
    )
    assert state_after_height["height"] == NEW_HEIGHT, (
      f"ROI height did not update: expected {NEW_HEIGHT}, got {state_after_height['height']}"
    )
    log.info("ROI height updated correctly.")

    result_recorder.success()
    return


@pytest.mark.fresh_stack
@common.mock_display
@pytest.mark.test_name("NEX-T10472")
def test_3d_ui_roi(scenescape_env, request, result_recorder):
  """! Test that the 3D UI ROI controls affect the ROI scene-graph node.
  @param    request                 List of test parameters.
  @param    result_recorder        Fixture for recording the test result.
  @return   None.
  """
  log.info("Executing: NEX-T10472")
  log.info("Test the 3D UI ROI color, show, opacity, and height controls.")

  scene_uids = getattr(scenescape_env, "scene_uids", None) or {}
  scene_name = next(
    (name for name in ("Demo", "Retail", "Queuing") if name in scene_uids),
    common.TEST_SCENE_NAME,
  )
  test = Scene3dRoiUserInterfaceTest("NEX-T10472", request, scene_name)
  try:
    test.check_roi_controls(result_recorder)
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()
