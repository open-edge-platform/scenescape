#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PTZ Pose Service — CLI entrypoint.

Keeps the Scenescape pose of one or more ONVIF PTZ cameras in sync with
their live pan/tilt position. See README.md for the config file schema and
environment variables.
"""

import argparse
import os

from scene_common import log

from ptz_pose_context import PTZPoseContext


def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("--resturl", default="https://web.scenescape.intel.com:443/api/v1",
                      help="Scenescape REST API base URL")
  parser.add_argument("--restauth", default="/run/secrets/calibration.auth",
                      help="user:password or path to JSON file for REST authentication")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to CA certificate for REST TLS verification")

  parser.add_argument("--config", default="/app/config/cameras.json",
                      help="path to the camera map JSON file")

  parser.add_argument("--onvif-username", default=os.environ.get("ONVIF_USERNAME", ""),
                      help="username for ONVIF camera authentication "
                           "(default: ONVIF_USERNAME env var)")
  parser.add_argument("--onvif-password", default=os.environ.get("ONVIF_PASSWORD", ""),
                      help="password for ONVIF camera authentication "
                           "(default: ONVIF_PASSWORD env var)")

  parser.add_argument("--poll-hz", type=float, default=5.0,
                      help="how many times per second to poll each camera's PTZ status")
  parser.add_argument("--min-delta-deg", type=float, default=0.2,
                      help="minimum rotation change (degrees) before pushing a pose update")

  parser.add_argument("--pan-scale", type=float, default=1.0,
                      help="default degrees of yaw per unit of ONVIF pan delta "
                           "(overridable per camera in the config file)")
  parser.add_argument("--tilt-scale", type=float, default=1.0,
                      help="default degrees of pitch per unit of ONVIF tilt delta "
                           "(overridable per camera in the config file)")
  parser.add_argument("--invert-pan", action="store_true", default=False,
                      help="flip the sign of the pan contribution")
  parser.add_argument("--invert-tilt", action="store_true", default=False,
                      help="flip the sign of the tilt contribution")

  parser.add_argument("--discover-only", action="store_true", default=False,
                      help="discover ONVIF/PTZ cameras on the network, log them, and exit "
                           "(use this to populate the config file, no REST connection needed)")
  return parser


def main():
  args = build_argparser().parse_args()

  if args.discover_only:
    PTZPoseContext.logDiscoveredCameras(args.onvif_username, args.onvif_password)
    return 0

  log.info("PTZ Pose Service started")
  ctx = PTZPoseContext(
      args.resturl, args.restauth, args.rootcert, args.config,
      onvif_username=args.onvif_username, onvif_password=args.onvif_password,
      poll_hz=args.poll_hz, min_delta_deg=args.min_delta_deg,
      default_pan_scale=args.pan_scale, default_tilt_scale=args.tilt_scale,
      default_invert_pan=args.invert_pan, default_invert_tilt=args.invert_tilt)
  ctx.setup()
  ctx.loop_forever()
  return 0


if __name__ == '__main__':
  exit(main() or 0)
