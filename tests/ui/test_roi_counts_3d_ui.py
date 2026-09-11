# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ROI occupancy-count UI test (3D scene view).

Verifies that an ROI renders in the 3D scene view and that its count label
shows the correct per-type amounts and resets when the ROI is vacated.

Assertions read the live Three.js scene graph through a test-only hook
(window.__testScene), which the server renders only when the stack is
started with EXPOSE_TEST_HOOKS (test/CI only, never production). This is
deterministic where pixel/canvas checks cannot distinguish "correct
per-type counts" from "some text happens to be there".
"""

import json
import time

import pytest

from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time
import tests.ui.common_ui_test_utils as common
from tests.ui.browser import Browser, By
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth=AUTH_CONTROLLER,
)

ROI_NAME = "OccupancyCount3DROI"
ROI_ORIGIN_X = -50
ROI_ORIGIN_Y = -200

# Bounding box at a known location in camera1's calibrated space
# (confirmed by prior empirical testing to map inside the ROI).
IN_ROI_BOUNDING_BOX = {
  "x": 1, "y": -0.1, "width": 0.24157160068234987, "height": 0.4988978709744182,
}
VACANT_OBJECTS = {"person": [], "vehicle": []}

# The 3D view needs ~20s to finish its MQTT handshake, and region events are
# only emitted when occupancy changes, so the budget must cover several
# occupancy cycles after the browser starts listening.
COUNT_WAIT_SECONDS = 75
VACATE_CYCLE_FRAMES = 80
VACATE_FRAMES = 40

# Reads the ROI and its count label from the live Three.js scene graph. The
# label is a child mesh named "countTextObject" of the region node, which is
# named after the ROI (see sceneregion.js updateCounts()).
GET_REGION_STATE_SCRIPT = """
const testScene = window.__testScene;
if (!testScene) return {hooksAvailable: false};
const region = testScene.getObjectByName(arguments[0]);
if (!region) return {hooksAvailable: true, found: false};
const label = region.getObjectByName("countTextObject");
return {
  hooksAvailable: true,
  found: true,
  hasPoints: Array.isArray(region.points) && region.points.length > 0,
  pointsCount: region.points ? region.points.length : null,
  height: region.height,
  hasCountLabel: !!label,
  countText: label ? label.userData.text : null,
};
"""


def get_region_state(browser, roi_name):
  """! Read the ROI's scene-graph state via the window.__testScene hook.
  @param    browser                 Object wrapping the Selenium driver.
  @param    roi_name                Display name of the ROI/region.
  @return   dict                    hooksAvailable/found/countText, per availability.
  """
  return browser.execute_script(GET_REGION_STATE_SCRIPT, roi_name)


def wait_for_region_rendered(browser, roi_name, timeout=30.0, poll_interval=0.5):
  """! Poll until the ROI node appears in the 3D scene graph.
  @param    browser                 Object wrapping the Selenium driver.
  @param    roi_name                Display name of the ROI/region.
  @param    timeout                 Maximum seconds to poll.
  @param    poll_interval           Seconds between polls.
  @return   dict                    The last observed state.
  """
  deadline = time.monotonic() + timeout
  state = None
  while time.monotonic() < deadline:
    state = get_region_state(browser, roi_name)
    if state.get("found"):
      return state
    time.sleep(poll_interval)
  return state


def publish_frame(client, camera_id, objects):
  """! Publish one detection frame on the DATA_CAMERA topic.
  @param    client                  Connected PubSub client.
  @param    camera_id               Camera id the frame is attributed to.
  @param    objects                 The "objects" payload dict to publish.
  """
  frame = {
    "timestamp": get_iso_time(),
    "id": camera_id,
    "objects": objects,
    "rate": 9.8,
  }
  client.publish(
    PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
    json.dumps(frame),
  )


def wait_for_count_text(client, browser, roi_name, objects, predicate,
                        timeout=COUNT_WAIT_SECONDS, poll_interval=0.1,
                        vacate=False):
  """! Publish detection frames until the ROI's count label satisfies
  predicate(text) or the timeout elapses, returning the last observed text.

  Region events are published only when occupancy changes, so a steady
  population emits one burst and then nothing. The 3D view completes its
  MQTT handshake around twenty seconds after page load and would miss that
  burst, so the ROI is repeatedly vacated and repopulated to keep emitting
  fresh events until the view is listening.

  @param    client                  Connected PubSub client.
  @param    browser                 Object wrapping the Selenium driver.
  @param    roi_name                Display name of the ROI/region.
  @param    objects                 The "objects" payload dict to keep publishing.
  @param    predicate               Callable taking the label text, returning bool.
  @param    timeout                 Maximum seconds to poll.
  @param    poll_interval           Seconds between polls.
  @param    vacate                  Periodically empty the ROI to force events.
  @return   str                     The last observed count label text.
  """
  deadline = time.monotonic() + timeout
  text = None
  frame = 0
  while time.monotonic() < deadline:
    vacating = vacate and frame % VACATE_CYCLE_FRAMES < VACATE_FRAMES
    publish_frame(client, "camera1", VACANT_OBJECTS if vacating else objects)
    text = get_region_state(browser, roi_name).get("countText")
    if text and predicate(text):
      return text
    frame += 1
    time.sleep(poll_interval)
  return text


@common.mock_display
@pytest.mark.test_name("NEX-T29220")
def test_roi_counts_3d_ui(params, result_recorder):
  """! Test that an ROI's live count renders and updates in the 3D scene view.

  Verifies:
  - The ROI renders as a scene-graph node with valid geometry
  - Its count label shows correct per-type amounts for multiple detected
    types (person, vehicle) and multiple objects of one type
  - The count resets to zero for every type when detections exit the ROI

  Convergence logic is unit-tested separately (tests/sscape_tests/analytics/).

  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  log.info("Executing: test_roi_counts_3d_ui")

  browser = None
  client = None
  try:
    client = PubSub(
      params["auth"], None, params["rootcert"],
      params["broker_url"], params["broker_port"],
    )
    client.connect()
    client.loopStart()

    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    log.info(f"Creating ROI {ROI_NAME}")
    assert common.create_roi(browser, ROI_NAME, ROI_ORIGIN_X, ROI_ORIGIN_Y)
    assert common.verify_roi(browser, [ROI_NAME])

    log.info("Switching to the 3D scene view")
    assert common.navigate_directly_to_page(
      browser, f"/scene/detail/{common.TEST_SCENE_ID}/"
    )
    assert common.wait_for_3d_scene_rendered(browser, timeout=60.0), \
      "3D scene did not render in time"

    # Confirm the ROI's async REST-backed thing object has finished loading.
    common.selenium_wait_for_elements(
      browser,
      (By.XPATH, "//div[@class='title' and normalize-space(text())='" + ROI_NAME + "']"),
      timeout=30,
    )

    state = wait_for_region_rendered(browser, ROI_NAME)
    assert state.get("hooksAvailable"), (
      "window.__testScene test hook is unavailable; ensure the stack was "
      "started with EXPOSE_TEST_HOOKS enabled"
    )
    assert state.get("found"), f"ROI '{ROI_NAME}' not found in the 3D scene graph"
    assert state.get("hasPoints"), "ROI node has no geometry (points list is empty)"
    assert state.get("height") is not None, "ROI node height not set"

    log.info("Publishing 2 persons and 1 vehicle detection in the ROI")
    persons = [
      {"id": 301, "category": "person", "bounding_box": IN_ROI_BOUNDING_BOX},
      {"id": 302, "category": "person", "bounding_box": IN_ROI_BOUNDING_BOX},
    ]
    vehicles = [{"id": 401, "category": "vehicle", "bounding_box": IN_ROI_BOUNDING_BOX}]

    text = wait_for_count_text(
      client, browser, ROI_NAME, {"person": persons, "vehicle": vehicles},
      lambda t: "person: 2" in t and "vehicle: 1" in t, vacate=True,
    )
    assert text and "person: 2" in text and "vehicle: 1" in text, (
      f"Expected 'person: 2' and 'vehicle: 1', got {text!r}"
    )

    log.info("Publishing empty frames until counts reset to zero")
    text = wait_for_count_text(
      client, browser, ROI_NAME, VACANT_OBJECTS,
      lambda t: "person: 0" in t and "vehicle: 0" in t,
    )
    assert text and "person: 0" in text and "vehicle: 0" in text, (
      f"Counts never reset to zero for all types, got {text!r}"
    )

    result_recorder.success()
  finally:
    if client is not None:
      client.loopStop()
    if browser is not None:
      browser.close()
