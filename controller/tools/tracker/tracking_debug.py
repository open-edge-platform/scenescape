# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from enum import IntEnum

import cv2
import numpy as np
from drawing import *

from controller.ilabs_tracking import IntelLabsTracking
from controller.scene import Scene
from controller.tracking import Tracking
from scene_common.geometry import DEFAULTZ, Line, Point


class SceneDebug:
  # These methods are for testing by saving and restoring the tracking state machine
  def dumpState(self):
    state = {
        'reid_expired': [x.dump() for x in self.reidExpired],
        'objects': {},
    }

    for otype in self._objects:
      objects = []
      for obj in self._objects[otype]:
        objects.append(obj.dump())
      state['objects'][otype] = objects
    return state

  def loadState(self, state, scene):
    if 'frame_average' in state:
      archived = state['objects']

      self.reidExpired = []
      reidExp = state['reid_expired']
      for exp in reidExp:
        vector = base64.b64decode(exp['reid'])
        vector = np.array(struct.unpack("256f", vector)).reshape(1, -1)
        self.reidExpired.append(Expired(exp['timestamp'], exp['gid'], vector,
                                        exp['frame_count'], exp['first_seen']))

    else:
      archived = state
    for otype in archived:
      objects = []
      for idx, obj in enumerate(archived[otype]):
        obj['id'] = idx
        camera_id = obj['vectors'][0]['camera']
        when = obj['location'][0]['timestamp']
        mobj, minW, maxW, maxH = Tracking.createObject(
            otype, obj, when, scene.cameras[camera_id])
        mobj.load(obj, scene)
        objects.append(mobj)
      if otype not in self.trackers:
        tracker = self.__class__()
        self.trackers[otype] = tracker
        tracker.start()
      self.trackers[otype]._objects = objects
    # FIXME - load objects into cameras?
    return

  def compareState(self, state):
    if 'frame_average' in state:
      archived = state['objects']
    else:
      archived = state
    match = True
    for otype in archived:
      print("Expected %s count" % (otype), len(archived[otype]))
      print("Actual %s count" % (otype), len(self.trackers[otype]._objects))
      if len(archived[otype]) != len(self.trackers[otype]._objects):
        print("Length mismatch")
        match = False

      for archived_obj in archived[otype]:
        category = archived_obj['category']
        gid = archived_obj['gid']
        location = Point(archived_obj['location'][0]['point'])
        if not location.is3D:
          location = Point(location.x, location.y, DEFAULTZ)
        print("Category", category)
        print("GID", gid)
        print("Expected Location", location)
        found_obj = False
        for obj in self.trackers[otype]._objects:
          if obj.gid == gid:
            found_obj = True
            break
        print("Have object", found_obj)
        if found_obj:
          tracked_loc = obj.location[0].point
          print("Calculated Location", tracked_loc)
          xdiff = round(abs(location.x - tracked_loc.x), 3)
          ydiff = round(abs(location.y - tracked_loc.y), 3)
          zdiff = round(abs(location.z - tracked_loc.z), 3)
          try:
            xdiff /= location.x
          except ZeroDivisionError:
            pass
          try:
            ydiff /= location.y
          except ZeroDivisionError:
            pass
          try:
            zdiff /= location.z
          except ZeroDivisionError:
            pass
          acceptable = 0.02
          if xdiff > acceptable or ydiff > acceptable or zdiff > acceptable:
            print("Wrong", xdiff, ydiff, zdiff)
            print(location.z, tracked_loc.z)
            print(abs(location.z - tracked_loc.z))
            match = False
          print("Loc Match", match)
        else:
          match = False
    return match


class DebugDisplay(IntEnum):
  INTERSECTIONS = 1
  CROSSHAIRS = 2
  FIELDOFVIEW = 4
  RADIUS = 8
  HOMOGRAPHY = 16
  ALLOBJECTS = 32
  REGIONS = 64
  OLDTRANSFORM = 128


pointColors = [(0, 0, 255), (0, 255, 255), (0, 128, 0), (255, 64, 64)]


