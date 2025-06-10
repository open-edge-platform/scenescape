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

import cv2
import json
import time
import base64
import numpy as np
from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from threading import Condition

from scene_common.timestamp import get_epoch_time
from scene_common.mqtt import PubSub
from selenium.common.exceptions import StaleElementReferenceException

TEST_WAIT_TIME = 10
UI_MARKS_DELAY = 3
MAX_TEST_TIME = 60
MAX_IMAGES = 10

image_history = {}
last_image = {}
connected = False
counter_img = {}
timestamp_img = []
cameras = ["camera1", "atag-qcam1"]

def on_connect(mqttc, data, flags, rc):
  """! Call back function for MQTT client on establishing a connection, which subscribes to the topic.
  @param    mqttc     The mqtt client object.
  @param    obj       The private user data.
  @param    flags     The response sent by the broker.
  @param    rc        The connection result.
  """
  global connected
  connected = True
  print( "Connected to MQTT Broker" )
  for cam in cameras:
    topic = PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id=cam)
    mqttc.subscribe( topic, 0 )
    print( "Subscribed to the topic {}".format(topic))
    mqttc.publish(PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=cam), "getimage")
  return

def on_image_message(mqttc, condlock, msg):
  """! Call back function for the MQTT client on receiving messages. If the message is an image
  adds it to an array and increments the image counter.
  @param    mqttc     The mqtt client object.
  @param    condlock  threading.Condition for signaling data was received
  @param    msg       The instance of MQTTMessage.
  """
  global counter_img
  global last_image
  topic = PubSub.parseTopic(msg.topic)
  camera_id = topic['camera_id']

  real_msg = str(msg.payload.decode("utf-8"))
  json_data = json.loads(real_msg)
  if 'image' in json_data:
    # Ignore images we already looked at, by timestamp.
    if json_data['timestamp'] not in timestamp_img:
      img = json_data['image']
      im_bytes = base64.b64decode(img)
      img_as_np = np.frombuffer(im_bytes, dtype=np.uint8)
      last_image[camera_id] = cv2.imdecode(img_as_np, flags=cv2.IMREAD_COLOR)

    if counter_img[camera_id] < MAX_IMAGES:
      # Ignore images we already looked at, by timestamp.
      if json_data['timestamp'] not in timestamp_img:
        img = json_data['image']
        im_bytes = base64.b64decode(img)
        im_arr = np.frombuffer(im_bytes, dtype=np.uint8)

        image_history[camera_id].append(cv2.imdecode(im_arr, flags=cv2.IMREAD_COLOR))
        counter_img[camera_id] += 1
        condlock.acquire()
        condlock.notify()
        condlock.release()

  mqttc.publish(PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera_id), "getimage")
  return

def get_person_marks(browser):
  """! Gets the marks available on the UI.
  @param   browser     Object wrapping the Selenium driver.
  @return  BOOL        Boolean representing a successful reset.
  """
  marks_class = 'mark'
  marks_found = []
  assert common.wait_for_elements(browser, marks_class, findBy=By.CLASS_NAME, maxWait=20)
  get_marks = browser.find_elements(By.CLASS_NAME, marks_class)
  for marks in get_marks:
    marks_found.append(marks.get_attribute('transform'))
  return marks_found

def check_person_marks(browser, camera_id):
  """! Checks that the number of person marks in a scene before a delay and after differ.
  @param   browser    Object wrapping the Selenium driver.
  @return  BOOL       Boolean representing a successful reset.
  """
  global UI_MARKS_DELAY
  video_frame = common.wait_for_elements(browser, camera_id, findBy=By.CSS_SELECTOR)

  marks_before = marks_after = []
  attempt = 0

  while attempt < 5:
    try:
      marks_before = get_person_marks(browser)
      # Wait for marks to move around
      time.sleep(UI_MARKS_DELAY)
      marks_after = get_person_marks(browser)
      if marks_before == marks_after:
        print("The marks are identical, re-trying")
        marks_before = marks_after = []
      else:
        break
    except StaleElementReferenceException:
      print("Failed getting marks, re-trying")
      marks_before = marks_after = []
    attempt += 1

  assert len(marks_before) and len(marks_after)
  if marks_before != marks_after and video_frame is True:
    print( "The dots ARE updating on the scene" )
    return True
  else:
    print( "The dots ARE NOT updating on the scene !" )
    print( "co-ordinates before ", marks_before )
    print( "co-ordinates after ", marks_after )
  return False

def test_out_of_box(params, record_xml_attribute):
  """! Checks that the person marks in the scene and the image stream for
  camera 1 are both changing in time.
  @param    params                  Dict of test parameters.
  @param    record_xml_attribute    Pytest fixture recording the test name.
  @return   exit_code               Indicates test success or failure.
  """
  TEST_NAME = "NEX-T10417"
  record_xml_attribute("name", TEST_NAME)
  print( "Executing: " + TEST_NAME )
  print( "Test that the out-of-box Demo scene is operating at first build")

  exit_code = 1
  frames_updating = False
  message_received = Condition()

  try:
    client = PubSub(params['auth'], None, params['rootcert'], params['broker_url'],
                    userdata=message_received)

    global counter_img
    global last_image
    global image_history
    global cameras

    client.onConnect=on_connect
    for cam in cameras:
      image_history[cam] = []
      counter_img[cam] = 0
      client.addCallback(PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id=cam), on_image_message)
    client.connect()

    # collects images
    testStart = get_epoch_time()
    message_received.acquire()
    client.loopStart()

    for cam in cameras:
      while(counter_img[cam] < MAX_IMAGES):
        message_received.wait(timeout=TEST_WAIT_TIME)
        print( "{} images obtained".format(counter_img[cam]) )
        testTime = get_epoch_time()
        if testTime - testStart > MAX_TEST_TIME:
          print( "Test seems stuck, aborting" )
          break
    message_received.release()
    client.loopStop()

    # checks that at least one of the collected images differs from the current image.
    for cam in cameras:
      assert len(image_history[cam]) > 1
      for image in image_history[cam]:
        if common.mse(last_image[cam], image) > 0.0:
          frames_updating = True
      assert frames_updating

    # Images are being updated from percebro, verify the scene controller + UI are working too:
    browser = Browser()
    assert common.check_page_login(browser, params)
    assert common.navigate_to_scene(browser, "Retail")
    assert check_person_marks(browser, '#camera1')

    assert common.navigate_to_scene(browser, "Queuing")
    assert check_person_marks(browser, '#atag-qcam1')

    print( "Camera images ARE updating on the scene" )
    exit_code = 0

  finally:
    common.record_test_result(TEST_NAME, exit_code)

  assert exit_code == 0
  return exit_code
