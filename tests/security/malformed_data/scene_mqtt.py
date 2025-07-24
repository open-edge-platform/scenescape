#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import sys

import json
import time

from scene_common.mqtt import PubSub, initializeMqttClient

TEST_WAIT_TIME = 180
TEST_MIN_DETECTIONS = TEST_WAIT_TIME * 10
objects_detected = 0
connected = False

def test_on_connect(mqttc, obj, flags, rc):
  global connected
  connected = True
  print( "Connected" )
  mqttc.subscribe( PubSub.formatTopic(PubSub.DATA_SCENE, scene_id="3bc091c7-e449-46a0-9540-29c499bca18c",
                                      thing_type="+"), 0 )

def test_on_message(mqttc, obj, msg):
  global objects_detected
  real_msg = str(msg.payload.decode("utf-8"))
  jdata = json.loads( real_msg )
  print( "Msg {} received ID {} Topic {}".format( objects_detected, jdata['id'], msg.topic ) )
  objects_detected += 1

def test_sscape_running():
  result = 1

  # Default location of root certificate
  rootca="/run/secrets/certs/scenescape-ca.pem"

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

  if certs is not None:
    client.tls_set(**certs)
    client.tls_insecure_set(False)

  client.username_pw_set(user, pw)

  client.on_message = test_on_message
  client.on_connect = test_on_connect
  client.connect(mqtt_broker, mqtt_port, 60)

  client.loop_forever()
  return result

exit( test_sscape_running() )
