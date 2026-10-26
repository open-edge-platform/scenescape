# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser, By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import AUTH_BROWSER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(profile=FULL_STACK, auth=AUTH_BROWSER)

PANEL_WAIT_SEC = 100
SCENE_NAME = common.TEST_SCENE_NAME
MAP_PATH = Path(__file__).resolve().parent / "test_media" / "box.glb"
POSE_AXES = ("posX", "posY", "posZ", "rotX", "rotY", "rotZ")
POSE_TOLERANCE = 0.01
SCENE_FOLDER_XPATH = (
  "//div[@id='panel-3d-controls']//div[@class='title' "
  "and normalize-space()='Scene Settings']/following-sibling::div[@class='children']"
)
SAVE_BUTTON = (
  By.XPATH,
  SCENE_FOLDER_XPATH + "//button[.//div[@class='name' and normalize-space()='save']]",
)


def open_scene_controls(browser: Browser) -> None:
  """Expand Scene Settings and its Pose folder after the GLB finishes loading."""
  WebDriverWait(browser, PANEL_WAIT_SEC).until(
    lambda driver: driver.execute_script(
      "return !!window.__testScene?.getObjectByName('3d_scene');"
    ),
    "GLB mesh or EXPOSE_TEST_HOOKS scene accessor was not available",
  )
  title = common.get_3d_control_folder_title(browser, "Scene Settings", PANEL_WAIT_SEC)
  common.expand_3d_control_folder(browser, "Scene Settings", title, PANEL_WAIT_SEC)
  pose_title = WebDriverWait(browser, PANEL_WAIT_SEC).until(
    EC.element_to_be_clickable((By.ID, f"{SCENE_NAME}-transform"))
  )
  browser.execute_script("arguments[0].click();", pose_title)
  WebDriverWait(browser, PANEL_WAIT_SEC).until(
    EC.visibility_of_element_located((By.ID, f"{SCENE_NAME}-posX"))
  )


def read_scene_pose(browser: Browser) -> dict:
  """Read the scene pose fields in world units and degrees."""
  return {
    axis: float(browser.find_element(By.ID, f"{SCENE_NAME}-{axis}").get_attribute("value"))
    for axis in POSE_AXES
  }


def set_pose_value(browser: Browser, axis: str, value: float) -> None:
  """Commit a numeric pose change through the visible UI field."""
  field = browser.find_element(By.ID, f"{SCENE_NAME}-{axis}")
  field.click()
  field.send_keys(Keys.CONTROL, "a")
  field.send_keys(f"{value:.4f}")
  field.send_keys(Keys.TAB)


def assert_scene_pose(browser: Browser, expected: dict) -> None:
  """Check all pose fields and the live GLB mesh, not just the input values."""
  def mesh_matches(driver):
    pose = driver.execute_script("""
      const mesh = window.__testScene?.getObjectByName('3d_scene');
      if (!mesh) return null;
      return {
        posX: mesh.position.x, posY: mesh.position.y, posZ: mesh.position.z,
        rotX: mesh.rotation.x * 180 / Math.PI,
        rotY: mesh.rotation.y * 180 / Math.PI,
        rotZ: mesh.rotation.z * 180 / Math.PI,
      };
    """)
    return pose and all(
      abs(pose[axis] - expected[axis]) < POSE_TOLERANCE for axis in POSE_AXES
    )

  WebDriverWait(browser, PANEL_WAIT_SEC).until(
    mesh_matches, f"GLB mesh pose did not match {expected}"
  )
  actual = read_scene_pose(browser)
  for axis in POSE_AXES:
    assert abs(actual[axis] - expected[axis]) < POSE_TOLERANCE, (
      f"Scene {axis}: expected {expected[axis]}, got {actual[axis]}"
    )


