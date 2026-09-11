# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ROI occupancy-count UI test (2D scene view).

Verifies that an ROI's count label renders in the 2D scene view and updates
with detection events. Focuses on UI rendering/DOM concerns; detection
convergence logic is unit-tested separately (tests/sscape_tests/analytics/).
"""

import json
import time

import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  require_password=True, auth=AUTH_CONTROLLER,
)

ROI_NAME = "OccupancyCountROI"
ROI_ORIGIN_X = -50
ROI_ORIGIN_Y = -200
# Bounding box at a known location in camera1's calibrated space
# (confirmed by prior empirical testing to map inside the ROI).
IN_ROI_BOUNDING_BOX = {
  "x": 1, "y": -0.1, "width": 0.24157160068234987, "height": 0.4988978709744182,
}

# Wait budget for convergence (single detection should be faster than
# the old multi-frame staged replay, which took up to 60s).
COUNT_WAIT_SECONDS = 30


def get_region_uid(rest, name):
  """! Look up a region's uid by its display name via REST.
  @param    rest                    Authenticated RESTClient.
  @param    name                    Region display name.
  @return   str                     The region's uid.
  """
  res = rest.getRegions({"name": name})
  assert res["results"], f"getRegions returned no results for {name}"
  return res["results"][0]["uid"]


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


@pytest.mark.test_name("NEX-T29219")
def test_roi_counts_ui(params, result_recorder):
  """! Test that an ROI's live count renders and updates in 2D scene view.

  Verifies:
  - Count element renders with correct per-type amounts for multiple
    detected types (person, vehicle) and multiple objects of one type
  - Count updates to zero for every type when detections exit the ROI
  - No stale DOM element remains after ROI deletion

  Convergence logic is unit-tested separately (tests/sscape_tests/analytics/).

  @param    params                  Dict of test parameters.
  @param    result_recorder         Pytest fixture recording the test result.
  """
  log.info("Executing: test_roi_counts_ui")

  browser = None
  client = None
  try:
    rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest.authenticate(params["user"], params["password"])

    client = PubSub(
      params["auth"], None, params["rootcert"],
      params["broker_url"], params["broker_port"],
    )
    client.connect()
    client.loopStart()

    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.check_db_status(browser)

    log.info(f"Creating ROI {ROI_NAME}")
    assert common.create_roi(browser, ROI_NAME, ROI_ORIGIN_X, ROI_ORIGIN_Y)
    assert common.verify_roi(browser, [ROI_NAME])
    roi_uid = get_region_uid(rest, ROI_NAME)
    count_selector = f"#roi_{roi_uid} #count"

    log.info("Publishing 2 persons and 1 vehicle detection in the ROI")
    persons = [
      {"id": 301, "category": "person", "bounding_box": IN_ROI_BOUNDING_BOX},
      {"id": 302, "category": "person", "bounding_box": IN_ROI_BOUNDING_BOX},
    ]
    vehicles = [{"id": 401, "category": "vehicle", "bounding_box": IN_ROI_BOUNDING_BOX}]

    # Publish periodically until both type/amount pairs appear (convergence).
    text = None
    deadline = time.monotonic() + COUNT_WAIT_SECONDS
    while time.monotonic() < deadline:
      publish_frame(client, "camera1", {"person": persons, "vehicle": vehicles})
      els = browser.find_elements(By.CSS_SELECTOR, count_selector)
      if els:
        text = els[0].text
        if text and "person: 2" in text and "vehicle: 1" in text:
          break
      time.sleep(1 / 10)
    assert text and "person: 2" in text and "vehicle: 1" in text, (
      f"Expected 'person: 2' and 'vehicle: 1', got {text!r}"
    )

    log.info("Publishing empty frames until counts reset to zero")
    reset_seen = False
    deadline = time.monotonic() + COUNT_WAIT_SECONDS
    while time.monotonic() < deadline:
      publish_frame(client, "camera1", {"person": [], "vehicle": []})
      els = browser.find_elements(By.CSS_SELECTOR, count_selector)
      if els:
        text = els[0].text
        if text and "person: 0" in text and "vehicle: 0" in text:
          reset_seen = True
          break
      time.sleep(1 / 10)
    assert reset_seen, f"Counts never reset to zero for all types, got {text!r}"

    log.info(f"Deleting ROI {ROI_NAME}")
    assert common.delete_roi(browser, ROI_NAME)
    assert not common.verify_roi(browser, [ROI_NAME])
    assert len(browser.find_elements(By.CSS_SELECTOR, f"#roi_{roi_uid}")) == 0, (
      "Stale ROI DOM element remained after deletion"
    )

    result_recorder.success()
  finally:
    if client is not None:
      client.loopStop()
    if browser is not None:
      browser.close()

