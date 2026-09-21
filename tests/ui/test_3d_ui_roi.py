# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import json
import pytest
import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest
from tests.ui.browser import By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth="",
)

# This test validates ROI control-panel behavior through the test-only Three.js
# scene hook, which is exposed in test/CI environments with EXPOSE_TEST_HOOKS.

WAIT_SEC = 5
PANEL_WAIT_SEC = 100
ROI_NAME = "3D_UI_ROI"
NEW_COLOR_HEX = "#00ff00"
NEW_OPACITY = 0.25
NEW_HEIGHT = 5


class Scene3dRoiUserInterfaceTest(UserInterfaceTest):
  BROWSER_WEBGL = True

  def __init__(self, testName, request):
    super().__init__(testName, request, None)

  def createRoi(self):
    """! Creates an ROI on the 2D scene page so it appears in the 3D control panel."""
    assert common.navigate_to_scene(self.browser, common.TEST_SCENE_NAME)

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
    self.executeScript(
      "const field = document.getElementById('id_rois');"
      "field.value = arguments[0];"
      "document.getElementById('roi-form').submit();",
      roi_data,
    )
    time.sleep(WAIT_SEC)
    assert roi_points, "Failed to create ROI"
    return

  def getRoiFolderTitle(self):
    """! Waits for the ROI's lil-gui folder to appear in the 3D control panel.
    @return   WebElement                 The folder title element.
    """
    title_xpath = f"//div[@class='title' and normalize-space(text())='{ROI_NAME}']"
    assert common.wait_for_elements(
      self.browser, title_xpath, findBy=By.XPATH, maxWait=PANEL_WAIT_SEC, refreshPage=False,
    ), f"ROI control panel for '{ROI_NAME}' did not load"
    return self.browser.find_element(By.XPATH, title_xpath)

  def expandRoiFolder(self, title_element):
    """! Expands the ROI's lil-gui folder if it is currently collapsed.
    @param    title_element              The folder title element.
    """
    children_xpath = (
      f"//div[@class='title' and normalize-space(text())='{ROI_NAME}']"
      "/following-sibling::div[@class='children'][1]"
    )
    children = self.browser.find_element(By.XPATH, children_xpath)
    if "closed" in (children.get_attribute("class") or ""):
      self.executeScript("arguments[0].click();", title_element)
      time.sleep(WAIT_SEC)
    return

  def getControlInput(self, control_name, input_selector):
    """! Locates an input belonging to a named control row inside the ROI folder.
    @param    control_name               lil-gui control label.
    @param    input_selector              CSS selector for the input.
    @return   WebElement                 The located input element.
    """
    xpath = (
      f"//div[@class='title' and normalize-space(text())='{ROI_NAME}']"
      "/following-sibling::div[@class='children'][1]"
      f"//div[@class='name' and normalize-space(text())='{control_name}']"
      f"/following-sibling::*[1]//input[{input_selector}]"
    )
    return self.browser.find_element(By.XPATH, xpath)

  def getShowCheckbox(self):
    return self.getControlInput("show", "@type='checkbox'")

  def getColorInput(self):
    return self.getControlInput("color", "@type='color'")

  def getOpacityInput(self):
    return self.getControlInput("opacity", "@type='number'")

  def getHeightInput(self):
    return self.getControlInput("height", "@type='number'")

  def setInputValue(self, input_element, value):
    """! Sets a lil-gui input and fires its input event to commit the change.
    @param    input_element              The input element to update.
    @param    value                      New value to assign.
    """
    self.executeScript(
      "arguments[0].value = arguments[1];"
      "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
      input_element, value,
    )
    time.sleep(WAIT_SEC)
    return

  def getRoiState(self):
    """! Reads the live ROI scene-graph node through the test-only hook.
    @return   dict                       Current ROI visibility, color, opacity,
                                         height, and label state.
    """
    script = """
      const testScene = window.__testScene;
      if (!testScene) return {hooksAvailable: false};
      const node = testScene.getObjectByName(arguments[0]);
      if (!node) return {hooksAvailable: true, found: false};
      const label = node.getObjectByName("textObject_" + arguments[0]);
      return {
        hooksAvailable: true,
        found: true,
        visible: node.visible,
        height: node.height,
        color: node.material ? node.material.color.getHexString() : null,
        opacity: node.material ? node.material.opacity : null,
        hasLabel: !!label,
        labelVisible: label ? (label.visible && node.visible) : null,
      };
    """
    return self.executeScript(script, ROI_NAME)

  def checkRoiControls(self, result_recorder):
    assert self.login()

    log.info("1. Create an ROI via the 2D scene page so it renders in the 3D control panel.")
    self.createRoi()

    log.info("2. Navigate to the Scene detail (3D) page.")
    common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    title_element = self.getRoiFolderTitle()
    self.expandRoiFolder(title_element)

    initial_state = self.getRoiState()
    assert initial_state["hooksAvailable"], "Test hooks (window.__testScene) are not exposed"
    assert initial_state["found"], f"ROI '{ROI_NAME}' was not found in the scene graph"

    log.info("3. Verify 3D ROI color changes with the color control.")
    self.setInputValue(self.getColorInput(), NEW_COLOR_HEX)
    state_after_color = self.getRoiState()
    assert state_after_color["color"] == NEW_COLOR_HEX.lstrip("#"), (
      f"ROI color did not update: expected {NEW_COLOR_HEX}, got {state_after_color['color']}"
    )
    log.info("ROI color updated correctly.")

    log.info("4. Verify that the 'show' toggle controls both the ROI and its child label.")
    show_checkbox = self.getShowCheckbox()
    was_checked = show_checkbox.is_selected()
    log.info(f"Toggle 'show' (currently {was_checked}) and verify ROI and label visibility.")
    show_checkbox.click()
    time.sleep(WAIT_SEC)
    state_after_toggle = self.getRoiState()
    assert state_after_toggle["visible"] is not was_checked, "ROI visibility did not flip after toggling 'show'"
    assert state_after_toggle["hasLabel"], "ROI label was not found in the scene graph"
    assert state_after_toggle["labelVisible"] is not was_checked, (
      "ROI label visibility did not follow the 'show' toggle"
    )

    show_checkbox = self.getShowCheckbox()
    show_checkbox.click()
    time.sleep(WAIT_SEC)
    state_restored = self.getRoiState()
    assert state_restored["visible"] is was_checked, "ROI visibility did not revert after re-toggling 'show'"
    assert state_restored["labelVisible"] is was_checked, "ROI label visibility did not revert after re-toggling 'show'"
    log.info("ROI and label visibility tracked the 'show' toggle correctly.")

    log.info("5. Change ROI opacity via the control panel.")
    self.setInputValue(self.getOpacityInput(), NEW_OPACITY)
    state_after_opacity = self.getRoiState()
    assert abs(state_after_opacity["opacity"] - NEW_OPACITY) < 0.01, (
      f"ROI opacity did not update: expected {NEW_OPACITY}, got {state_after_opacity['opacity']}"
    )
    log.info("ROI opacity updated correctly.")

    log.info("6. Change ROI height via the control panel.")
    self.setInputValue(self.getHeightInput(), NEW_HEIGHT)
    state_after_height = self.getRoiState()
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

  test = Scene3dRoiUserInterfaceTest("NEX-T10472", request)
  try:
    test.checkRoiControls(result_recorder)
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()
