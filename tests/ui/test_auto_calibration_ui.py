# SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time

import pytest
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import tests.ui.common_ui_test_utils as common
from tests.ui import UserInterfaceTest
from tests.ui.browser import By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_AUTOCALIBRATION
from tests.utils.spec import FuncTestSpec

log = get_logger(__name__)

TEST_NAME = "NEX-T15710"

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_AUTOCALIBRATION,
  require_password=True, auth="",
)

def wait_for_calibration(browser, wait_time):
  """! Waits for the auto calibration to initialize.
  @param    browser                 Object wrapping the Selenium driver.
  @param    wait_time               Int seconds to wait.
  @return   autocal_button          Web Element auto calibration button.
  """
  start = time.time()
  autocal_button = browser.find_element(By.ID, "auto-autocalibration")
  while not autocal_button.is_enabled() and time.time() - start < wait_time:
    time.sleep(1)
    autocal_button = browser.find_element(By.ID, "auto-autocalibration")
  log.info(f"After {int(time.time() - start)} seconds autocal enabled: "
           f"{autocal_button.is_enabled()}")
  return autocal_button

def wait_for_live_frame(browser, wait_time):
  """! Waits until camCanvas has replaced the offline.png placeholder with a live frame.
  @param    browser                 Object wrapping the Selenium driver.
  @param    wait_time               Int seconds to wait.
  @return   BOOL                    True if a live frame is loaded.
  """
  script = (
    "const img = window.camera_calibration?.camCanvas?.image;"
    "return !!img && img.complete && img.naturalWidth > 0"
    " && img.src.startsWith('data:image/');"
  )
  deadline = time.time() + wait_time
  while time.time() < deadline:
    if browser.execute_script(script):
      return True
    time.sleep(1)
  return False

# Timeouts for autocalibration-specific waits.
AUTOCAL_RESULT_TIMEOUT_S = 120
REGISTRATION_TIMEOUT_S = 180
SAVE_TIMEOUT_S = 30
RELOAD_TIMEOUT_S = 30

def wait_for_calibration_points(browser, wait_time, min_points=4):
  """! Polls camCanvas until at least min_points calibration points appear.
  @param    browser     Object wrapping the Selenium driver.
  @param    wait_time   Int seconds to wait.
  @param    min_points  Minimum point count required to return True.
  @return   BOOL        True if enough points appeared within the timeout.
  """
  script = (
    "return Object.keys("
    "window.camera_calibration?.camCanvas?.getCalibrationPoints?.() || {}"
    ").length;"
  )
  deadline = time.time() + wait_time
  count = 0
  while time.time() < deadline:
    try:
      count = browser.execute_script(script) or 0
    except Exception:
      count = 0
    if count >= min_points:
      return True
    time.sleep(1)
  log.warning(f"Only {count} of {min_points} required calibration points appeared")
  return False

