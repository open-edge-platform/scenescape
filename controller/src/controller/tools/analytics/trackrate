#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import json
import os

from controller.detections_builder import buildDetectionsList
from scene_common.json_track_data import CamManager
from scene_common.scenescape import SceneLoader
from scene_common.schema import SchemaValidation
from scene_common.timestamp import get_epoch_time

SCHEMA_PATH = os.path.abspath(
  os.path.join(os.path.dirname(__file__), '..', 'schema', 'metadata.schema.json')
)

def build_argparser():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("input", nargs="+", help="json file(s) for simulation")
  parser.add_argument("--config", default="config.json", help="path to config file")
  parser.add_argument("--schema", default=SCHEMA_PATH, help="path to config file")
  parser.add_argument("--frame", type=int, help="frame number to stop at")
  parser.add_argument("--skip-validation", action="store_true",
                      help="Skip JSON Validation for performance measurement")
  parser.add_argument("--track", help="path to write tracking JSON to")
  return parser

def publishDetections(trackFile, scene, objects, jdata):
  objList = []
  for category in objects.keys():
    currObjects = scene.tracker.currentObjects(category)
    for obj in currObjects:
      objList.append(obj)

  jdata['objects'] = buildDetectionsList(objList, None)
  jstr = json.dumps(jdata)
  trackFile.write(jstr)
  trackFile.write("\n")
  return

def main():
  args = build_argparser().parse_args()

  schema_val = SchemaValidation(args.schema)

  if args.track:
    trackFile = open(args.track, "w")

  scene = SceneLoader(args.config).scene
  mgr = CamManager(args.input, scene)
  curFrame = 0

  timeTotal = 0
  timeVal = 0
  curGoodFrames = 0
  curObject = 0
  startTime = get_epoch_time()
  detectedCategory = None

  while True:
    jcount, camDetect, frame = mgr.nextFrame(scene, loop=False)
    if not camDetect:
      break

    timeStepStart = get_epoch_time()
    timeStepAfterVal = get_epoch_time()
    objects = scene.tracker.groupObjects(camDetect['objects'])

    camDetect['objects'] = objects
    scene.processCameraData(camDetect)

    if not args.skip_validation:
      if not schema_val.validateMessage("detector", camDetect):
        print("Failed validating json message {}".format(camDetect))
        continue

    # FIXME - write scene data. Need to include frame num & cam ID
    # for later conversion to XML.
    if args.track:
      jdata = {
        'cam_id': camDetect['id'],
        'frame': camDetect['frame'],
        'timestamp': camDetect['timestamp']
      }
      publishDetections(trackFile, scene, objects, jdata)

    timeStepDone = get_epoch_time()
    for detectedCategory in objects.keys():
      if len(objects) and objects[detectedCategory] != None and len(objects[detectedCategory]):
        curGoodFrames += 1
        curObject += len(objects[detectedCategory])
    timeTotal += (timeStepDone - timeStepStart)
    timeVal += (timeStepAfterVal - timeStepStart)

    curFrame += 1
    if args.frame and curFrame == args.frame:
      break

  stopTime = get_epoch_time()
  realTime = stopTime - startTime
  print("PERF: Total time: {} Validation time {}, Homography avg"
        " {:.2f}ms Validation avg {:.2f}ms"
        .format(timeTotal, timeVal, (timeTotal - timeVal)*1000/(curFrame),
                timeVal*1000 / curFrame))
  print("PERF: Processed {} objects shown in {} frames, total of {} frames ***"
        .format(curObject, curGoodFrames, curFrame))
  print("PERF: {:.2f} OPS (total) {:.2f} FPS (total) ***"
        .format(curObject/(realTime), curGoodFrames/(realTime)))
  print("PERF: (without getFrame) {:.2f} OPS (total) {:.2f} FPS (total) ***"
        .format(curObject/(timeTotal), curGoodFrames/(timeTotal)))

  scene.tracker.join()

  return

if __name__ == '__main__':
  exit(main() or 0)
