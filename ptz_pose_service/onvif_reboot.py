#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Reboot an ONVIF-capable camera via the device management SystemReboot command."""

import argparse
import os
import site

from onvif import ONVIFCamera


def build_argparser():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("camera", nargs="?", default="",
                       help="IP/hostname of camera, optionally with :port")
  parser.add_argument("--auth", default="", help="user:pass to authenticate as")
  return parser


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

  idx = args.auth.find(':')
  if idx < 0:
    print("Need both user and password separated by a colon for authentication")
    return 1
  user = args.auth[:idx]
  password = args.auth[idx + 1:]

  wsdl_path = find_wsdl_path()
  print("WSDL is", wsdl_path)

  print(f"Attempting connection to {cam_ip}:{cam_port}")
  mycam = ONVIFCamera(cam_ip, cam_port, user, password, wsdl_path)
  hostname = mycam.devicemgmt.GetHostname()
  print("Connected to", hostname.Name)

  print("Sending SystemReboot request...")
  result = mycam.devicemgmt.SystemReboot()
  print("Camera response:", result)

  return 0


if __name__ == '__main__':
  exit(main())
