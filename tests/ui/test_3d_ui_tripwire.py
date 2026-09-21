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

  def check_tripwire_controls(self, result_recorder):
    assert self.login()

    log.info("1. Create a tripwire via the 2D scene page so it renders in the 3D control panel.")
    self.create_tripwire()

    log.info("2. Navigate to the Scene detail (3D) page.")
    common.navigate_directly_to_page(self.browser, f"/scene/detail/{common.TEST_SCENE_ID}/")

    title_element = common.get_3d_control_folder_title(self.browser, TRIPWIRE_NAME, PANEL_WAIT_SEC)
    common.expand_3d_control_folder(self.browser, TRIPWIRE_NAME, title_element, PANEL_WAIT_SEC)

    initial_state = common.get_3d_scene_object_state(self.browser, TRIPWIRE_NAME)
    assert initial_state["hooksAvailable"], "Test hooks (window.__testScene) are not exposed"
    assert initial_state["found"], f"Tripwire '{TRIPWIRE_NAME}' was not found in the scene graph"

    log.info("3. Change tripwire color via the control panel.")
    color_input = common.get_3d_control_input(self.browser, TRIPWIRE_NAME, "color", "@type='color'")
    common.set_3d_control_input_value(self.browser, color_input, NEW_COLOR_HEX)
    state_after_color = common.wait_for_3d_scene_object_state(
      self.browser, TRIPWIRE_NAME,
      lambda state: state.get("color") == NEW_COLOR_HEX.lstrip("#")
    )
    assert state_after_color["color"] == NEW_COLOR_HEX.lstrip("#"), (
      f"Tripwire color did not update: expected {NEW_COLOR_HEX}, got {state_after_color['color']}"
    )
    log.info("Tripwire color updated correctly.")

    show_checkbox = common.get_3d_control_input(self.browser, TRIPWIRE_NAME, "show", "@type='checkbox'")
    was_checked = show_checkbox.is_selected()
    log.info(f"4. Toggle 'show' (currently {was_checked}) and verify the tripwire and its label follow.")
    show_checkbox.click()
    state_after_toggle = common.wait_for_3d_scene_object_state(
      self.browser, TRIPWIRE_NAME,
      lambda state: (
        state.get("visible") is not was_checked
        and state.get("hasLabel")
        and state.get("labelVisible") is not was_checked
      )
    )
    assert state_after_toggle["visible"] is not was_checked, "Tripwire visibility did not flip after toggling 'show'"
    assert state_after_toggle["hasLabel"], "Tripwire label was not found in the scene graph"
    assert state_after_toggle["labelVisible"] is not was_checked, (
      "Tripwire label visibility did not follow the 'show' toggle"
    )

    log.info("5. Toggle 'show' back and verify the tripwire and its label return to the original state.")
    show_checkbox = common.wait_for_3d_control_enabled(self.browser, TRIPWIRE_NAME)
    show_checkbox.click()
    state_restored = common.wait_for_3d_scene_object_state(
      self.browser, TRIPWIRE_NAME,
      lambda state: (
        state.get("visible") is was_checked
        and state.get("labelVisible") is was_checked
      )
    )
    assert state_restored["visible"] is was_checked, "Tripwire visibility did not revert after re-toggling 'show'"
    assert state_restored["labelVisible"] is was_checked, "Tripwire label visibility did not revert after re-toggling 'show'"
    common.wait_for_3d_control_enabled(self.browser, TRIPWIRE_NAME)
    log.info("Tripwire and label visibility tracked the 'show' toggle correctly.")

    log.info("6. Change tripwire height via the control panel.")
    height_input = common.get_3d_control_input(self.browser, TRIPWIRE_NAME, "height", "@type='number'")
    common.set_3d_control_input_value(self.browser, height_input, NEW_HEIGHT)
    state_after_height = common.wait_for_3d_scene_object_state(
      self.browser, TRIPWIRE_NAME, lambda state: state.get("height") == NEW_HEIGHT,
    )
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
