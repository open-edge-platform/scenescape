# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
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

WAIT_SEC = 5
PANEL_WAIT_SEC = 100
TRIPWIRE_NAME = "3D_UI_Tripwire"
NEW_COLOR_HEX = "#00ff00"
NEW_HEIGHT = 5


class Scene3dTripwireUserInterfaceTest(UserInterfaceTest):
  BROWSER_WEBGL = True

  def __init__(self, testName, request):
    super().__init__(testName, request, None)

  def createTripwire(self):
    """! Creates a tripwire on the 2D scene page so it appears in the 3D control panel."""
    assert common.navigate_to_scene(self.browser, common.TEST_SCENE_NAME)
    tw_points = common.create_tripwire(self.browser, TRIPWIRE_NAME)
    assert tw_points, "Failed to create tripwire"
    return

  def getTripwireFolderTitle(self):
    """! Waits for the tripwire's lil-gui folder to appear in the 3D control panel.
    @return   WebElement                 The folder title element.
    """
    title_xpath = f"//div[@class='title' and normalize-space(text())='{TRIPWIRE_NAME}']"
    assert common.wait_for_elements(
      self.browser, title_xpath, findBy=By.XPATH, maxWait=PANEL_WAIT_SEC, refreshPage=False,
    ), f"Tripwire control panel for '{TRIPWIRE_NAME}' did not load"
    return self.browser.find_element(By.XPATH, title_xpath)

  def expandTripwireFolder(self, title_element):
    """! Expands the tripwire's lil-gui folder if it is currently collapsed.
    @param    title_element              The folder title element.
    """
    children_xpath = (
      f"//div[@class='title' and normalize-space(text())='{TRIPWIRE_NAME}']"
      "/following-sibling::div[@class='children'][1]"
    )
    children = self.browser.find_element(By.XPATH, children_xpath)
    if "closed" in (children.get_attribute("class") or ""):
      self.executeScript("arguments[0].click();", title_element)
      time.sleep(WAIT_SEC)
    return

  def getControlInput(self, control_name, input_selector):
    """! Locates an input belonging to a named control row inside the tripwire's folder.
    @param    control_name               lil-gui control label (e.g. "color", "height", "show").
    @param    input_selector              CSS selector for the input, scoped to the control's widget.
    @return   WebElement                 The located input element.
    """
    xpath = (
      f"//div[@class='title' and normalize-space(text())='{TRIPWIRE_NAME}']"
      "/following-sibling::div[@class='children'][1]"
      f"//div[@class='name' and normalize-space(text())='{control_name}']"
      f"/following-sibling::*[1]//input[{input_selector}]"
    )
    return self.browser.find_element(By.XPATH, xpath)

  def getShowCheckbox(self):
    return self.getControlInput("show", "@type='checkbox'")

  def getColorInput(self):
    return self.getControlInput("color", "@type='color'")

  def getHeightInput(self):
    return self.getControlInput("height", "@type='number'")

  def setInputValue(self, input_element, value):
    """! Sets a lil-gui input's value via script and fires the "input" event
    that lil-gui controllers listen on to commit the change immediately.
    @param    input_element              The <input> element to update.
    @param    value                      New value to assign.
    """
    self.executeScript(
      "arguments[0].value = arguments[1];"
      "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
      input_element, value,
    )
    time.sleep(WAIT_SEC)
    return

  def getTripwireState(self):
    """! Reads the live tripwire scene-graph node via the test-only
    window.__testScene hook.
    @return   dict                       hooksAvailable/found/visible/height/
                                         color/hasLabel/labelVisible, per availability.
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
        hasLabel: !!label,
        labelVisible: label ? (label.visible && node.visible) : null,
      };
    """
    return self.executeScript(script, TRIPWIRE_NAME)

  def checkTripwireControls(self, result_recorder):
    assert self.login()

    log.info("Create a tripwire via the 2D scene page so it renders in the 3D control panel.")
    self.createTripwire()

    log.info("Navigate to the Scene detail (3D) page.")
    common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    title_element = self.getTripwireFolderTitle()
    self.expandTripwireFolder(title_element)

    initial_state = self.getTripwireState()
    assert initial_state["hooksAvailable"], "Test hooks (window.__testScene) are not exposed"
    assert initial_state["found"], f"Tripwire '{TRIPWIRE_NAME}' was not found in the scene graph"

    # 1. Verify 3D tripwire changes color with slider.
    log.info("Change tripwire color via the control panel.")
    color_input = self.getColorInput()
    self.setInputValue(color_input, NEW_COLOR_HEX)
    state_after_color = self.getTripwireState()
    assert state_after_color["color"] == NEW_COLOR_HEX.lstrip("#"), (
      f"Tripwire color did not update: expected {NEW_COLOR_HEX}, got {state_after_color['color']}"
    )
    log.info("Tripwire color updated correctly.")

    # 2 & 3. Verify 3D tripwire (and label) visibility when show is toggled.
    # New tripwires default to visible=false (scenetripwire.js), so read the
    # actual starting state instead of assuming it is checked.
    show_checkbox = self.getShowCheckbox()
    was_checked = show_checkbox.is_selected()
    log.info(f"Toggle 'show' (currently {was_checked}) and verify the tripwire and its label follow.")
    show_checkbox.click()
    time.sleep(WAIT_SEC)
    state_after_toggle = self.getTripwireState()
    assert state_after_toggle["visible"] is not was_checked, "Tripwire visibility did not flip after toggling 'show'"
    assert state_after_toggle["hasLabel"], "Tripwire label was not found in the scene graph"
    assert state_after_toggle["labelVisible"] is not was_checked, (
      "Tripwire label visibility did not follow the 'show' toggle"
    )

    log.info("Toggle 'show' back and verify the tripwire and its label return to the original state.")
    show_checkbox = self.getShowCheckbox()
    show_checkbox.click()
    time.sleep(WAIT_SEC)
    state_restored = self.getTripwireState()
    assert state_restored["visible"] is was_checked, "Tripwire visibility did not revert after re-toggling 'show'"
    assert state_restored["labelVisible"] is was_checked, "Tripwire label visibility did not revert after re-toggling 'show'"
    log.info("Tripwire and label visibility tracked the 'show' toggle correctly.")

    # 4. Verify 3D tripwire height changes with slider.
    log.info("Change tripwire height via the control panel.")
    height_input = self.getHeightInput()
    self.setInputValue(height_input, NEW_HEIGHT)
    state_after_height = self.getTripwireState()
    assert state_after_height["height"] == NEW_HEIGHT, (
      f"Tripwire height did not update: expected {NEW_HEIGHT}, got {state_after_height['height']}"
    )
    log.info("Tripwire height updated correctly.")

    result_recorder.success()
    return


@pytest.mark.fresh_stack
@common.mock_display
@pytest.mark.test_name("NEX-T10471")
def test_3d_ui_tripwire(scenescape_env, request, result_recorder):
  """! Test that the 3D UI tripwire control panel's color, show, and height
  controls correctly affect the tripwire's scene-graph node.
  @param    request                 List of test parameters.
  @param    result_recorder        Fixture for recording the test result.
  @return   None.
  """
  log.info("Executing: NEX-T10471")
  log.info("Test the 3D UI tripwire color, show, and height controls.")

  test = Scene3dTripwireUserInterfaceTest("NEX-T10471", request)
  try:
    test.checkTripwireControls(result_recorder)
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()
