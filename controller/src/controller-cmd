#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import os

from controller.scene_controller import SceneController

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--rewriteBadTime", action="store_true",
                      help="Rewrite bad time stamps instead of discarding data")
  parser.add_argument("--rewriteAllTime", action="store_true",
                      help="Rewrite all time stamps")
  parser.add_argument("--maxlag", help="Maximum amount of lag in seconds",
                      default=1.0, type=float)

  # FIXME - configure mosquitto to authenticate against REST so that
  # same user/pass can be used for both REST and MQTT
  # https://pypi.org/project/django-mqtt/
  parser.add_argument("--broker", default="broker.scenescape.intel.com:1883",
                      help="hostname or IP of MQTT broker, optional :port")
  parser.add_argument("--brokerauth", default="/run/secrets/controller.auth",
                      help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com/api/v1",
                      help="URL of REST server")
  parser.add_argument("--restauth", required=True,
                      help="user:password or JSON file for REST authentication")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert", help="path to client certificate")

  parser.add_argument("--verbose", action="store_true",
                      help="lots and lots of debug printing")
  parser.add_argument("--ntp", help="NTP server, default is to use mqtt broker")
  script_path = os.path.abspath(__file__)
  parser.add_argument("--tracker_config_file", help="JSON file with tracker configuration for time-based parameters",
            default=os.path.join(os.path.dirname(script_path), "tracker-config.json"))
  parser.add_argument("--schema_file", help="JSON file with metadata schema",
            default=os.path.join(os.path.dirname(script_path), "schema/metadata.schema.json"))
  parser.add_argument("--visibility_topic", help="Which topic to publish visibility on."
                      "Valid options are 'unregulated', 'regulated', or 'none'",
                      default="regulated")
  return parser

def main():
  args = build_argparser().parse_args()
  controller = SceneController(args.rewriteBadTime, args.rewriteAllTime,
                              args.maxlag, args.broker,
                              args.brokerauth, args.resturl,
                              args.restauth, args.cert,
                              args.rootcert, args.ntp, args.tracker_config_file, args.schema_file,
                              args.visibility_topic)
  controller.loopForever()

  return

if __name__ == '__main__':
  exit(main() or 0)
