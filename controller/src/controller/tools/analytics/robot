#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import json
import traceback

from scene_common import log
from scene_common.mqtt import PubSub

my_parser = argparse.ArgumentParser()
my_parser.add_argument('-b', '--broker',
                       action='store',
                       help='MQTT broker',
                       default='localhost')

my_parser.add_argument('--port',
                       type=int,
                       help='MQTT port',
                       default=1883)

my_parser.add_argument('-r', '--region',
                       action='store',
                       help='Region of Interest (RoI) name',
                       default='Hazard')

my_parser.add_argument('-s', '--scene',
                       action='store',
                       help='Scene name',
                       default='Demo')

my_parser.add_argument('-a', '--auth',
                       help='Scenescape Auth file')

my_parser.add_argument('-p', '--password',
                       help='MQTT password')

my_parser.add_argument('-u', '--username',
                       help='MQTT user name')

my_parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                       help="path to ca certificate")

# Global flag for scene occupancy to stop the robot if nobody is around
occupied = False

def on_connect(mqttc, obj, flags, rc):
  log("rc: " + str(rc))
  return

def on_message(mqttc, obj, msg):
  global occupied
  global client

  try:
    #log(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

    # Start the robot when people are in the scene
    # SceneScape issue: scene enumeration rather than name is used in the topic
    topic_info = client.parseTopic(msg.topic)
    if 'data/scene' in msg.topic \
        and topic_info['scene_id'] == args.scene and topic_info['thing_type'] == 'person':
      message = json.loads(msg.payload)
      scene_count = len(message["objects"])

      if scene_count > 0 and not occupied:
        occupied = True
        log("Starting the robot because someone is in the scene.")
        client.publish("meca500/control", "start")
      else:
        if scene_count == 0 and occupied:
          occupied = False
          log("Stopping the robot because nobody is in the scene.")
          client.publish("meca500/control", "stop")

    # Stop the robot if people are in the scene and anyone is in the target region
    elif 'event/' in msg.topic \
        and topic_info['scene_id'] == args.scene \
        and topic_info['region_id'] == args.region:
      message = json.loads(msg.payload)
      region_count = message["counts"]["person"]

      if occupied:
        if region_count > 0:
          log("Stopping the robot because the region is occupied.")
          client.publish("meca500/control", "stop")
        else:
          log("Starting the robot because nobody is in the region.")
          client.publish("meca500/control", "start")

  except:
    traceback.print_exc()
    exit(1)

def on_publish(mqttc, obj, mid):
  log("mid: " + str(mid))
  return

def on_subscribe(mqttc, obj, mid, granted_qos):
  log("Subscribed: " + str(mid) + " " + str(granted_qos))
  return

def on_log(mqttc, obj, level, string):
  log(string)
  return

args = my_parser.parse_args()

log("Broker: ", args.broker)
log("Scene: ", args.scene)
log("Region: ", args.region)

topic = "scenescape/#"

auth_str = args.auth
if auth_str is None:
  auth_str = args.username + ':' + args.password

client = PubSub(auth_str, None, args.rootcert, args.broker, args.port, 60, userdata=args)
client.onMessage = on_message
client.onLog = on_log
client.onConnect = on_connect
client.onSubscribe = on_subscribe

client.connect()
client.subscribe(topic, 0)

client.loopForever()
