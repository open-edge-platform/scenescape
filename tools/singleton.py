#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import json
import random
import time
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_iso_time

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                   description='Sample of publishing pseudo-random singleton data to SceneScape.')

  parser.add_argument('-b', '--broker',
                      help='MQTT broker',
                      default='localhost')

  parser.add_argument('--port',
                      type=int,
                      help='MQTT port',
                      default=1883)

  parser.add_argument('-a', '--auth',
                      help='Scenescape Auth file')

  parser.add_argument('-p', '--password',
                      help='MQTT password')

  parser.add_argument('-u', '--username',
                      help='MQTT user name')

  parser.add_argument('-i', '--id',
                      help='Sensor ID (or mqttid)',
                      required=True)

  parser.add_argument('--min',
                      type=int,
                      help='Minimum sensor value',
                      default=0)

  parser.add_argument('--max',
                      type=int,
                      help='Maximum sensor value',
                      default=100)

  parser.add_argument('-t', '--time',
                      type=float,
                      help='Delay time in seconds between messages',
                      default=1.0)

  parser.add_argument('-s', '--subtype',
                      help='Sensor subtype',
                      default='temperature')

  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  return parser.parse_args()

def on_log(client, userdata, level, buf):
  print("Log: ", buf)

  return


def main():
  args = build_argparser()
  auth_str = args.auth
  if auth_str is None:
    auth_str = args.username + ':' + args.password
  client = PubSub(auth_str, None, args.rootcert, args.broker, args.port, 60, insecure=True)
  client.onLog = on_log
  # Connect to the broker
  print("Connecting to broker: " + args.broker)
  client.connect()

  time.sleep(2)

  try:
    while True:
      time.sleep(args.time)

      value = int(args.min + random.random() * (args.max - args.min))
      # Generate the message with a timestamp and the random value
      message_dict = {'timestamp' : get_iso_time(),
                      'subtype'   : args.subtype,
                      'id'        : args.id,
                      'value'     : value }

      # Publish the message to the singleton topic
      topic = PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=args.id)
      result = client.publish(topic, json.dumps(message_dict))
      status = result[0]
      if status != 0:
        print(f"Failed to send message to topic {topic}")

  except KeyboardInterrupt:
    print("\nShutting down random sensor publishing...")

    # Disconnect the MQTT client
    client.disconnect()

  return 0

if __name__ == '__main__':
  exit(main() or 0)
