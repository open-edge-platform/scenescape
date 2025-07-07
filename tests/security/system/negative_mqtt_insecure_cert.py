#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os

import json
import time

import tests.common_test_utils as common
from scene_common.mqtt import initializeMqttClient

TEST_WAIT_TIME = 10
TEST_MIN_DETECTIONS = TEST_WAIT_TIME * 20
objects_detected = 0
connected = False

def on_connect(mqttc, obj, flags, rc):
  global connected
  connected = True
  print( "Connected" )
  topic = 'scenescape/#'
  mqttc.subscribe( topic, 0 )

def on_message(mqttc, obj, msg):
  global objects_detected
  if objects_detected == 0:
    real_msg = str(msg.payload.decode("utf-8"))
    print( "First msg received (Topic {})".format( msg.topic ) )

  objects_detected += 1


def test_mqtt_insecure_cert(record_xml_attribute):

  TEST_NAME = "NEX-T10423_MQTT_INSECURE_CERT"
  record_xml_attribute("name", TEST_NAME)

  print("Executing: " + TEST_NAME)

  # Default location of root certificate
  rootca="/workspace/scenescape-ca.pem"

  # Location for generated user/passwd from image
  auth = "/run/secrets/percebro.auth"

  # mqtt broker info:
  mqtt_broker = 'broker.scenescape.intel.com'
  mqtt_port = 1883

  client = initializeMqttClient()

  # The following is from scenescape/mqtt.py

  certs = None
  if os.path.exists(rootca):
    if certs is None:
      certs = {}
    certs['ca_certs'] = rootca

  if os.path.exists(auth):
    with open(auth) as json_file:
      data = json.load(json_file)

    user = data['user']
    pw = data['password']

  else:
    user = 'tmp'
    pw = 'dummy'

  print( "Note: Tester should verify Manually that user '{}' pw '{}' are the right secrets!".format( user, pw ) );

  result = 1
  try:
    if certs is not None:
      client.tls_set(**certs)
    client.tls_insecure_set(True)

    client.username_pw_set(user, pw)

    client.on_message = on_message
    client.on_connect = on_connect
    client.connect(mqtt_broker, mqtt_port, 60)

    client.loop_start()
    time.sleep( TEST_WAIT_TIME )
    client.loop_stop()

    global connected
    global objects_detected

    if connected:
      print( "{} Objects detected in {} seconds".format( objects_detected, TEST_WAIT_TIME ) )

      if objects_detected > TEST_MIN_DETECTIONS:
        print( "Test failed!" )
      else:
        print( "Test passed!" )
    else:
      print( "Test passed! Failed to connect! " )
  except:
    print( "Test passed! Bad certificate, unable to connect! " )
    result = 0

  common.record_test_result(TEST_NAME, result)

  assert result == 0

if __name__ == '__main__':
  exit( test_mqtt_insecure_cert() or 0 )
