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
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--cert",
                      help="path to client certificate")
  parser.add_argument("--webui", action="store_true", default=True,
                      help="enable WebUI on port 5000 (default: enabled)")
  parser.add_argument("--no-webui", dest="webui", action="store_false",
                      help="disable WebUI")
  parser.add_argument("--webui-port", type=int, default=5000,
                      help="WebUI port (default: 5000)")
  return parser

def main():
  args = build_argparser().parse_args()
  print("Cluster Analytics Container started")
  analytics_context = ClusterAnalyticsContext(args.broker,
                                        args.brokerauth,
                                        args.cert,
                                        args.rootcert,
                                        enable_webui=args.webui,
                                        webui_port=args.webui_port)
  analytics_context.loopForever()
  return

if __name__ == '__main__':
  exit(main() or 0)
