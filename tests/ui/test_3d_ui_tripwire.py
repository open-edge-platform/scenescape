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
NEW_COLOR_HEX = "#ff0000"
NEW_HEIGHT = 5


class Scene3dTripwireUserInterfaceTest(UserInterfaceTest):
  BROWSER_WEBGL = True

  def __init__(self, testName, request):
    super().__init__(testName, request, None)

  def create_tripwire(self):
    """! Creates a tripwire on the 2D scene page so it appears in the 3D control panel."""
    assert common.navigate_to_scene(self.browser, common.TEST_SCENE_NAME)
    tripwire_points = common.create_tripwire(self.browser, TRIPWIRE_NAME)
    assert tripwire_points, "Failed to create tripwire"
    return

  def get_tripwire_folder_title(self):
    """! Waits for the tripwire's lil-gui folder to appear in the 3D control panel.
    @return   WebElement                 The folder title element.
    """
    title_xpath = f"//div[@class='title' and normalize-space(text())='{TRIPWIRE_NAME}']"
    assert common.wait_for_elements(
      self.browser, title_xpath, findBy=By.XPATH, maxWait=PANEL_WAIT_SEC, refreshPage=False,
    ), f"Tripwire control panel for '{TRIPWIRE_NAME}' did not load"
    return self.browser.find_element(By.XPATH, title_xpath)

  def expand_tripwire_folder(self, title_element):
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

  def get_control_input(self, control_name, input_selector):
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

  def get_show_checkbox(self):
    return self.get_control_input("show", "@type='checkbox'")

  def get_color_input(self):
    return self.get_control_input("color", "@type='color'")

  def get_height_input(self):
    return self.get_control_input("height", "@type='number'")

  def set_input_value(self, input_element, value):
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

  def get_tripwire_state(self):
    """! Reads the live tripwire scene-graph node via the test-only
    window.__testScene hook.
    @return   dict                       hooks_available/found/visible/height/
                                         color/has_label/label_visible, per availability.
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

  def wait_for_label(self, timeout_seconds=30):
    """! Poll until the asynchronously created text label is present in the scene."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
      state = self.get_tripwire_state()
      if state.get("hasLabel"):
        return state
      time.sleep(0.25)
    state = self.get_tripwire_state()
    assert state.get("hasLabel"), "Tripwire label was not created in the scene graph in time"
    return state

  def check_tripwire_controls(self, result_recorder):
    assert self.login()

    log.info("1. Create a tripwire via the 2D scene page so it renders in the 3D control panel.")
    self.create_tripwire()

    log.info("2. Navigate to the Scene detail (3D) page.")
    common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    title_element = self.get_tripwire_folder_title()
    self.expand_tripwire_folder(title_element)

    initial_state = self.get_tripwire_state()
    assert initial_state["hooksAvailable"], "Test hooks (window.__testScene) are not exposed"
    assert initial_state["found"], f"Tripwire '{TRIPWIRE_NAME}' was not found in the scene graph"

    log.info("3. Change tripwire color via the control panel.")
    color_input = self.get_color_input()
    self.set_input_value(color_input, NEW_COLOR_HEX)
    state_after_color = self.get_tripwire_state()
    assert state_after_color["color"] == NEW_COLOR_HEX.lstrip("#"), (
      f"Tripwire color did not update: expected {NEW_COLOR_HEX}, got {state_after_color['color']}"
    )
    log.info("Tripwire color updated correctly.")

    show_checkbox = self.get_show_checkbox()
    was_checked = show_checkbox.is_selected()
    log.info(f"4. Toggle 'show' (currently {was_checked}) and verify the tripwire and its label follow.")
    show_checkbox.click()
    time.sleep(WAIT_SEC)
    state_after_toggle = self.wait_for_label()
    state_after_toggle = self.get_tripwire_state()
    assert state_after_toggle["visible"] is not was_checked, "Tripwire visibility did not flip after toggling 'show'"
    assert state_after_toggle["hasLabel"], "Tripwire label was not found in the scene graph"
    assert state_after_toggle["labelVisible"] is not was_checked, (
      "Tripwire label visibility did not follow the 'show' toggle"
    )

    log.info("5. Toggle 'show' back and verify the tripwire and its label return to the original state.")
    show_checkbox = self.get_show_checkbox()
    show_checkbox.click()
    time.sleep(WAIT_SEC)
    state_restored = self.wait_for_label()
    state_restored = self.get_tripwire_state()
    assert state_restored["visible"] is was_checked, "Tripwire visibility did not revert after re-toggling 'show'"
    assert state_restored["labelVisible"] is was_checked, "Tripwire label visibility did not revert after re-toggling 'show'"
    log.info("Tripwire and label visibility tracked the 'show' toggle correctly.")

    log.info("6. Change tripwire height via the control panel.")
    height_input = self.get_height_input()
    self.set_input_value(height_input, NEW_HEIGHT)
    state_after_height = self.get_tripwire_state()
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
    test.check_tripwire_controls(result_recorder)
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()
