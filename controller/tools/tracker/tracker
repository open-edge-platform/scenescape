#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64
import json
import os
import struct
from argparse import ArgumentParser

import cv2
import numpy as np
from drawing_helper import *
from tracking_debug import *

from controller.detections_builder import buildDetectionsList
from scene_common import log
from scene_common.geometry import Region, Tripwire
from scene_common.json_track_data import CamManager
from scene_common.scenescape import SceneLoader


def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("input", nargs="+", help="json file(s) for simulation")
  parser.add_argument("--frame", type=int, help="frame number to stop at")
  parser.add_argument("--skip", default=0, type=int, help="frame number to skip to")
  parser.add_argument("--config", default="config.json", help="path to config file")
  parser.add_argument("--demo", help="path to save scene video to")
  parser.add_argument("--dumpframe", type=int, help="frame to dump unit test data for")
  parser.add_argument("--dumpall", action="store_true",
                      help="dump unit test data for all frames")
  parser.add_argument("--dumpout", help="file to write unit test data to")
  parser.add_argument("--verbose", "-v", action="store_true",
                      help="lots and lots of debug printing")
  return parser

def findResults(olist, rname):
  found = []
  for obj in olist:
    if not isinstance(obj, dict):
      continue
    if rname in obj:
      found.append(obj)

    for key in obj:
      ll = obj[key]
      if isinstance(ll, list):
        o = findResults(ll, rname)
        if o is not None:
          found.extend(o)

  return found

def serializeVectors(objects, key):
  found = findResults(objects, key)
  for obj in found:
    if isinstance(obj[key], np.ndarray):
      vector = obj[key].flatten().tolist()
      vector = struct.pack("256f", *vector)
      vector = base64.b64encode(vector).decode('utf-8')
      obj[key] = vector
  return

def publishEvents(scene, ts_str):
  for event_type in scene.events:
    for region_name, region in scene.events[event_type]:
      rid = scene.name + "/" + region_name
      etype = None
      if isinstance(region, Tripwire):
        etype = 'tripwire'
      elif isinstance(region, Region):
        etype = 'region'

      event_data = {
        'timestamp': ts_str,
        etype + '_id': rid,
        etype + '_name': region_name,
      }
      counts = {}
      num_objects = 0
      all_objects = []
      for otype, objects in region.objects.items():
        counts[otype] = len(objects)
        num_objects += counts[otype]
        all_objects += objects
      event_data['counts'] = counts
      event_data['objects'] = buildDetectionsList(all_objects, None)
      if hasattr(region, 'value'):
        event_data['value'] = region.value
      exited = getattr(region, 'exited', {})
      exited_dict = {}
      for exited_list in exited.values():
        exited_objs = []
        for exited_obj, dwell in exited_list:
          exited_dict[exited_obj.gid] = dwell
          exited_objs.extend([exited_obj])
        exited_objs = buildDetectionsList(exited_objs, scene)
        exited_data = [{'object': exited_obj, 'dwell': exited_dict[exited_obj['id']]} for exited_obj in exited_objs]
        event_data['exited'].extend(exited_data)

      if not isinstance(region, Tripwire) or num_objects > 0:
        print(event_type, event_data)
  return

