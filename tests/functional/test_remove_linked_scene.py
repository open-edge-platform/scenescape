#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time

from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from tests.functional import FunctionalTest
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
import tests.common_test_utils as common
from scene_common.timestamp import get_iso_time

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

FRAME_RATE = 10
MAX_WAIT = 10
NUM_PUBLISH_ITERATIONS = 3


class RemoveLinkedScene(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.parent_id = None
    self.child_id = None
    self.child_link_id = None
    self.parent_received = []
    self.child_received = []
    self.connected = False

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def on_connect(self, mqttc, obj, flags, rc):
    """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
    @param    mqttc     The mqtt client object.
    @param    obj       The private user data.
    @param    flags     The response sent by the broker.
    @param    rc        The connection result.
    @return   None
    """
    log.info("Connected!")
    self.connected = True
    topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.parent_id)
    mqttc.subscribe(topic)
    topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=self.child_id)
    mqttc.subscribe(topic)

  def on_message(self, mqttc, obj, msg):
    """! Call back function for the MQTT client on receiving messages.
    @param    mqttc     The mqtt client object.
    @param    obj       The private user data.
    @param    msg       The instance of MQTTMessage.
    @return   None
    """
    topic = PubSub.parseTopic(msg.topic)
    real_msg = str(msg.payload.decode("utf-8"))
    data = json.loads(real_msg)

    log.info(f"Received message on topic: {msg.topic}")

    if topic['scene_id'] == self.parent_id:
      self.parent_received.append(data)
      obj_count = len(data.get('objects', []))
      log.info(f"Parent received data: {obj_count} objects")

    elif topic['scene_id'] == self.child_id:
      self.child_received.append(data)
      obj_count = len(data.get('objects', []))
      log.info(f"Child received data: {obj_count} objects")

  def _setup_scenes(self):
    """! Set up parent scene and link existing Demo scene as child.
    @return   None
    """
    parent_scene = self.rest.createScene({'name': "parent"})
    assert parent_scene.statusCode == 201, \
      f"Expected status code 201, got {parent_scene.statusCode}"
    self.parent_id = parent_scene['uid']
    log.info(f"Parent Scene ID: {self.parent_id}")

    scenes = self.rest.getScenes({'name': 'Demo'})
    assert scenes['count'] > 0, "Demo scene not found"
    child_scene = scenes['results'][0]
    self.child_id = child_scene['uid']
    log.info(f"Child Scene (Demo) ID: {self.child_id}")

    res = self.rest.updateScene(self.child_id, {'parent': self.parent_id})
    assert res.statusCode == 200, \
      f"Expected status code 200, got {res.statusCode}"

    res = self.rest.getChildScene({'parent': self.parent_id})
    assert res.statusCode == 200 and res['count'] >= 1, \
      f"Expected child link after linking, got {res.statusCode} count={res.get('count')}"
    self.child_link_id = res['results'][0]['uid']
    log.info(f"Child link ID: {self.child_link_id}")

  def _publish_data(self, obj_data, obj_category="person"):
    """! Publish simulated object detection data to a camera's MQTT topic.
    @param    obj_data        The object data fixture containing camera id and objects.
    @param    obj_category    The object category to publish (default: "person").
    @return   None
    """
    cam_id = obj_data["id"]
    topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=cam_id)

    for iteration in range(NUM_PUBLISH_ITERATIONS):
      for i in range(5):
        obj_data["timestamp"] = get_iso_time()
        obj_data["objects"][obj_category][0]["bounding_box"]["y"] = 100 + (i * 20)
        obj_data["objects"][obj_category][0]["category"] = obj_category
        line = json.dumps(obj_data)

        self.client.publish(topic, line)
        log.info(
          f"Published object via camera {cam_id}: y={100 + (i * 20)} (iter {iteration})")
        time.sleep(1.0 / FRAME_RATE)

  def _wait_for_messages(self, timeout=MAX_WAIT):
    """! Wait for MQTT messages with objects to arrive on parent and/or child topics.
    Returns early once at least one message has been received, and fails on timeout.
    @param    timeout     Maximum time to wait in seconds.
    @return   None
    """
    start = time.time()
    while time.time() - start < timeout:
      if self.parent_received or self.child_received:
        return
      time.sleep(0.5)
    assert self.parent_received or self.child_received, (
      f"Timed out after {timeout} seconds waiting for MQTT messages "
      "on parent/child scenes"
    )

  def runRemoveLinkedScene(self, objData):
    """! Verify unlinking a child scene from parent stops data forwarding.
    @param    objData   Object data fixture with camera id and detection objects.
    @return   None
    """
    self._setup_scenes()

    self.client = PubSub(self.params["auth"], None, self.params["rootcert"],
                         self.params["broker_url"], int(self.params["broker_port"]))
    self.client.onConnect = self.on_connect
    self.client.onMessage = self.on_message
    self.client.connect()
    self.client.loopStart()

    start = time.time()
    while not self.connected and time.time() - start < MAX_WAIT:
      time.sleep(0.5)
    assert self.connected, "MQTT client failed to connect within timeout"

    log.info("Step 1: Publishing data to child scene while linked to parent")
    self.parent_received.clear()
    self.child_received.clear()
    self._publish_data(objData, obj_category="person")
    self._wait_for_messages()

    assert len(self.child_received) > 0, \
      "Child scene should have received regulated data"
    assert len(self.parent_received) > 0, \
      "Parent scene should have received regulated data"
    log.info(f"Child received {len(self.child_received)} messages")
    log.info(f"Parent received {len(self.parent_received)} messages")
    log.info("PASS: Parent scene received data from linked child scene")

    log.info("Step 2: Unlinking child scene from parent scene")
    res = self.rest.deleteChildSceneLink(self.child_link_id)
    assert res.statusCode == 200, \
      f"Expected status code 200, got {res.statusCode}"

    log.info("Step 3: Publishing data to child scene after unlinking")
    self.parent_received.clear()
    self.child_received.clear()
    self._publish_data(objData, obj_category="person")
    self._wait_for_messages(timeout=5)

    assert len(self.child_received) > 0, \
      "Child scene should still receive its own data"
    assert len(self.parent_received) == 0, \
      "Parent scene should not receive data from unlinked child scene"
    log.info("PASS: Parent scene did not receive data after child was unlinked")

    self.exitCode = 0


def test_remove_linked_scene(request, record_xml_attribute, params, objData, demo_scene):
  """! Test to verify the unlinking of a child scene from parent scene and validating the data flow.
  """
  TEST_NAME = "NEX-T10520"
  record_xml_attribute("name", TEST_NAME)
  test = RemoveLinkedScene(
    "test_remove_linked_scene",
    request,
    record_xml_attribute,
  )
  test.runRemoveLinkedScene(objData)
  common.record_test_result(TEST_NAME, test.exitCode)
