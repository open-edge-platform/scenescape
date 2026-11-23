#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from http import HTTPStatus

import pytest
from selenium.webdriver.support.ui import WebDriverWait

import tests.ui.common_ui_test_utils as common
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.ui.browser import Browser
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

CAMERA_ID = "camera1"
CATEGORY_A = "category_alpha"
CATEGORY_B = "category_beta"
# Object Library entries are named after the category they represent.
ASSET_COLORS = {CATEGORY_A: "#ff0000", CATEGORY_B: "#0000ff"}
BOUNDING_BOX = {"x": 0.56, "y": 0.0, "width": 0.24, "height": 0.49}
FRAME_RATE = 10
PAGE_WAIT_SEC = 60
STATE_TIMEOUT_SEC = 60
SENTINEL = "__categoryChangeSentinel"

# Lists the tracked-object marks of the 3D scene with the category in their label
# and the asset (name and color) that represents them.
READ_MARKS_SCRIPT = """
  const scene = window.__testScene;
  if (!scene) return null;
  const marks = [];
  scene.traverse((node) => {
    const label = node.children.find((child) => child.name === "css2dLabel");
    const model = node.children.find((child) => child.name === "model");
    if (!label || !model) return;
    let mesh = null;
    model.traverse((child) => { if (!mesh && child.isMesh) mesh = child; });
    const header = label.element.querySelector(".asset-label-id").textContent;
    marks.push({
      category: header.slice(0, header.lastIndexOf(" #")),
      asset: mesh ? mesh.name : null,
      color: mesh ? mesh.material.color.getHexString() : null,
    });
  });
  return marks;
"""


def create_assets(rest):
  """! Creates one Object Library entry per category, replacing leftovers of an aborted run.
  @param    rest                    Authenticated RESTClient.
  @return   list                    UIDs of the created assets.
  """
  existing = {asset["name"]: asset["uid"] for asset in rest.getAssets(None).get("results") or []}
  uids = []
  for category, color in ASSET_COLORS.items():
    if category in existing:
      assert rest.deleteAsset(existing[category]).statusCode == HTTPStatus.OK
    res = rest.createAsset({"name": category, "mark_color": color})
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), \
      f"Failed to create asset '{category}': {res.errors}"
    uids.append(res["uid"])
  return uids


def connect_publisher(params):
  """! Connects an MQTT client that feeds camera detections to the scene controller.
  @param    params                  Dict of test parameters.
  @return   PubSub                  Connected client with its network loop running.
  """
  client = PubSub(params["auth"], None, params["rootcert"], params["broker_url"],
                  port=int(params["broker_port"]))
  client.connect()
  client.loopStart()
  return client


def publish_frame(client, active_category, idle_categories=()):
  """! Publishes one camera frame holding the same object under active_category.
  @param    client                  Connected MQTT client.
  @param    active_category         Category the object is detected as.
  @param    idle_categories         Categories reported empty so their old tracks are retired.
  """
  objects = {category: [] for category in idle_categories}
  objects[active_category] = [
    {"id": 1, "category": active_category, "bounding_box": BOUNDING_BOX}
  ]
  frame = {
    "id": CAMERA_ID,
    "timestamp": get_iso_time(),
    "objects": objects,
    "rate": float(FRAME_RATE),
  }
  client.publish(PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=CAMERA_ID), json.dumps(frame))


def shows_only(category):
  """! Builds a predicate accepting marks that are all drawn with the asset of category.
  @param    category                Category whose Object Library entry is expected.
  @return   callable                Predicate taking the list of marks read from the 3D scene.
  """
  expected = {
    "category": category,
    "asset": category,
    "color": ASSET_COLORS[category].lstrip("#"),
  }
  return lambda marks: bool(marks) and all(mark == expected for mark in marks)


def feed_until(browser, client, active_category, idle_categories, predicate):
  """! Keeps publishing frames until the marks of the 3D scene satisfy predicate.
  @param    browser                 Browser showing the 3D scene.
  @param    client                  Connected MQTT client.
  @param    active_category         Category the object is detected as.
  @param    idle_categories         Categories reported empty in every frame.
  @param    predicate               Callable taking the list of marks.
  @return   list                    The marks that satisfied the predicate.
  """
  deadline = time.monotonic() + STATE_TIMEOUT_SEC
  marks = None
  while time.monotonic() < deadline:
    publish_frame(client, active_category, idle_categories)
    marks = browser.execute_script(READ_MARKS_SCRIPT)
    if predicate(marks or []):
      return marks
    time.sleep(1 / FRAME_RATE)
  raise AssertionError(
    f"3D scene never drew only '{active_category}' marks within {STATE_TIMEOUT_SEC}s; "
    f"last marks: {marks}")


@common.mock_display
@pytest.mark.test_name("NEX-T10528")
def test_object_category_change_ui(demo_scene, params, result_recorder):
  """
  ## Name
  Object category change gets reflected without web page refresh

  ## Objective
  Verify the 3D UI switches the Object Library asset representing a tracked
  object when the object changes category, without a web page refresh. The
  detections are injected over MQTT instead of running a 3D object detection
  model.

  ## Labels
  - UI
  - 3D UI
  - Object Library
  - MQTT

  ## Steps
  1. Create an Object Library entry with its own mark color for each of two object categories.
  2. Open the 3D UI of the scene and keep that page loaded for the rest of the test.
  3. Publish camera detections of one object under the first category.
  4. Assert the 3D UI draws the object with the first category's asset and color.
  5. Keep publishing the same detection under the second category, and the first as empty.
  6. Assert the 3D UI switches the object to the second category's asset and color.
  7. Assert no mark drawn with the first category's asset is left behind.
  8. Assert the page was not reloaded, then delete both Object Library entries.
  """
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), "REST authentication failed"

  asset_uids = []
  browser = None
  client = None
  try:
    log.info("Step 1. Create an Object Library entry for each category")
    asset_uids = create_assets(rest)

    log.info("Step 2. Open the 3D UI of the scene")
    client = connect_publisher(params)
    browser = Browser(webgl=True)
    assert common.check_page_login(browser, params)
    assert common.navigate_directly_to_page(browser, f"/scene/detail/{demo_scene}/")
    WebDriverWait(browser, PAGE_WAIT_SEC).until(
      lambda driver: driver.execute_script("return !!window.__testScene;"),
      "window.__testScene hook is unavailable; start the stack with EXPOSE_TEST_HOOKS",
    )
    browser.execute_script(f"window.{SENTINEL} = true;")

    log.info(f"Steps 3-4. Detect the object as '{CATEGORY_A}'")
    feed_until(browser, client, CATEGORY_A, (), shows_only(CATEGORY_A))

    log.info(f"Steps 5-7. Change the object to '{CATEGORY_B}'")
    marks = feed_until(browser, client, CATEGORY_B, (CATEGORY_A,), shows_only(CATEGORY_B))
    assert not any(mark["asset"] == CATEGORY_A for mark in marks), \
      f"Mark drawn with the '{CATEGORY_A}' asset is still in the scene: {marks}"

    log.info("Step 8. Check the page was never reloaded")
    assert browser.execute_script(f"return window.{SENTINEL} === true;"), \
      "The page was reloaded while the object changed category"
    result_recorder.success()
  finally:
    if browser is not None:
      browser.close()
    if client is not None:
      client.loopStop()
      client.disconnect()
    for uid in asset_uids:
      rest.deleteAsset(uid)