class SceneDisplayDebug:
  def displayScene(self, featureMask=None, onlyGID=None):
    img = self.background.copy()
    pad = [0, 0, 0, 0]
    w = len(img[0])
    h = len(img)
    if featureMask and featureMask & DebugDisplay.FIELDOFVIEW:
      for cameraID in self.cameras:
        camera = self.cameras[cameraID]
        spt = self.mapScale(pad[:2], camera.pose.translation)
        if spt.x < 0 and abs(spt.x) > pad[0]:
          pad[0] = abs(spt.x)
        if spt.x > w and spt.x - w > pad[2]:
          pad[2] = spt.x - w
        if spt.y < 0 and abs(spt.y) > pad[1]:
          pad[1] = abs(spt.y)
        if spt.y > h and spt.y - h > pad[3]:
          pad[3] = spt.y - h
      if sum(pad) > 0:
        pad = [int(x + 10) for x in pad]
        img = cv2.copyMakeBorder(img,
                                 left=pad[0], top=pad[1], right=pad[2], bottom=pad[3],
                                 borderType=cv2.BORDER_CONSTANT, value=(255, 255, 255))
        self.pad = pad[:2]

      for cameraID in self.cameras:
        camera = self.cameras[cameraID]
        color = camera.color
        # cv2.fillConvexPoly(img, np.array(camera.pose.regionOfView.coordinates), camera.color)
        fov = np.array(self.mapScale(
            pad[:2], camera.pose.regionOfView.coordinates), np.int32)
        radius = 5
        for idx in range(len(fov)):
          scl_circle(img, tuple(fov[idx]),
                     radius, pointColors[idx], -1)
          scl_circle(img, tuple(fov[idx]), radius, color, 1)
        scl_polylines(img, [fov], True, color, 1)

        scl_circle(img, self.mapScale(
            pad[:2], camera.pose.translation).cv, 5, color, -1)
        if featureMask and featureMask & DebugDisplay.HOMOGRAPHY:
          for pt in camera.mapCoords:
            scl_circle(img, tuple(pt), 5, color, 2)
        self.drawLabel(img, camera.cameraID, self.mapScale(
            pad[:2], camera.pose.translation))

    for name in self.regions:
      region = self.regions[name]
      points = np.array(self.mapScale(pad[:2], region.coordinates))
      scl_polylines(img, [points], True, (0, 192, 192), 2)

    for name in self.tripwires:
      region = self.tripwires[name]
      points = np.array(self.mapScale(pad[:2], region.coordinates))
      scl_polylines(img, [points], False, (0, 192, 192), 2)

    objects = self.tracker.currentObjects()
    if len(objects) == 0:
      cv2.imshow("Scene", img)
      self.frame = img
    else:
      for otype in objects:
        self.displaySceneObjects(img, pad, otype, featureMask, onlyGID)

    return

  def displaySceneObjects(self, img, pad, thingType, featureMask, onlyGID=None):
    diameter = 7
    crossCounter = 0
    if featureMask and featureMask & DebugDisplay.INTERSECTIONS:
      for cameraID in self.cameras:
        camera = self.cameras[cameraID]
        if hasattr(camera, thingType) and len(getattr(camera, thingType)):
          diameter += 3
      for cameraID in self.cameras:
        camera = self.cameras[cameraID]
        color = camera.color
        if hasattr(camera, thingType) and len(getattr(camera, thingType)):
          for obj in getattr(camera, thingType):
            if onlyGID and obj.gid != onlyGID:
              continue
            point = obj.orig_point
            scl_circle(img, self.mapScale(
                pad[:2], point).cv, diameter, color, -1)
            label = "%i/%i" % (obj.gid, obj.oid)
            self.drawLabel(img, label, self.mapScale(pad[:2], point))
            if featureMask & DebugDisplay.CROSSHAIRS:
              self.crosshairs(img, point, crossCounter)
            crossCounter += 1
            angle = Line(camera.pose.translation, point).angle
            endP = Line(camera.pose.translation, Point(polar=(camera.frameSize[0] * 2, angle)),
                        relative=True).end
            scl_line(img, self.mapScale(pad[:2], camera.pose.translation).cv,
                     self.mapScale(pad[:2], endP).cv, color, 2)
          diameter -= 3
        scl_circle(img, self.mapScale(pad[:2], camera.pose.translation).cv, 5,
                   (64, 64, 64), -1)
        if hasattr(camera, 'location'):
          scl_circle(img, self.mapScale(pad[:2], camera.location).cv, 5,
                     color, -1)
        leftL = Line(camera.pose.translation.as2Dxy,
                     Point(polar=(5, camera.pose.angle - 90)),
                     relative=True)
        rightL = Line(camera.pose.translation.as2Dxy,
                      Point(polar=(5, camera.pose.angle + 90)),
                      relative=True)
        scl_line(img, self.mapScale(pad[:2], leftL.origin).cv, self.mapScale(pad[:2], leftL.end).cv,
                 (128, 160, 128), 2)
        scl_line(img, self.mapScale(pad[:2], rightL.origin).cv, self.mapScale(pad[:2], rightL.end).cv,
                 (128, 128, 160), 2)

    if featureMask and featureMask & DebugDisplay.ALLOBJECTS:
      for cameraID in self.cameras:
        camera = self.cameras[cameraID]
        if thingType in camera.objects:
          for obj in camera.objects[thingType]:
            scl_circle(img, self.mapScale(
                pad[:2], obj.orig_point).cv, 18, camera.color, 3)
            scl_circle(img, self.mapScale(
                pad[:2], obj.orig_point).cv, 15, (255, 0, 255), 3)

    objects = self.tracker.currentObjects(thingType)
    for obj in objects:
      if onlyGID and obj.gid != onlyGID:
        continue

      point = obj.sceneLoc

      if featureMask and featureMask & DebugDisplay.HOMOGRAPHY:
        points = np.array([p.cv for p in self.mapScale(pad[:2], obj.bbShadow)])
        scl_polylines(img, [points], True, obj.vectors[0].camera.color, 2)

      if featureMask and featureMask & DebugDisplay.INTERSECTIONS:
        for org in obj.vectors:
          endP = org.point
          begP = org.camera.pose.translation
          scl_line(img, self.mapScale(pad[:2], begP).cv, self.mapScale(pad[:2], endP).cv,
                   (0, 128, 0), 2)

      scl_circle(img, self.mapScale(
          pad[:2], point).cv, diameter, (0, 255, 0), -1)
      if featureMask and featureMask & DebugDisplay.OLDTRANSFORM and hasattr(point, 'oldway'):
        scl_circle(img, self.mapScale(
            pad[:2], point.oldway).cv, diameter + 2, (255, 152, 69), 3)

      if featureMask and featureMask & DebugDisplay.RADIUS:
        scl_circle(img, self.mapScale(pad[:2], point).cv,
                   int(obj.vMeters / 2),
                   (0, 0, 255), 2)
        scl_circle(img, self.mapScale(pad[:2], point).cv,
                   int(obj.vMeters),
                   (0, 255, 0), 2)
        if len(obj.location) > 1:
          ptl = point
          for pt in obj.location[1:]:
            scl_circle(img, self.mapScale(pad[:2], pt.point).cv,
                       diameter, (0, 192, 0), 2)
            scl_line(img, self.mapScale(pad[:2], ptl).cv, self.mapScale(pad[:2], pt.point).cv,
                     (0, 192, 0), 2)
            ptl = pt.point
          b = obj.estimateCoef()
          if b is not None:
            pt = obj.location[-1].point
            pte = Point(point.x, b(point.x))
            scl_line(img, self.mapScale(pad[:2], pt).cv, self.mapScale(pad[:2], pte).cv,
                     (0, 0, 128), 2)
          b = obj.estimateCoef(5)
          if b is not None:
            pt = obj.location[:5][-1].point
            pte = Point(point.x, b(point.x))
            scl_line(img, self.mapScale(pad[:2], pt).cv, self.mapScale(pad[:2], pte).cv,
                     (32, 128, 128), 2)

      if featureMask and featureMask & DebugDisplay.INTERSECTIONS:
        obj.displayIntersections(img, self.mapScale, pad[:2])
      label = "%i" % (obj.gid)
      # if len(obj.location) > 1:
      #   v = obj.expected(self.lastWhen + 1/15)
      #   vline = Line(obj.sceneLoc.as2Dxy, v.as2Dxy)
      #   scl_line(img, self.ms(pad[:2], vline.origin).cv,
      #            self.ms(pad[:2], vline.end).cv, (0,128,255), 2)

      self.drawLabel(img, label, self.mapScale(pad[:2], point), True, True)

    cv2.imshow("Scene", img)
    self.frame = img
    return

  # No, it's not web scale, it's Map Scale!
  # Takes care of converting coordinates to map pixel points
  def mapScale(self, offset, obj):
    bgRes = self.background.shape[1::-1]
    if isinstance(obj, Point):
      pt = Point(obj.x * self.scale, bgRes[1] - obj.y * self.scale)
      return pt + offset
    elif isinstance(obj, (list, tuple, np.ndarray)):
      if len(obj) == 2 and not isinstance(obj[0], Point):
        return [int(offset[0] + obj[0] * self.scale),
                int(offset[1] + bgRes[1] - obj[1] * self.scale)]
      nl = []
      for item in obj:
        nl.append(self.mapScale(offset, item))
      return nl
    return None

  def crosshairs(self, img, pt, counter):
    cv2.line(img, pt.cv, (0, int(pt.y)), (0, 0, 0), 1)
    cv2.line(img, pt.cv, (int(pt.x), 0), (0, 0, 0), 1)
    label = str(int(pt.x))
    cv2.putText(img, label, (int(pt.x), 15 * (counter + 1)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    label = str(int(pt.y))
    cv2.putText(img, label, (30 * counter, int(pt.y)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return

  def drawLabel(self, img, label, point, centerX=False, centerY=False):
    font = cv2.FONT_HERSHEY_SIMPLEX
    fsize = 0.5
    pt = point
    if isinstance(pt, Point):
      pt = pt.cv
    rel = [-1, 1]
    if centerX:
      rel[0] = 0
    if centerY:
      rel[1] = 0
    _, origin, scale = scl_text_size(img, label, pt, rel, font, fsize, 5)
    cv2.putText(img, label, origin, font, fsize *
                scale, (0, 0, 0), int(3 * scale))
    cv2.putText(img, label, origin, font, fsize *
                scale, (255, 255, 255), int(1 * scale))
    return

def copyMethods(dstClass, srcClass):
  for name, method in srcClass.__dict__.items():
    if callable(method):
      setattr(dstClass, name, method)

copyMethods(IntelLabsTracking, SceneDebug)

Scene.available_trackers = {
  'intel_labs': IntelLabsTracking,
}

copyMethods(Scene, SceneDisplayDebug)
