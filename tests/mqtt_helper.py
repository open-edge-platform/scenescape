# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time

from scene_common.mqtt import PubSub

TEST_MQTT_DEFAULT_ROOTCA = "/run/secrets/certs/scenescape-ca.pem"
TEST_MQTT_DEFAULT_AUTH   = "/run/secrets/controller.auth"


waitConnected = False
objectDetectionMessages = 0
sceneUpdateMessages = 0

def wait_on_connect(mqttc, obj, flags, rc):
  """! This is callback function  for on_connect
  @params mqttc - the client instance for this callback
  @params obj - the private user data as set in Client() or user_data_set()
  @params flags - response flags sent by the broker
  @params rc - the connection status
  """
  global waitConnected

  waitConnected = True
  #print( "Connected to MQTT Broker" )
  mqttc.subscribe( PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id="+"), 0 )
  mqttc.subscribe( PubSub.formatTopic(PubSub.DATA_SCENE, scene_id="+",
                                      thing_type="+"), 0 )
  #print("Subscribed to the topic {}".format( topic ))
  return

def wait_on_message(mqttc, obj, msg):
  """! This is callback function  to receive messages from the mqtt broker
  @params mqttc - the client instance for this callback
  @params obj - the private user data as set in Client() or user_data_set()
  @params msg is the payload
  """
  global objectDetectionMessages, sceneUpdateMessages

  realMsg = str(msg.payload.decode("utf-8"))
  metadata = json.loads(realMsg)

  topic = PubSub.parseTopic(msg.topic)
  if topic['_topic_id'] == PubSub.DATA_CAMERA:
    if len(list(metadata["objects"].values())[0]):
      objectDetectionMessages += 1
  elif topic['_topic_id'] == PubSub.DATA_SCENE:
    sceneUpdateMessages += 1
  return

def mqtt_wait_for_detections( broker, port, rootca, auth,
                              waitOnVideoAnalytics, waitOnScene,
                              maxWait=120, waitStep=2, minMessages=10):
  """! This function waits for object detection mqtt messages to be available
  on the broker, so tests can start after they are available.
  @params broker   - The address for the broker.
  @params port     - Port at which the broker should be found
  @params rootca   - Root certificate to use. Optional.
  @params auth     - Authentication secret file to use. Optional.
  @params maxWait  - Maximum time to wait for detection messages. Optional.
  @params waitStep - Interval to wait for messages. Optional.
  @params minMessages - Number of detection messages to wait for. Optional.
  @returns True if at least minMessages were detected. False otherwise.
  """

  global objectDetectionMessages
  global waitConnected
  global sceneObjectUpdates, sceneValidObjects

  waitClient = PubSub(auth, None, rootca, broker, port)

  result = False

  waitClient.onMessage = wait_on_message
  waitClient.onConnect = wait_on_connect
  waitClient.connect()

  currentWait = 0
  waitDone = False

  waitClient.loopStart()
  while waitDone == False:

    time.sleep( waitStep )
    if waitConnected:
      waitDone = True
      result = True
      if waitOnVideoAnalytics and objectDetectionMessages < minMessages:
        waitDone = False
        result = False
      if waitOnScene and sceneUpdateMessages < minMessages:
        waitDone = False
        result = False
    if waitDone == False:
      currentWait += waitStep

      if currentWait >= maxWait:
        print( "Error: Did not find object detection messages coming in!" )
        waitDone = True

  waitClient.loopStop()
  print("mqtt_wait_for_detections: {},{} detections found".format(
    objectDetectionMessages, sceneUpdateMessages))

  return result
