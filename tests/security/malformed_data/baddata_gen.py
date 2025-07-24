#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import sys, os
from argparse import ArgumentParser
import base64, json, re
import time
from scene_common.timestamp import get_iso_time
from scene_common.mqtt import PubSub, initializeMqttClient

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("broker", nargs="?", default="broker.scenescape.intel.com",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("-i", "--input", action="append",
                      help="Camera device you are using. If using /dev/video0 the"
                      " argument should be -i 0", required=True)
  return parser

def mqttDidConnect(client, userdata, flags, rc):
  cam_mqttTopic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id="camera1")
  print("Subscribing", cam_mqttTopic)
  client.subscribe(cam_mqttTopic)
  print("Connected")
  return

def mqttReceived(client, userdata, message):
  global sendImage, virtual

  msg = str(message.payload.decode("utf-8"))
  print("Rx message {}".format(msg))
  return

def main():
  global vision_models, mac_addr, cams, sendImage, virtual

  args = build_argparser().parse_args()

  # Default location of root certificate
  rootca="/run/secrets/certs/scenescape-ca.pem"

  # Location for generated user/passwd from image
  auth = "/run/secrets/percebro.auth"

  bad_data_input = open(args.input[0], 'r')
  bad_data = bad_data_input.readlines()

  current_line = 0

  client = initializeMqttClient()
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

  client.on_connect = mqttDidConnect
  client.on_message = mqttReceived

  mqtt_broker = args.broker
  mqtt_port = 1883
  if ':' in mqtt_broker:
    mqtt_broker, mqtt_port = mqtt_broker.split(':')
    mqtt_port = int(mqtt_port)

  if certs is not None:
    client.tls_set(**certs)

  client.tls_insecure_set(True)
  client.username_pw_set(user, pw)
  client.connect(mqtt_broker, mqtt_port)
  client.loop_start()

  time.sleep(3)
  print("Sending data")
  for line in bad_data:

    if not line.startswith("#"):
      jdata = json.loads(line.strip())
      camera_id = jdata["id"]
      if jdata['timestamp'] != "-1":
        jdata['timestamp'] = get_iso_time()

      line = json.dumps(jdata)
      print("Sending frame {} id {}".format(current_line, camera_id))
      #print("Data: {}".format( line.strip()))

      client.publish(PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id),
                     line.strip())

      time.sleep(0.33)
      current_line += 1

  bad_data_input.close()

  print("Malformed JSON Generation: finished")
  time.sleep(3)

  sys.exit(0)

  return

if __name__ == '__main__':
  os._exit(main() or 0)
