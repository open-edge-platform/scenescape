#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from argparse import ArgumentParser
import os
import cv2
import re

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("video", help="video file to test")
  return parser

def main():
  args = build_argparser().parse_args()

  print("CV2 version", cv2.__version__)
  if re.match("^[0-9]+$", args.video):
    args.video = int(args.video)
  cam = cv2.VideoCapture(args.video)
  assert cam.isOpened()
  print("Codec", int(cam.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, byteorder = 'little'))
  ret, frame = cam.read()
  if not ret:
    print("####### FAILED TO READ FRAME #######")
    exit(1)

  print("Read frame", frame.shape)
  return

if __name__ == '__main__':
  exit(main() or 0)
