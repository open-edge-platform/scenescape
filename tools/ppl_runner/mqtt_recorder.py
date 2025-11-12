#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import os

from argparse import ArgumentParser
from scene_common.mqtt import PubSub

MQTT_DEFAULT_ROOTCA = "/run/secrets/certs/scenescape-ca.pem"
MQTT_DEFAULT_AUTH   = "/run/secrets/controller.auth"


def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("--broker", help="MQTT broker address")
  parser.add_argument("--topic", help="MQTT topic to subscribe to")
  parser.add_argument("--interval", type=int, default=5,
                      help="Number of seconds to wait for messages")
  parser.add_argument("--output",
                      help="Location to save captured mqtt messages")
  return parser

def on_connect(mqttc, obj, flags, rc):
  global topic_name
  print("Connected to MQTT broker")
  mqttc.subscribe(topic_name)
  return

def on_message(mqttc, obj, msg):
  global log_file
  real_msg = str(msg.payload.decode("utf-8"))
  jdata = json.loads( real_msg )
  if log_file is not None:
    json.dump( jdata, log_file )
    log_file.write("\n")
  return

def record_mqtt():
  args = build_argparser().parse_args()
  global topic_name
  topic_name = args.topic
  interval = args.interval
  broker = args.broker
  print(f"Subscribing to topic {topic_name} on broker {broker} for {interval} seconds")

  # TODO: get it from secret
  auth_string = f'admin:admin'
  client = PubSub(auth_string, None, MQTT_DEFAULT_ROOTCA, broker)
  print("Connecting to MQTT broker at ", broker)

  client.onMessage = on_message
  client.onConnect = on_connect
  client.connect()

  global log_file
  if args.output is not None:
    log_file = open( args.output, 'w' )

  client.loopStart()

  time.sleep(interval)
  client.loopStop()

  if log_file is not None:
    log_file.close()

  return 0

if __name__ == '__main__':
  exit(record_mqtt() or 0)