def select_transform_mode(browser: Browser, mode: str) -> None:
  """Toggle the switch and verify only the corresponding scene gizmo is displayed."""
  toggle = browser.find_element(By.ID, f"{SCENE_NAME}-toggle-rotate-translate")
  rotate = mode == "rotate"
  if toggle.is_selected() != rotate:
    toggle.click()
  assert toggle.is_selected() == rotate, f"Scene switch did not select {mode} mode"

  def gizmo_matches(driver):
    return driver.execute_script("""
      const scene = window.__testScene;
      const control = scene?.getObjectByName(arguments[0] + '-transform-controls');
      if (!control || !control.visible) return false;
      let gizmo;
      control.traverse(node => {
        if (node.gizmo?.rotate && node.gizmo?.translate) gizmo = node;
      });
      if (!gizmo) return false;
      const mode = arguments[1];
      const other = mode === 'rotate' ? 'translate' : 'rotate';
      return gizmo.visible && gizmo.mode === mode &&
        gizmo.gizmo[mode].visible && !gizmo.gizmo[other].visible &&
        gizmo.gizmo[mode].children.some(handle => handle.visible);
    """, SCENE_NAME, mode)

  WebDriverWait(browser, PANEL_WAIT_SEC).until(
    gizmo_matches, f"Scene {mode} gizmo was not displayed exclusively"
  )


@common.mock_display
@pytest.mark.test_name("NEX-T10498")
def test_3d_ui_glb_scene_position_management(params, result_recorder):
  """Verify GLB scene rotation, translation, gizmo modes, and saved pose persistence."""
  browser = None

  try:
    log.info("Executing: NEX-T10498")
    assert MAP_PATH.is_file(), f"GLB test map not found: {MAP_PATH}"
    browser = Browser(headless=False, webgl=True)
    assert common.check_page_login(browser, params)

    log.info("1. Upload a GLB map through the Update Scene page.")
    update_url = f"/scene/update/{common.TEST_SCENE_ID}/"
    assert common.navigate_directly_to_page(browser, update_url)
    map_input = WebDriverWait(browser, PANEL_WAIT_SEC).until(
      EC.presence_of_element_located((By.ID, "id_map"))
    )
    map_input.send_keys(str(MAP_PATH))
    browser.find_element(By.ID, "save").click()
    WebDriverWait(browser, PANEL_WAIT_SEC).until(EC.staleness_of(map_input))
    assert common.navigate_directly_to_page(browser, update_url)
    map_link = WebDriverWait(browser, PANEL_WAIT_SEC).until(
      EC.presence_of_element_located((By.CSS_SELECTOR, "#map_wrapper a"))
    )
    assert map_link.get_attribute("href").lower().endswith(".glb"), (
      "Saved scene map is not a GLB file"
    )

    log.info("2. Open the 3D UI and expand Scene Settings and Pose.")
    assert common.navigate_directly_to_page(
      browser, f"/scene/detail/{common.TEST_SCENE_ID}/"
    )
    open_scene_controls(browser)
    initial_pose = read_scene_pose(browser)
    assert_scene_pose(browser, initial_pose)

    log.info("3. Toggle translation and rotation, checking the corresponding gizmos.")
    select_transform_mode(browser, "translate")
    select_transform_mode(browser, "rotate")
    assert_scene_pose(browser, initial_pose)

    log.info("4. Rotate the mesh on all axes and verify translation remains unchanged.")
    expected_pose = initial_pose.copy()
    for axis, delta in (("rotX", 10.0), ("rotY", -15.0), ("rotZ", 20.0)):
      expected_pose[axis] += delta
      set_pose_value(browser, axis, expected_pose[axis])
      assert_scene_pose(browser, expected_pose)

    log.info("5. Translate the mesh on all axes and verify rotation remains unchanged.")
    select_transform_mode(browser, "translate")
    for axis, delta in (("posX", 0.5), ("posY", -0.25), ("posZ", 0.75)):
      expected_pose[axis] += delta
      set_pose_value(browser, axis, expected_pose[axis])
      assert_scene_pose(browser, expected_pose)

    log.info("6. Save the scene mesh pose.")
    assert common.click_when_clickable(
      browser, SAVE_BUTTON, timeout_s=PANEL_WAIT_SEC
    ), "Scene save button did not become clickable"
    WebDriverWait(browser, PANEL_WAIT_SEC).until(
      EC.text_to_be_present_in_element(
        (By.CSS_SELECTOR, "#toast-area .alert-success"),
        "Scene mesh settings have been updated!",
      )
    )

    log.info("7. Reload and verify all saved pose fields and the live mesh pose.")
    browser.refresh()
    open_scene_controls(browser)
    assert_scene_pose(browser, expected_pose)
    result_recorder.success()

  finally:
    if browser is not None:
      browser.quit()
