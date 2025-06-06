#!/usr/bin/env python3

# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import os
import time
import json

from tests.functional.tc_roi_mqtt import ROIMqtt
from tests.common_test_utils import check_event_contains_data
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time, get_epoch_time
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10406"
TW_NAME = "Automated_Trip_Wire"
FRAME_RATE = 10
MAX_DELAYS = 3
PERSON = "person"
MAX_CONTROLLER_WAIT = 30 # seconds

RIGHT = 1
LEFT = -1
ZERO = 0

message_received = False
rightAcross = 0
leftAcross = 0
tripwirePoints = None

class WillOurShipGo(ROIMqtt):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneUID = self.params['scene_id']

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.client = PubSub(self.params["auth"], None, self.params["rootcert"],
                         self.params["broker_url"], int(self.params["broker_port"]))
    self.client.onConnect = self.on_connect
    self.client.onMessage = self.on_message
    self.client.connect()
    self.client.loopStart()
    return

  def on_connect(self, mqttc, obj, flags, rc):
    """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
    @param    mqttc     The mqtt client object.
    @param    obj       The private user data.
    @param    flags     The response sent by the broker.
    @param    rc        The connection result.
    """
    print("Connected!")
    return

  def on_message(self, mqttc, obj, msg):
    """! Call back function for the MQTT client on receiving messages.
    @param    mqttc     The mqtt client object.
    @param    obj       The private user data.
    @param    msg       The instance of MQTTMessage.
    """
    global message_received
    global rightAcross, leftAcross

    real_msg = str(msg.payload.decode("utf-8"))
    tripwireEvent = json.loads(real_msg)
    check_event_contains_data(tripwireEvent, "tripwire")
    currPoint = tripwireEvent["objects"][0]["translation"]

    direction = self.directionOfPoint(tripwirePoints[0], tripwirePoints[1], currPoint)
    if direction == RIGHT:
      rightAcross = RIGHT
      print("right across {}".format(rightAcross))

    if direction == LEFT:
      leftAcross = LEFT
      print("left across {}".format(leftAcross))
    message_received = True
    return

  def directionOfPoint(self, a, b, point):
    """! Returns the direction (LEFT, RIGHT, ZERO) of a point relative to a line
    from point a to point b using the 2D cross product.
    @param    a            Coordinates of line point a.
    @param    b            Coordinates of line point b.
    @param    point        Coordinates of current point.
    @return   direction    Right, left or zero.
    """
    term_1 = (b[0] - a[0]) * (point[1] - a[1])
    term_2 = (b[1] - a[1]) * (point[0] - a[0])
    crossProduct = term_1 - term_2
    if crossProduct > 0:
      return RIGHT
    elif crossProduct < 0:
      return LEFT
    else:
      return ZERO

  def create_tripwire_by_ratio(self, tripwire_name, scene_id, x_ratio):
    """! This function creates a tripwire by filling in the tripwire
    form and submitting it directly.
    @param    tripwire_name              Name of the created tripwire.
    @param    scene_id                   ID of scene where tripwire is added.
    @param    x_ratio                    Ratio of scene width.
    @return   points                     List of tripwire points.
    """
    demo_scene_width = 900
    demo_scene_height = 643
    demo_scene_scale = 100

    # Create tripwire across the center point (origin is bottom left in meters)
    cx = demo_scene_width / (2 * demo_scene_scale)
    cy = demo_scene_height / (2 * demo_scene_scale)
    dx = cx * x_ratio
    pt1 = (cx - dx, cy)
    pt2 = (cx + dx, cy)
    tripwire_data = {'scene': scene_id, 'name': tripwire_name, 'points': (pt1, pt2)}
    return tripwire_data

  def prepareScene(self):
    """! Prepares scene for the test.
    @return   res                     Response object.
    """
    tripwire_data = self.create_tripwire_by_ratio(TW_NAME, self.sceneUID, 0.8)
    res = self.rest.createTripwire(tripwire_data)
    return res

  def checkForMalfunctions(self):
    """! This function creates a tripwire and sends MQTT messages mocking objects moving across the tripwire.
    The test then verifies the count to reflect the count received from the tripwire event data matches the expected count.
    @param    obj_location            Pytest fixture defining the objects location.
    @param    objData                 Pytest fixture defining object data such as ID, etc.
    @return   None.
    """
    global message_received
    global rightAcross, leftAcross, tripwirePoints
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      res = self.prepareScene()
      assert res["points"]
      self.client.subscribe(PubSub.formatTopic(PubSub.EVENT, event_type="objects",
                                               region_type="tripwire", scene_id=self.sceneUID,
                                               region_id=res['uid']))
      tripwirePoints = res["points"]
      print("tripwire points: ", tripwirePoints)
      objLocation = self.getLocations()
      objData = self.objData()
      objData['objects'][PERSON][0]['bounding_box']['y'] = objLocation[0]
      waitTopic = PubSub.formatTopic(PubSub.DATA_SCENE,
                                   scene_id=self.sceneUID, thing_type=PERSON)
      publishTopic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=objData['id'])

      self.sceneReady(MAX_DELAYS, waitTopic, publishTopic, objData)

      for yLoc in objLocation:
        id = objData["id"]
        objData["timestamp"] = get_iso_time()
        objData["objects"][PERSON][0]["bounding_box"]["y"] = yLoc
        line = json.dumps(objData)
        message_received = False
        self.client.publish(publishTopic, line)
        num_delays = 0
        while num_delays < MAX_DELAYS:
          time.sleep( 1/FRAME_RATE )
          if message_received == True:
            break
          num_delays += 1

      print()
      print("rightAcross: ", rightAcross)
      print("leftAcross: ", leftAcross)
      print()
      if (rightAcross == RIGHT) and (leftAcross == LEFT):
        self.exitCode = 0

    finally:
      self.recordTestResult()
    return

def test_sensor_region_events(request, record_xml_attribute):
  test = WillOurShipGo(TEST_NAME, request, record_xml_attribute)
  test.checkForMalfunctions()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_sensor_region_events(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
