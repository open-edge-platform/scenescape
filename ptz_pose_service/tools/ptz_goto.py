#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Move a PTZ camera to a position, arriving from a known direction on each axis.

With gear backlash, where the camera physically ends up depends on the
direction it arrived from, and the pose service needs to know that direction
at startup (``pan_home_approach``/``tilt_home_approach``). This overshoots each
axis on the opposite side first, so the final approach is the requested one.

Run inside the ptz-pose container:

    docker compose exec ptz-pose python3 /tmp/tools/ptz_goto.py \\
        --onvif-host 192.168.0.91 --onvif-port 2020 \\
        --pan-approach decreasing --tilt-approach increasing

Without ``--pan``/``--tilt`` the current position is kept (re-approached).
Prints the final position as JSON on the last line.
"""

import argparse
import json
import os
import time

from dlstreamer.onvif import find_ptz_capable_profiles, PTZController
from dlstreamer.onvif.ptz.types import PTZVector

APPROACHES = ("increasing", "decreasing")


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--onvif-host", required=True)
  parser.add_argument("--onvif-port", type=int, default=80)
  parser.add_argument("--onvif-username", default=os.environ.get("ONVIF_USERNAME", ""))
  parser.add_argument("--onvif-password", default=os.environ.get("ONVIF_PASSWORD", ""))
  parser.add_argument("--pan", type=float, help="target pan (default: current)")
  parser.add_argument("--tilt", type=float, help="target tilt (default: current)")
  parser.add_argument("--pan-approach", choices=APPROACHES)
  parser.add_argument("--tilt-approach", choices=APPROACHES)
  parser.add_argument("--overshoot", type=float, default=0.05,
                      help="ONVIF units to overshoot before the final approach; more than the "
                           "backlash, so the slack is fully taken up")
  parser.add_argument("--settle-s", type=float, default=3.0)
  parser.add_argument("--status-only", action="store_true",
                      help="only print the current position")
  return parser


def before(target, approach, overshoot):
  """Where to start from so the last move toward ``target`` goes the ``approach`` way."""
  if approach is None:
    return target
  return target - overshoot if approach == "increasing" else target + overshoot


def main():
  args = build_argparser().parse_args()
  profiles = list(find_ptz_capable_profiles(
      [{"hostname": args.onvif_host, "port": args.onvif_port}],
      args.onvif_username, args.onvif_password))
  if not profiles:
    print(f"No PTZ-capable profile found on {args.onvif_host}:{args.onvif_port}")
    return 1
  controller = PTZController(args.onvif_host, args.onvif_port, profiles[0].profile_token,
                             args.onvif_username, args.onvif_password)
  position = controller.get_status().position

  if not args.status_only:
    pan = position.pan if args.pan is None else args.pan
    tilt = position.tilt if args.tilt is None else args.tilt
    controller.absolute_move(PTZVector(pan=before(pan, args.pan_approach, args.overshoot),
                                       tilt=before(tilt, args.tilt_approach, args.overshoot)))
    time.sleep(args.settle_s)
    controller.absolute_move(PTZVector(pan=pan, tilt=tilt))
    time.sleep(args.settle_s)
    position = controller.get_status().position

  print(json.dumps({"pan": position.pan, "tilt": position.tilt}))
  return 0


if __name__ == "__main__":
  exit(main())
