#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import cv2
import subprocess
import re
import time
import pandas

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("camera", help="camera")
  return parser

def v4l_get(path):
  cmd = ["v4l2-ctl", "--all", "-d", path]
  proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
  output, err = proc.communicate()
  lines = output.decode().splitlines()
  resolution = fps = None
  for line in lines:
    if "Width/Height" in line:
      m = re.match(r".*Width/Height *: *([0-9]+)/([0-9]+)", line)
      resolution = (float(m.group(1)), float(m.group(2)))
    elif "Frames per second" in line:
      m = re.match(r".*Frames per second *: *([0-9]+[.][0-9]+)", line)
      fps = float(m.group(1))
  return {'width': resolution[0], 'height': resolution[1], 'fps': fps}

def v4l_set(path, attribs):
  cmd = ["v4l2-ctl", f"--set-fmt-video=width={attribs['width']},height={attribs['height']}",
         "-p", str(attribs['fps']),
         "-d", path]
  proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
  output, err = proc.communicate()
  return

def cv2_get(cam):
  width = cam.get(cv2.CAP_PROP_FRAME_WIDTH)
  height = cam.get(cv2.CAP_PROP_FRAME_HEIGHT)
  fps = cam.get(cv2.CAP_PROP_FPS)
  resolution = (width, height)
  return {'width': resolution[0], 'height': resolution[1], 'fps': fps}

def cv2_set(cam, attribs):
  success = cam.set(cv2.CAP_PROP_FRAME_WIDTH, attribs['width'])
  success2 = cam.set(cv2.CAP_PROP_FRAME_HEIGHT, attribs['height'])
  success3 = cam.set(cv2.CAP_PROP_FPS, attribs['fps'])
  print("CV2 set", success, success2, success3)
  if not success or not success2 or not success3:
    print("Unable to use cv2.set(), are you sure gstreamer isn't being used?")
  return

def main():
  args = build_argparser().parse_args()

  print("OpenCV version:", cv2.__version__)

  v4l_path = args.camera
  if re.match("^[0-9]+$", v4l_path):
    v4l_path = "/dev/video" + v4l_path

  settings = {'width': 1280, 'height': 720, 'fps': 15}
  v4l_set(v4l_path, settings)
  v4l_settings = v4l_get(v4l_path)
  print("V4l settings:", v4l_settings)

  cam = cv2.VideoCapture(v4l_path)
  default_settings = cv2_get(cam)
  ret, frame = cam.read()
  capture_resolution = frame.shape[1::-1]
  print("CV2 settings:", default_settings)
  print("CV2 capture resolution", capture_resolution)

  cv2_set(cam, settings)
  new_settings = cv2_get(cam)
  ret, frame = cam.read()
  if not ret:
    print("Unable to get frame")
    exit(1)

  print("CV2 settings:", new_settings)
  print("CV2 capture resolution", frame.shape[1::-1])

  if settings != new_settings:
    print()
    print("CV2 failed to set correct values")
    print(pandas.DataFrame([[settings[key], new_settings[key],
                             settings[key] == new_settings[key]] for key in settings],
                           settings.keys(), ["requested", "actual", "match"]))
    exit(1)

  return

if __name__ == '__main__':
  exit(main() or 0)
