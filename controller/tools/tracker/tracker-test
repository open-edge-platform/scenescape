#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
import sys
import tempfile
from argparse import ArgumentParser

from tracking_debug import *

from scene_common import log
from scene_common.geometry import Rectangle
from scene_common.scenescape import scenescape


def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("input", nargs="+", help="json file(s) to test")
  parser.add_argument("--verbose", "-v", action="store_true",
                      help="lots and lots of debug printing")
  parser.add_argument("--redump",
                      help="Redump output to new file in order to create new expected results")
  return parser

def main():
  args = build_argparser().parse_args()

  if args.verbose:
    log.LVL_TRACK = 20
    log.LVL_MIN = log.LVL_INFO

  for file in args.input:
    if args.redump == file:
      print("Cannot redump to same file as input", file=sys.stderr)
      return 1

    jfile = open(file, "r")

    linecount = 0
    while True:
      line = jfile.readline()
      linecount += 1
      if not line:
        break
      unit_test = json.loads(line)

      cfile, cfname = tempfile.mkstemp()
      os.write(cfile, bytes(json.dumps(unit_test['config']), 'UTF-8'))
      os.close(cfile)
      scene = scenescape(cfname).scene
      os.remove(cfname)

      print()
      print("Testing line", linecount, "frame", unit_test['frame'])
      scene.tracker.loadState(unit_test['state'], scene)
      input = unit_test['input']
      objects = scene.tracker.groupObjects(input['objects'])
      for otype, ogroup in objects.items():
        for obj in ogroup:
          if 'bounding_box_px' not in obj:
            obj['bounding_box_px'] = obj['bounding_box']
            cam_id = input['id']
            cam = scene.sensors[cam_id]
            bounds = Rectangle(obj['bounding_box'])
            obj['bounding_box'] = cam.pose.intrinsics.pixelsToMeterPlane(bounds).asDict
        input['objects'] = ogroup
        # func usually called when mqtt is received. Here we simulate a received mqtt message
        scene.processSensorData(input, otype)
      scene.tracker.join()
      match = scene.tracker.compareState(unit_test['output'])
      print("MATCH", match)

      if args.redump:
        with open(args.redump, 'w') as outfile:
          unit_test['output'] = scene.tracker.dumpState()
          json.dump(unit_test, outfile)
          outfile.write("\n")

      if not match:
        print("#################################")
        print("TEST FAIL - Frame %i mismatch" % (unit_test['frame']))
        print("#################################")
        return 1
      else:
        print("PASS Frame %i" % (unit_test['frame']))

  return

if __name__ == '__main__':
  exit(main() or 0)
