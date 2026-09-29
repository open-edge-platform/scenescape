#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Reboot an ONVIF-capable camera via the device management SystemReboot command.

Run inside the ptz-pose container rather than a host virtualenv: the pinned
onvif-zeep/zeep versions in the image are known to work with these cameras,
whereas newer zeep releases fail their GetCapabilities call outright.

    docker cp ptz_pose_service/tools scenescape-ptz-pose-1:/tmp/tools
    docker compose exec ptz-pose python3 /tmp/tools/onvif_reboot.py 192.168.0.91:2020

Rebooting needs an administrator account, which is typically not the
PTZ-capable account the pose service runs as.
"""

import argparse
import getpass
import os
import site

from onvif import ONVIFCamera
from onvif.exceptions import ONVIFError


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("camera", nargs="?", default="192.168.0.91:2020",
                       help="IP/hostname of camera, optionally with :port")
  parser.add_argument("--username", default=os.environ.get("ONVIF_ADMIN_USERNAME"),
                      help="ONVIF admin username (default: ONVIF_ADMIN_USERNAME env var, "
                           "else prompted)")
  return parser


def prompt_credentials(username):
  """Resolve ONVIF admin credentials, prompting for whatever wasn't supplied.

  Deliberately reads ONVIF_ADMIN_USERNAME/ONVIF_ADMIN_PASSWORD rather than the
  ONVIF_USERNAME/ONVIF_PASSWORD pair the pose service runs with: rebooting
  needs an administrator account, while the service only needs a PTZ-capable
  one, and the two must stay independent.

  The password is never accepted as a CLI argument so it can't leak into
  shell history or the process list.
  """
  while not username:
    username = input("ONVIF admin username: ").strip()
  password = os.environ.get("ONVIF_ADMIN_PASSWORD")
  while not password:
    password = getpass.getpass(f"ONVIF password for {username}: ")
  return username, password


def find_wsdl_path():
  for path in site.getsitepackages():
    pdir = os.path.dirname(path)
    wsdl_path = os.path.join(pdir, "site-packages/wsdl")
    if os.path.isdir(wsdl_path):
      return wsdl_path
  raise FileNotFoundError("Could not locate onvif wsdl directory")


def main():
  args = build_argparser().parse_args()

  cam_ip = args.camera
  cam_port = 80
  if cam_ip.find(':') >= 0:
    idx = cam_ip.find(':')
    cam_port = int(cam_ip[idx + 1:])
    cam_ip = cam_ip[:idx]

  user, password = prompt_credentials(args.username)

  wsdl_path = find_wsdl_path()
  print("WSDL is", wsdl_path)

  print(f"Attempting connection to {cam_ip}:{cam_port}")
  try:
    mycam = ONVIFCamera(cam_ip, cam_port, user, password, wsdl_path)
    hostname = mycam.devicemgmt.GetHostname()
  except ONVIFError as err:
    print(f"Failed to connect to {cam_ip}:{cam_port} as {user}: {err}")
    return 1
  print("Connected to", hostname.Name)

  print("Sending SystemReboot request...")
  try:
    result = mycam.devicemgmt.SystemReboot()
  except ONVIFError as err:
    # Cameras commonly expose read-only ONVIF accounts that can drive PTZ but
    # can't reboot; that surfaces here as an "Authority failure" fault.
    print(f"Reboot rejected by camera: {err}")
    print(f"'{user}' may lack administrator rights; retry with an admin account.")
    return 1
  print("Camera response:", result)

  return 0


if __name__ == '__main__':
  exit(main())
