#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import json
import os
import subprocess


def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("topic", help="topic to subscribe to")
  parser.add_argument("broker", nargs="?", default="broker.scenescape.intel.com",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("--rootcert", default="secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert", help="path to client certificate")
  parser.add_argument("--auth", default="secrets/controller.auth",
                      help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--type", default="subscribe",
                      help="type to either subscribe or publish")
  parser.add_argument("--message", default="",
                      help="message to publish")
  return parser

def main():
  args = build_argparser().parse_args()

  if args.auth is not None:
    user = pw = None
    if os.path.exists(args.auth):
      with open(args.auth) as json_file:
        data = json.load(json_file)
      user = data['user']
      pw = data['password']
    else:
      sep = args.auth.find(':')
      if sep < 0:
        raise ValueError("Invalid user/password")
      user = args.auth[:sep]
      pw = args.auth[sep+1:]

  mqtt_broker = args.broker
  mqtt_port = 1883
  if ':' in mqtt_broker:
    mqtt_broker, mqtt_port = mqtt_broker.split(':')
    mqtt_port = int(mqtt_port)

  cmd = ["mosquitto_sub", "-v",
         "--tls-version", "tlsv1.3",
         "--cafile", args.rootcert,
         "-t", args.topic,
         "-u", user, "-P", pw,
         "-h", mqtt_broker, "-p", str(mqtt_port)]

  if args.type == 'publish':
    cmd = ["mosquitto_pub",
       "--tls-version", "tlsv1.3",
       "--cafile", args.rootcert,
       "-t", args.topic,
       "-m", args.message,
       "-u", user, "-P", pw,
       "-h", mqtt_broker, "-p", str(mqtt_port)]

  subprocess.run(cmd)
  return

if __name__ == '__main__':
  exit(main() or 0)
