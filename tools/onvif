#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import json
import logging
import os
import site
import time

import zeep
from onvif import ONVIFCamera

logging.getLogger("requests").setLevel(logging.WARNING)

def zeep_pythonvalue(self, xmlvalue):
  return xmlvalue

zeep.xsd.simple.AnySimpleType.pythonvalue = zeep_pythonvalue

def build_argparser():
  parser = argparse.ArgumentParser()
  parser.add_argument("camera", help="IP/hostname of camera")
  parser.add_argument("commands", nargs="*", help="commands to execute: [ptz][+-]<float>")
  parser.add_argument("--auth", default="admin:admin123", help="user:pass to authenticate as")
  parser.add_argument("--presets", default="presets.json", help="file with saved positions")
  parser.add_argument("--flag", action="store_true", help="flag to do something")
  return parser

def ptzEqual(ptz1, ptz2):
  return ptz1.Position.PanTilt.x == ptz2.Position.PanTilt.x \
    and ptz1.Position.PanTilt.y == ptz2.Position.PanTilt.y \
    and ptz1.Position.Zoom.x == ptz2.Position.Zoom.x

def moveCamera(ptz, token, pan=None, tilt=None, zoom=None):
  status = ptz.GetStatus({'ProfileToken': token})

  request = ptz.create_type('AbsoluteMove')
  request.ProfileToken = token
  request.Position = status.Position
  if pan is not None:
    request.Position.PanTilt.x = pan
  if tilt is not None:
    request.Position.PanTilt.y = tilt
  if zoom is not None:
    request.Position.Zoom.x = zoom
  ret = ptz.AbsoluteMove(request)

  tries = 0
  last = status
  while True:
    time.sleep(1)
    current = ptz.GetStatus({'ProfileToken': token})
    print("Now at", current.Position.PanTilt.x, current.Position.PanTilt.y,
          current.Position.Zoom.x)
    if ptzEqual(current, request) or ptzEqual(current, last) or tries > 3:
      break
    tries += 1
    last = current
  return

def setZoom(val, ptz, token):
  return moveCamera(ptz, token, zoom=val)

def setPan(val, ptz, token):
  return moveCamera(ptz, token, pan=val)

def setTilt(val, ptz, token):
  return moveCamera(ptz, token, tilt=val)

def main():
  args = build_argparser().parse_args()

  for path in site.getsitepackages():
    pdir = os.path.dirname(path)
    wsdl_path = os.path.join(pdir, "site-packages/wsdl")
    if os.path.isdir(wsdl_path):
      print("WSDL is", wsdl_path)
      break

  cam_ip = args.camera
  cam_port = 80
  if cam_ip.find(':') >= 0:
    idx = cam_ip.find(':')
    cam_port = int(cam_ip[idx+1:])
    cam_ip = cam_ip[:idx]

  presets = None
  if args.presets is not None and os.path.exists(args.presets):
    with open(args.presets) as f:
      p = json.load(f)
      if cam_ip in p:
        presets = p[cam_ip]
        print("PRESETS LOADED", presets)

  idx = args.auth.find(':')
  if idx < 0:
    print("Need both user and password separated by a colon for authentication")
    exit(1)

  user = args.auth[:idx]
  password = args.auth[idx+1:]

  print('Attempting connection to ' + cam_ip)
  mycam = ONVIFCamera(cam_ip, cam_port, user, password, wsdl_path)
  hostname = mycam.devicemgmt.GetHostname()

  print('Connected to ' + hostname.Name)

  ptz = mycam.create_ptz_service()
  media = mycam.create_media_service()
  media_profile = media.GetProfiles()[0]
  token = media_profile.token

  # caps = mycam.devicemgmt.GetCapabilities()
  # print(caps)

  # request = ptz.create_type('GetConfigurationOptions')
  # request.ConfigurationToken = media_profile.PTZConfiguration.token
  # ptz_configuration_options = ptz.GetConfigurationOptions(request)
  # print(ptz_configuration_options)

  pan = tilt = zoom = None
  for cmd in args.commands:
    if presets is not None and cmd in presets:
      pan, tilt, zoom = presets[cmd]
    else:
      func = cmd[0]
      relative = cmd[1] in "+-"
      val = float(cmd[1:])

      # FIXME - if relative then do relative movement
      if cmd[0] == 't':
        if tilt is not None:
          moveCamera(ptz, token, pan=pan, tilt=tilt, zoom=zoom)
          pan = tilt = zoom = None
        tilt = val
      elif cmd[0] == 'p':
        if pan is not None:
          moveCamera(ptz, token, pan=pan, tilt=tilt, zoom=zoom)
          pan = tilt = zoom = None
        pan = val
      elif cmd[0] == 'z':
        if zoom is not None:
          moveCamera(ptz, token, pan=pan, tilt=tilt, zoom=zoom)
          pan = tilt = zoom = None
        zoom = val

  moveCamera(ptz, token, pan=pan, tilt=tilt, zoom=zoom)

  # status = mycam.ptz.GetStatus({'ProfileToken': token})
  # print(status.Position)
  # zoom = status.Position.Zoom.x
  # if args.zoom is not None:
  #   zoom = args.zoom
  # setZoom(zoom, ptz, token)

  # steps = 128
  # for z in range(steps):
  #   zoom = z / steps
  #   setZoom(zoom, ptz, token)
  #   time.sleep(1)
  #   print()

  # while True:
  #     status = mycam.ptz.GetStatus({'ProfileToken': token})
  #     #print("%0.10f" % status.Position.Zoom.x)

  return

if __name__ == '__main__':
  exit(main() or 0)

