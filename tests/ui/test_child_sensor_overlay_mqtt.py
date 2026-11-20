# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import uuid

import pytest
from selenium.webdriver.support.ui import WebDriverWait

from scene_common.rest_client import RESTClient
from tests.ui.browser import By, Browser
import tests.ui.common_ui_test_utils as common
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import AUTH_BROWSER, FuncTestSpec

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_BROWSER,
)


@pytest.mark.test_name("NEX-T22000")
def test_child_sensor_overlay_refresh_mqtt(
  params, scene_factory, result_recorder
):
  """Verify child overlay updates and removals reach the open page over MQTT."""
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"])

  scene_suffix = uuid.uuid4().hex[:8]
  parent = scene_factory(
    f"OverlayParent{scene_suffix}",
    map_image="tests/resources/maps/HazardZoneSceneLarge.png",
    scale=100.0,
  )
  child = scene_factory(f"OverlayChild{scene_suffix}")
  link = rest.updateScene(child["uid"], {"parent": parent["uid"]})
  assert link.statusCode == 200, link.errors

  sensor_name = f"ChildSensor{scene_suffix}"
  sensor = rest.createSensor({
    "scene": child["uid"],
    "name": sensor_name,
    "sensor_id": f"cs{scene_suffix}",
    "area": "circle",
    "center": [1.0, 1.0],
    "radius": 0.5,
  })
  assert sensor.statusCode == 201, sensor.errors
  sensor_uid = sensor["uid"]

  browser = None
  try:
    browser = Browser()
    assert common.check_page_login(browser, params)
    scene_url = f"{params['weburl']}/{parent['uid']}/"
    browser.get(scene_url)

    overlay_id = f"child_sensor_{sensor_name}"
    wait = WebDriverWait(browser, 20)
    wait.until(lambda driver: driver.execute_script(
      """const area = document.getElementById(arguments[0])?.querySelector('.area');
      return area?.tagName.toLowerCase() === 'circle';""",
      overlay_id,
    ))

    mqtt_wait = WebDriverWait(browser, 60)
    mqtt_wait.until(
      lambda driver: "connected" in (
        driver.find_element(By.ID, "mqtt_status").get_attribute("class") or ""
      ).split()
    )

    update = rest.updateSensor(sensor_uid, {
      "area": "circle",
      "center": [0.0, 2.0],
      "radius": 0.75,
    })
    assert update.statusCode == 200, update.errors
    wait.until(lambda driver: driver.execute_script(
      """const marker = document.getElementById(arguments[0])?.querySelector('.sensor');
      return marker && Math.abs(Number(marker.getAttribute('cx'))) < 1e-6;""",
      overlay_id,
    ))

    update = rest.updateSensor(sensor_uid, {
      "area": "poly",
      "points": [[0.0, 1.5], [1.0, 1.5], [1.0, 2.5], [0.0, 2.5]],
    })
    assert update.statusCode == 200, update.errors
    wait.until(lambda driver: driver.execute_script(
      """const group = document.getElementById(arguments[0]);
      return group?.querySelector('.area')?.tagName.toLowerCase() === 'polygon'
        && group.querySelector('.sensor') !== null;""",
      overlay_id,
    ))

    update = rest.updateSensor(sensor_uid, {
      "area": "circle",
      "center": [0.0, 2.0],
      "radius": 0.75,
    })
    assert update.statusCode == 200, update.errors
    wait.until(lambda driver: driver.execute_script(
      """const group = document.getElementById(arguments[0]);
      return group?.querySelector('.area')?.tagName.toLowerCase() === 'circle'
        && group.querySelector('.sensor') !== null;""",
      overlay_id,
    ))

    update = rest.updateSensor(sensor_uid, {"area": "scene"})
    assert update.statusCode == 200, update.errors
    wait.until(lambda driver: driver.execute_script(
      """const group = document.getElementById(arguments[0]);
      return group && group.querySelector('.area') === null
        && group.querySelector('.sensor') !== null;""",
      overlay_id,
    ))

    update = rest.updateSensor(sensor_uid, {
      "area": "circle",
      "center": [0.0, 2.0],
      "radius": 0.75,
    })
    assert update.statusCode == 200, update.errors
    wait.until(lambda driver: driver.execute_script(
      """const group = document.getElementById(arguments[0]);
      return group?.querySelector('.area')?.tagName.toLowerCase() === 'circle'
        && group.querySelector('.sensor') !== null;""",
      overlay_id,
    ))

    removed = rest.deleteSensor(sensor_uid)
    assert removed.statusCode == 200, removed.errors
    sensor_uid = None
    wait.until(lambda driver: driver.execute_script(
      "return document.getElementById(arguments[0]) === null;",
      overlay_id,
    ))
    result_recorder.success()
  finally:
    if sensor_uid is not None:
      rest.deleteSensor(sensor_uid)
    if browser is not None:
      browser.close()
