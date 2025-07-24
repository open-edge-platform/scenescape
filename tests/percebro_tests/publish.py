#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import json
import time
import paths

percebro = paths.init()
from scene_common.timestamp import get_iso_time
from scene_common.mqtt import PubSub, initializeMqttClient

NUM_MESSAGES = 5
TEST_WAIT_TIME = 3

def on_connect(mqttc, obj, flags, rc):
  mqttc.subscribe(PubSub.formatTopic(PubSub.IMAGE_CAMERA, camera_id="camera1"), 0)

def test_main(videoData):
  #datetime for video data
  ts = get_iso_time(videoData.begin)
  #frame from video data
  frame = videoData.frames[0]

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
    print( "Warning: Could not determine mqtt user/password!" )

  if certs is not None:
    client.tls_set(**certs)
    client.tls_insecure_set(False)

  client.username_pw_set(user, pw)
  client.on_connect = on_connect
  client.connect(mqtt_broker, mqtt_port, 60)
  flag = True
  count = 0
  client.loop_start()

  while flag:
    print("Publishing image and pose in percebro..")
    percebro.publishImages(videoData, client, ts)
    percebro.getPose(frame, videoData.cam, client)
    time.sleep(TEST_WAIT_TIME)
    if count == NUM_MESSAGES:
      flag = False
    count+=1
