#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
from argparse import ArgumentParser

import cv2
from tracking_debug import *

from scene_common.json_track_data import CamManager
from scene_common.scenescape import scenescape


def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("output", help="png file to write")
  parser.add_argument("input", nargs="+", help="json file(s) for simulation")
  parser.add_argument("--frame", type=int, help="frame number to stop at")
  parser.add_argument("--skip", default=0, type=int, help="frame number to skip to")
  parser.add_argument("--config", default="config.json", help="path to config file")
  return parser

def main():
  args = build_argparser().parse_args()

  scene = scenescape(args.config).scene
  mgr = CamManager(args.input, scene)

  curFrame = 0
  while curFrame < args.skip:
    mgr.nextFrame(scene, False, False)
    print(curFrame, end="\r")
    curFrame += 1

  tracked_objects = {}

  while True:
    jcount, camDetect, frame = mgr.nextFrame(scene, False)
    if not camDetect:
      break

    objects = scene.tracker.groupObjects(camDetect['objects'])
    for otype, ogroup in objects.items():
      camDetect['objects'] = ogroup
      scene.processSensorData(camDetect, otype)

    scene.tracker.waitForComplete()

    curObjects = scene.tracker.currentObjects()
    for detectionType in curObjects:
      for obj in curObjects[detectionType]:
        if obj.gid not in tracked_objects:
          tracked_objects[obj.gid] = []
        tracked_objects[obj.gid].append(obj.sceneLoc)

    if (args.frame is not None and args.frame == curFrame):
      break
    curFrame += 1

  scene.tracker.join()

  img = scene.background.copy()
  for gid in tracked_objects:
    locations = tracked_objects[gid]
    for pair in zip(locations, locations[1:]):
      if hasattr(scene, 'mapScale'):
        points = [scene.mapScale((0,0), x).cv for x in pair]
      else:
        points = [scene.ms((0,0), x).cv for x in pair]
      cv2.line(img, *points, (0,192,0))

  base, ext = os.path.splitext(args.output)
  path = base + ".png"
  cv2.imwrite(path, img)

  return

if __name__ == '__main__':
  exit(main() or 0)