def main():
  args = build_argparser().parse_args()

  if args.verbose:
    log.LVL_TRACK = 20
    log.LVL_MIN = log.LVL_INFO

  scene = SceneLoader(args.config).scene

  singleStep = True
  doStep = False
  curFrame = 0
  if args.frame is not None or args.dumpframe is not None or args.dumpall:
    singleStep = False

  if args.dumpall or args.dumpframe:
    with open(args.config) as f:
      config = json.load(f)

  # Make sure dumpout file is empty when doing dumpall
  if args.dumpall and args.dumpout is not None:
    with open(args.dumpout, 'w') as outfile:
      pass

  font = cv2.FONT_HERSHEY_SIMPLEX

  mgr = CamManager(args.input, scene)

  while curFrame < args.skip:
    mgr.nextFrame(scene, False, False)
    print(curFrame, end="\r")
    curFrame += 1

  cv2.namedWindow("Scene", cv2.WINDOW_NORMAL)
  scene.displayScene()

  if args.demo:
    sceneWriter, output = initDemoData(args, scene, mgr)

  mask = 0
  # mask |= DebugDisplay.INTERSECTIONS
  # mask |= DebugDisplay.FIELDOFVIEW
  # mask |= DebugDisplay.HOMOGRAPHY
  # mask |= DebugDisplay.REGIONS
  # mask |= DebugDisplay.OLDTRANSFORM

  sensor = None
  onlyGID = None

  doLoop = not args.demo and not args.dumpall
  while True:
    if not singleStep or doStep:
      jcount, camDetect, frame = mgr.nextFrame(scene, doLoop)
      if not camDetect:
        break
      if doStep:
        print(curFrame, camDetect['id'])
      doStep = False

      cd = camDetect.copy()
      if 'image' in cd:
        del cd['image']

      if args.dumpframe == curFrame - 1 or args.dumpall:
        unit_test = {
          'config': config,
          'state': scene.tracker.dumpState(),
          'input': camDetect
        }

      objects = scene.tracker.groupObjects(camDetect['objects'])

      for otype, ogroup in objects.items():
        camDetect['objects'] = ogroup
        scene.processCameraData(camDetect, otype)
        if len(scene.events):
          publishEvents(scene, camDetect['timestamp'])

      scene.tracker.waitForComplete()

      if args.dumpframe == curFrame - 1 or args.dumpall:
        unit_test['output'] = scene.tracker.dumpState()
        unit_test['frame'] = curFrame - 1
        unit_test['files'] = args.input

        for otype in unit_test['state']['objects']:
          ogroup = unit_test['state']['objects'][otype]
          serializeVectors(ogroup, 'reid')

        for otype in unit_test['output']['objects']:
          ogroup = unit_test['output']['objects'][otype]
          serializeVectors(ogroup, 'reid')

        if args.dumpout:
          mode = 'w'
          if args.dumpall:
            mode = 'a'
          with open(args.dumpout, mode) as outfile:
            json.dump(unit_test, outfile)
            outfile.write("\n")
          if not args.dumpall:
            exit(0)
        else:
          print(json.dumps(unit_test))

      altFrame = frame
      # altFrame = 255 * np.ones(frame.shape, np.uint8)

      sensor = scene.cameraWithID(camDetect['id'])
      if not sensor:
        print("Unknown sensor", camDetect['id'])
        print(scene.sensors)
        exit(1)

      drawHorizon(frame, sensor)

      overlayDetailsOnCameraFrames(scene, sensor, altFrame, camDetect, font,
                                  mask & DebugDisplay.HOMOGRAPHY)

      displayScene(scene, curFrame, sensor.color, mask, font, onlyGID)
      if args.demo:
        dframe = cv2.resize(frame, (mgr.frameres[0], mgr.frameres[1]))
        output[mgr.frameres[1] * jcount:mgr.frameres[1] * (jcount + 1),
               :mgr.frameres[0], :3] = dframe
        output[:scene.frame.shape[0],
               mgr.frameres[0]:mgr.frameres[0] + scene.frame.shape[1], :3] = scene.frame
        sceneWriter.write(output)

      if (args.frame is not None and args.frame == curFrame) \
         or (args.dumpframe is not None and args.dumpframe == curFrame - 1):
        singleStep = True
        doStep = False

      curFrame += 1

    key = cv2.waitKey(int(1000/60))
    singleStep, doStep, __break = handleKeyPress(key, scene, sensor, curFrame, singleStep, doStep, mask, font, onlyGID)
    if __break:
      break

  cv2.destroyAllWindows()
  scene.tracker.join()

  if args.demo:
    # for jfile in jfiles:
    #   jfile.writer.release()
    sceneWriter.release()

  return

def handleKeyPress(key, scene, sensor, curFrame, singleStep, doStep, mask, font, onlyGID):
  if key == ord(" "):
    singleStep = not singleStep
  elif key == ord("."):
    mask ^= DebugDisplay.INTERSECTIONS
    if sensor:
      displayScene(scene, curFrame - 1, sensor.color, mask, font, onlyGID)
  elif key == ord("'"):
    mask ^= DebugDisplay.RADIUS
    if sensor:
      displayScene(scene, curFrame - 1, sensor.color, mask, font, onlyGID)
  elif key == ord(","):
    mask ^= DebugDisplay.ALLOBJECTS
    if sensor:
      displayScene(scene, curFrame - 1, sensor.color, mask, font, onlyGID)
  elif key == 13:
    singleStep = True
    doStep = True
    print()
  elif key == 27:
    return singleStep, doStep, True
  elif key == ord("Q") or key == ord("S") or key == ord("<") or key == ord(">"):
    gids = [x.gid for x in scene.person]
    gids2 = [x.gid for x in scene.vehicle]
    gids.extend(gids2)
    if len(gids):
      gids.sort()
      if onlyGID and onlyGID in gids:
        idx = gids.index(onlyGID)
      else:
        idx = -1
      idx += key - (61 + 21 * (key > 62))
      if idx < -1:
        onlyGID = gids[idx+1]
      elif idx < 0 or idx >= len(gids):
        onlyGID = None
      else:
        onlyGID = gids[idx]
      if sensor:
        displayScene(scene, curFrame - 1, sensor.color, mask, font, onlyGID)
  elif key > -1:
    print("KEY", key)
  return singleStep, doStep, False

def initDemoData(args, scene, mgr):
  res = [scene.frame.shape[1], scene.frame.shape[0]]
  res[0] += mgr.frameres[0]
  res[1] = max(mgr.frameres[1] * len(mgr.jfiles), res[1])
  four_cc = cv2.VideoWriter_fourcc(*"MP4V")
  base = os.path.splitext(args.demo)
  sceneWriter = cv2.VideoWriter(base + ".mp4", four_cc, 15 * len(mgr.jfiles), tuple(res))
  output = np.zeros([res[1], res[0], 3], np.uint8)
  return sceneWriter, output

if __name__ == '__main__':
  exit(main() or 0)
