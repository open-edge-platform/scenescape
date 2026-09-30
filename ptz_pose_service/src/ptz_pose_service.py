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
  parser.add_argument("--pose-settle-s", type=float, default=0.5, help="seconds of stillness before writing a ptz_delta pose (0 disables; per-camera override: pose_settle_s)")

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

  # The broker is used to push live pose updates to open calibration pages.
  parser.add_argument("--broker", default="broker.scenescape.intel.com",
                      help="MQTT broker host[:port] for live calibration-page updates")
  parser.add_argument("--brokerauth", default="/run/secrets/browser.auth",
                      help="user:password or path to JSON file for MQTT broker authentication")
  parser.add_argument("--brokerrootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to CA certificate for MQTT broker TLS verification")
  parser.add_argument("--rebaseline-check-s", type=float, default=2.0,
                      help="how often to check whether the stored pose was re-calibrated "
                           "elsewhere (e.g. from the Scenescape UI) and should replace the "
                           "cached home reference; 0 disables the check")
  parser.add_argument("--rebaseline-tolerance-deg", type=float, default=0.5,
                      help="how far the stored pose must differ from the last one this service "
                           "wrote before it counts as an external re-calibration")
  parser.add_argument("--no-notify-ui", dest="notify_ui", action="store_false", default=True,
                      help="don't push pose updates to open calibration pages (they will then "
                           "only show a new pose after a reload)")
  # Removed with the autocalibration pose mode; still accepted so existing deployments start.
  for obsolete in ("--autocalibration-url", "--autocalibration-rootcert"):
    parser.add_argument(obsolete, dest="obsolete_" + obsolete[2:].replace("-", "_"),
                        help=argparse.SUPPRESS)
  return parser


def main():
  args = build_argparser().parse_args()

  if args.discover_only:
    PTZPoseContext.logDiscoveredCameras(args.onvif_username, args.onvif_password)
    return 0

  log.info("PTZ Pose Service started")
  # After the first info line: scene_common.log fixes its level from the first message.
  for name in ("autocalibration_url", "autocalibration_rootcert"):
    if getattr(args, "obsolete_" + name) is not None:
      log.warning(f"--{name.replace('_', '-')} is no longer used and is ignored")
  ctx = PTZPoseContext(
      args.resturl, args.restauth, args.rootcert, args.config,
      onvif_username=args.onvif_username, onvif_password=args.onvif_password,
      poll_hz=args.poll_hz, min_delta_deg=args.min_delta_deg, pose_settle_s=args.pose_settle_s,
      default_pan_scale=args.pan_scale, default_tilt_scale=args.tilt_scale,
      default_invert_pan=args.invert_pan, default_invert_tilt=args.invert_tilt,
      broker=args.broker, brokerauth=args.brokerauth, brokerrootcert=args.brokerrootcert,
      rebaseline_check_s=args.rebaseline_check_s,
      rebaseline_tolerance_deg=args.rebaseline_tolerance_deg,
      notify_ui=args.notify_ui)
  ctx.setup()
  ctx.loop_forever()
  return 0


if __name__ == '__main__':
  exit(main() or 0)
