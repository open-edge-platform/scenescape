#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import math
import numpy as np

from drawing import *

class_colors = {
  'Person': (0,0,255),
  'Vehicle': (255,0,0),
  'other': (0,255,255)
}

def displayScene(scene, curFrame, color, mask, font, onlyGID):
  label = str(curFrame)
  scene.displayScene(featureMask=mask, onlyGID=onlyGID)
  frame = scene.frame
  point = (10, 470)
  if point[1] > scene.frame.shape[0]:
    point = (point[0], scene.frame.shape[0] - 10)
  cv2.putText(frame, label, point, font, 1, (0,0,0), 5)
  cv2.putText(frame, label, point, font, 1, color, 2)
  cv2.imshow("Scene", frame)
  return

def centerTextWithinFrame(frame, label, loc, font, fsize, color):
  size, origin, scale = scl_text_size(frame, label, loc, (0, 0), font, fsize, 5)
  cv2.putText(frame, label, origin, font, int(fsize * scale), (0,0,0), int(5 * scale))
  cv2.putText(frame, label, origin, font, int(fsize * scale), color, int(2 * scale))
  return size

def labelObjects(objects, camDetect, frame, sensor, font, scale):
  old = []
  for obj in objects:
    found = False
    for cobj in camDetect:
      if obj.oid == cobj.oid:
        found = True
        break
    if not found:
      old.append(obj)
  for obj in camDetect:
    bounds = obj.boundingBoxPixels
    point = np.array((bounds.x + bounds.width / 2,
                      bounds.y + bounds.height / 2)) / scale
    label = "GID:%s" % (obj.gid)
    size = centerTextWithinFrame(frame, label, point, font, 1, sensor.color)
    label = "%s/%s" % (obj.oid, obj.reidVector)
    lsize = cv2.getTextSize(label, font, 0.5, 2)[0]
    point[1] += size[1] + lsize[1] / 2
    centerTextWithinFrame(frame, label, point, font, 0.5, sensor.color)
    tag_id = getattr(obj, 'tag_id', None)
    if tag_id is not None:
      label = tag_id
      lsize = cv2.getTextSize(label, font, 0.5, 2)[0]
      point[1] += size[1] + lsize[1] / 2
      centerTextWithinFrame(frame, label, point, font, 0.5, sensor.color)

    # color = (128,128,128)
    # for loc in obj.location[1:]:
    #   bounds = np.array(loc.bounds.cv) / scale
    #   bounds = tuple(map(tuple, bounds.astype(int)))
    #   scl_rect(frame, *bounds, color, 2)

    color = class_colors['other']
    if obj.__class__.__name__ in class_colors:
      color = class_colors[obj.__class__.__name__]
    if obj in old:
      color = (128,128,128)
    # bounds = np.array(obj.location[0].bounds.cv) / scale
    # bounds = tuple(map(tuple, bounds.astype(int)))
    # scl_rect(frame, *bounds, color, 2)
    bounds = obj.boundingBoxPixels
    scl_rect(frame, *bounds.cv, color, 2)

    estBounds = sensor.pose.projectEstimatedBoundsToCameraPixels(obj.sceneLoc,
                                                                 obj.bbMeters.size)
    scl_rect(frame, *estBounds.cv, (255,255,255), 2)

    pt = obj.averageCenter()
    if obj.location[0].bounds.isPointWithin(pt):
      scl_line(frame, (int(bounds.x1), int(pt.y)), (int(bounds.x2), int(pt.y)), color, 2)
      scl_line(frame, (int(pt.x), int(bounds.y1)), (int(pt.x), int(bounds.y2)), color, 2)

  return

def drawTextBelow(frame, label, point, font, fscale, fthick, tcolor, bgcolor=None):
  if bgcolor:
    size, origin, _ = scl_text_size(frame, label, point.cv, (-1, 1), font, fscale, fthick)
    lpoint = (origin[0] + size[0], origin[1] + size[1])
    scl_rect(frame, point.cv, lpoint, bgcolor, cv2.FILLED)
  size = scl_text(frame, label, point.cv, (-1, 1), font, fscale, tcolor, fthick)
  return size

def labelDimensions(objects, frame, font):
  for obj in objects:
    label = "%0.1fm x %0.1fm" % (obj.bbMeters.width, obj.bbMeters.height)
    lsize = drawTextBelow(frame, label, obj.boundingBoxPixels.origin, font, 0.5, 1,
                          (0,0,0), (255,0,255))

    # label = "%ipx x %ipx" % (obj.boundingBox.width, obj.boundingBox.height)
    # lpoint = obj.boundingBox.origin + (0, lsize[1] + 2)
    # lsize = drawTextBelow(frame, label, lpoint, font, 0.5, 1, (0,0,0), (255,0,255))

    # label = "%0.2f deg" % (obj.baseAngle)
    # lpoint = obj.boundingBox.origin + (0, lsize[1] + 2)
    # lsize = drawTextBelow(frame, label, lpoint, font, 0.5, 1, (0,0,0), (255,0,255))
  return

def drawHorizon(frame, sensor):
  focalLength = sensor.pose.intrinsics.intrinsics[1][1]
  height = frame.shape[0]
  fovAngle = 2 * math.degrees(math.atan((height / 2) / focalLength))
  camAngle = sensor.pose.euler_rotation[2]
  horizonAngle = 90 - camAngle
  horizonHeight = focalLength * math.sin(math.radians(horizonAngle))
  y = int(height / 2 - horizonHeight)
  # print("HORIZON", focalLength, height, fovAngle, camAngle, horizonAngle, horizonHeight, y)
  scl_line(frame, (0, y), (frame.shape[1] - 1, y), (128, 128, 128), 5)
  return

def overlayDetailsOnCameraFrames(scene, sensor, altFrame, camDetect, font, showHomography):
  scale = 1
  # if frame.shape[1] > 640:
    #   scale = 2
    #   frame = cv2.resize(frame, (int(frame.shape[1] / scale), int(frame.shape[0] / scale)))
  curObjects = scene.tracker.currentObjects()
  sensorObjects = {}
  for category in curObjects:
    sensorObjects[category] = [x for x in curObjects[category]
                                if x.vectors[0].camera == sensor]
  for category in sensorObjects:
    ogroup = sensorObjects[category]
    if not len(ogroup):
      continue
    labelObjects(curObjects[category], ogroup, altFrame, sensor, font, scale)
    labelDimensions(ogroup, altFrame, font)

  cv2.namedWindow(camDetect['id'], cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

  # FIXME - if onlyGID display only that one
  scl_rect(altFrame, (0, 0), altFrame.shape[:2][::-1], sensor.color, 8)
  if showHomography:
    for pt in sensor.camCoords:
      pt = (np.array(pt) / scale).astype(int)
      scl_circle(altFrame, tuple(pt), 5, (0,255,0), -1)

  cv2.imshow(camDetect['id'], altFrame)

  # warp = cv2.warpPerspective(frame, sensor.transform, sensor.res)
  # cv2.imshow(camDetect['id'] + "2", warp)
  return
