#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import os

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

  # WebUI is disabled by default, can be enabled via flag
  parser.add_argument("--webui", action="store_true", default=False,
                      help="enable WebUI on port 5000 (default: disabled, can be enabled via flag)")
  parser.add_argument("--no-webui", dest="webui", action="store_false",
                      help="disable WebUI")
  parser.add_argument("--webui-port", type=int, default=5000,
                      help="WebUI port (default: 5000)")
  parser.add_argument("--webui-certfile",
                      help="path to SSL certificate file for HTTPS WebUI (required when WebUI is enabled)")
  parser.add_argument("--webui-keyfile",
                      help="path to SSL private key file for HTTPS WebUI (required when WebUI is enabled)")
  return parser

def main():
  args = build_argparser().parse_args()

  # Validate WebUI certificate requirements
  if args.webui:
    if not args.webui_certfile or not args.webui_keyfile:
      print("ERROR: WebUI is enabled but SSL certificate files are missing.")
      print("Please provide both --webui-certfile and --webui-keyfile arguments,")
      print("or disable WebUI with --no-webui")
      exit(1)

  print("Cluster Analytics Container started")
  if args.webui:
    print(f"WebUI will be available at https://0.0.0.0:{args.webui_port}")
  else:
    print("WebUI is disabled")

  analytics_context = ClusterAnalyticsContext(args.broker,
                                        args.brokerauth,
                                        args.cert,
                                        args.rootcert,
                                        enable_webui=args.webui,
                                        webui_port=args.webui_port,
                                        webui_certfile=args.webui_certfile,
                                        webui_keyfile=args.webui_keyfile)
  analytics_context.loopForever()
  return

if __name__ == '__main__':
  exit(main() or 0)
