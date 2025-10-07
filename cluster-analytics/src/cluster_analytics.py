#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse

from cluster_analytics_context import ClusterAnalyticsContext

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--broker", default="broker.scenescape.intel.com",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("--brokerauth", default="/run/secrets/calibration.auth",
                      help="user:password or JSON file for MQTT authentication")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com/api/v1",
                      help="URL of REST API")
  parser.add_argument("--restauth", default=None,
                      help="user:password or JSON file for REST authentication")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert",
                      help="path to client certificate")
  return parser

def main():
  args = build_argparser().parse_args()
  print("Cluster Analytics Container started")
  analytics_context = ClusterAnalyticsContext(args.broker,
                                        args.brokerauth,
                                        args.cert,
                                        args.rootcert,
                                        args.resturl,
                                        args.restauth)
  analytics_context.loopForever()
  return

if __name__ == '__main__':
  exit(main() or 0)