class AprilTagCalibrationTest(UserInterfaceTest):
  # The camera calibration page constructs a THREE.WebGLRenderer
  BROWSER_WEBGL = True

  def __init__(self, testName, request):
    super().__init__(testName, request, None)
    self.sceneName = self.params['scene']
    return

  def click_button_by_id(self, button_id):
    """! Finds a button by ID and clicks it.
    @param    button_id    String ID of the button to click.
    @return   None.
    """
    wait = WebDriverWait(self.browser, 10)
    button = wait.until(EC.element_to_be_clickable((By.ID, button_id)))
    button.click()
    return

  def assert_points_within_tolerance(self, actual_points, expected_points, tolerance=0.1):
    """! Validates that calibration points are within tolerance of expected values.
    Order of points is not guaranteed, so points are matched by finding closest pairs.
    @param    actual_points     Dict of actual calibration points.
    @param    expected_points   Dict of expected calibration points.
    @param    tolerance         Float tolerance as percentage (0.1 = 10%).
    @return   None              Raises AssertionError if validation fails.
    """
    # Allow at most one missing point
    missing_count = len(expected_points) - len(actual_points)
    assert missing_count <= 1, \
      f"Too many missing points: expected {len(expected_points)}, got {len(actual_points)}"

    actual_list = list(actual_points.values())
    expected_list = list(expected_points.values())

    # Match each actual point to the closest expected point
    used_expected_indices = set()
    for actual_coords in actual_list:
      # Find the closest expected point that hasn't been used yet
      best_match_idx = None
      best_distance = float('inf')

      for idx, expected_coords in enumerate(expected_list):
        if idx in used_expected_indices:
          continue
        # Calculate Euclidean distance
        distance = ((actual_coords[0] - expected_coords[0])**2 + (actual_coords[1] - expected_coords[1])**2)**0.5
        if distance < best_distance:
          best_distance = distance
          best_match_idx = idx

      assert best_match_idx is not None, "Could not find a match for actual point"
      used_expected_indices.add(best_match_idx)
      expected_coords = expected_list[best_match_idx]

      # Validate each coordinate is within tolerance
      for i in range(2):  # x and y coordinates
        actual = actual_coords[i]
        expected = expected_coords[i]
        coord_tolerance = abs(expected * tolerance)
        assert abs(actual - expected) <= coord_tolerance, \
          f"Point {actual_coords} coordinate[{i}]: {actual} not within {tolerance*100}% of {expected}"

    log.info(f"{len(actual_list)} calibration points validated within {tolerance*100}% tolerance")
    return

  def check_autocalibration(self, cam_url, scene_name, wait_time):
    """! Auto-calibrates a camera, saves the result and verifies the persisted points.
    @param    cam_url                 String cam calibration url.
    @param    scene_name              String scene name.
    @param    wait_time               Int seconds to wait for the live camera frame.
    @return   None.
    """
    log.info(f"{scene_name} auto calibration test case")

    time.sleep(1)
    cam_list_url = "/cam/list/"
    self.navigateDirectlyToPage(cam_list_url)

    self.navigateDirectlyToPage(cam_url)
    log.info(f"Navigated to cam calibration page {cam_url}")

    time.sleep(1)

    autocal_button = wait_for_calibration(self.browser, REGISTRATION_TIMEOUT_S)
    assert autocal_button.is_enabled(), (
      f"Auto-calibrate button not enabled within {REGISTRATION_TIMEOUT_S}s: "
      f"{autocal_button.get_attribute('title')!r}"
    )
    assert wait_for_live_frame(self.browser, wait_time), (
      f"No live camera frame received within {wait_time}s"
    )
    self.click_button_by_id("reset_points")
    time.sleep(1)
    # Snapshot current transforms so we can detect that save actually persisted.
    pre_save_transforms = self.browser.execute_script(
      "return document.getElementById('id_transforms')?.value;"
    )
    save_page_url = self.browser.current_url
    autocal_button.click()
    # Wait for the autocalibration result to populate camCanvas.
    assert wait_for_calibration_points(self.browser, AUTOCAL_RESULT_TIMEOUT_S, min_points=4), (
      f"Auto-calibration produced no points within {AUTOCAL_RESULT_TIMEOUT_S}s"
    )
    self.click_button_by_id("top_save")
    # Save dispatches form submit only after an alert("Camera updated") and an
    # async MQTT round trip. Accept the alert and wait for the navigation.
    assert common.wait_for_save_complete(self.browser, SAVE_TIMEOUT_S, save_page_url), (
      "Save did not complete within timeout (alert or navigation missing)"
    )
    self.navigateDirectlyToPage(cam_url)
    # On reload, wait for the persisted points to be re-rendered to camCanvas.
    assert wait_for_calibration_points(self.browser, RELOAD_TIMEOUT_S, min_points=4), (
      f"Persisted calibration points did not appear on reload within {RELOAD_TIMEOUT_S}s"
    )
    # Sanity check: the persisted transforms differ from the seed value.
    post_save_transforms = self.browser.execute_script(
      "return document.getElementById('id_transforms')?.value;"
    )
    assert post_save_transforms and post_save_transforms != pre_save_transforms, (
      f"Save did not persist: transforms unchanged ({post_save_transforms!r})"
    )
    points = get_calibration_points_from_js(self.browser, "camera")
    log.info(f"Actual points: {points}")

    expected_points = {
        'p0': [42.74131548684735, 663.6953887756321],
        'p1': [244.56545098806737, 615.208280012257],
        'p2': [562.6995395869819, 324.7693256122194],
        'p3': [1061.0969448580838, 653.5331261796596],
        'p4': [197.19155139690756, 202.56618588566755],
        'p5': [997.5488664337493, 238.69529323145943]
    }

    self.assert_points_within_tolerance(points, expected_points, tolerance=0.1)
    return

  def execute_test(self, result_recorder):
    """! Checks that a user can setup a scene with april tags.
    @param    result_recorder         Pytest fixture recording the test result.
    @return   None.
    """
    MAX_WAIT_TIME = 60
    assert self.login()

    assert common.navigate_to_scene(self.browser, "Queuing")
    cam_url = common.camera_calibrate_url(self.browser, "atag-qcam1")
    self.check_autocalibration(cam_url, "Queuing", MAX_WAIT_TIME)

    result_recorder.success()
    return

def get_calibration_points_from_js(browser, canvas_type):
  """! Gets calibration points directly from JavaScript.
  @param    browser                 Object wrapping the Selenium driver.
  @param    canvas_type             String "camera" or "map".
  @return   dict                    Dictionary of calibration points.
  """
  if canvas_type == "camera":
    # Sensor pixels; camCanvas points are in preview-image pixels (offline.png is 640x480).
    script = """
        return window.camera_calibration?.getSensorCalibrationPoints?.() || {};
    """
  else:  # map/viewport
    script = """
        return window.camera_calibration?.viewport?.getCalibrationPoints(true) || {};
    """

  points = browser.execute_script(script)
  log.info(f"Calibration points from {canvas_type}: {points}")
  return points

@pytest.mark.test_name("NEX-T15710")
@common.mock_display
def test_april_tag(scenescape_env, request, result_recorder):
  """! Checks that a user can setup a scene with april tags.
  @param    scenescape_env          Fixture providing the running SceneScape stack.
  @param    request                 Pytest request providing the test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  @return   None.
  """
  log.info(f"Executing: {TEST_NAME}")

  test = AprilTagCalibrationTest(TEST_NAME, request)
  try:
    test.execute_test(result_recorder)
  finally:
    browser = getattr(test, "browser", None)
    if browser is not None:
      browser.quit()
