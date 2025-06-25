#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import traceback
from argparse import ArgumentParser

import cv2
import numpy as np
from drawing import *

from scene_common import log
from scene_common.geometry import Point, Size
from scene_common.scenescape import scenescape
from scene_common.transform import HomographyTransform

log.LVL_TRACK = 20
#log.LVL_MIN = log.LVL_TRACK + 1
log.LVL_MIN = log.LVL_TRACK

pointColors = [(0,0,255), (0,255,255), (0,128,0), (255,64,64),
               (0xAA,0x00,0x00), (0x00,0xAA,0x00), (0x00,0xAA,0xAA), (0x00,0x00,0xAA),
               (0xAA,0x00,0xAA), (0x00,0x55,0xAA), (0xAA,0xAA,0xAA), (0x55,0x55,0x55),
               (0xFF,0x55,0x55), (0x55,0xFF,0x55), (0xFF,0xFF,0x55), (0x55,0x55,0xFF),
               (0xFF,0x55,0xFF), (0x55,0xFF,0xFF)]

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("map", help="image of map")
  parser.add_argument("video", help="video file to get frame from")
  parser.add_argument("config", help="JSON file for tracker config")
  parser.add_argument("camera", help="ID of camera in config")
  parser.add_argument("--aspect", help="aspect ratio to force")
  parser.add_argument("--region", help="region to display")
  return parser

class Cybertronium:
  def __init__(self, number, name, image, coords, intrinsics=None, rcoords=None):
    self.number = number
    self.windowName = name
    self.registered = False
    self.coords = []
    self.rcoords = rcoords
    self.image = self.originalImage = image
    if intrinsics is not None:
      self.image = intrinsics.unwarp(self.originalImage)

    corners = [[0, 0], [self.image.shape[1] - 1, 0],
               [self.image.shape[1] - 1, self.image.shape[0] - 1],
               [0, self.image.shape[0] - 1]]
    normalized = []
    for idx in range(max(len(coords), len(corners))):
      c = ([-1, -1])
      if idx < len(coords):
        c = coords[idx]
      if not self.coordInFrame(c):
        c = corners[idx]
      normalized.append(c)
    self.coords = normalized
    self.moving = None
    self.dotScale = self.scale = 1
    size = self.image.shape[:2]
    if size[1] > 800 or size[0] > 640:
      self.dotScale = int((size[1] + 639) / 640)
    return

  def setImage(self, image):
    self.originalImage = self.image = image
    return

  def drawPoints(self, img, radius, border):
    if self.moving is not None:
      pt = self.coords[self.moving]
      size = img.shape[:2]
      scl_line(img, (pt[0], 0), (pt[0], size[0]), (255,255,255), 1)
      scl_line(img, (0, pt[1]), (size[1], pt[1]), (255,255,255), 1)
      scl_line(img, (pt[0]+1, 0), (pt[0]+1, size[0]), (0,0,0), 1)
      scl_line(img, (0, pt[1]+1), (size[1], pt[1]+1), (0,0,0), 1)
      scl_line(img, (pt[0]-1, 0), (pt[0]-1, size[0]), (0,0,0), 1)
      scl_line(img, (0, pt[1]-1), (size[1], pt[1]-1), (0,0,0), 1)

    for idx in range(len(self.coords)):
      scl_circle(img, tuple(self.coords[idx]),
                 radius, pointColors[idx], -1)
      scl_circle(img, tuple(self.coords[idx]), radius, (0,0,0), border)
    return

  def drawName(self, img):
    size = Size(img.shape[1::-1])
    label = str(self.number)
    lsize = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                            1*self.scale, 2*self.scale)[0]
    radius = int(lsize[1] / 2) + 5
    pt = Point(10 + radius, size.height - 10 - radius)
    color = (0,0,128)
    if self.registered:
      color = (0,128,0)
    scl_circle(img, pt.cv, radius, color, -1)
    pt = pt + (-1 * lsize[0] / 2, lsize[1] / 2)
    cv2.putText(img, label, pt.cv, cv2.FONT_HERSHEY_SIMPLEX,
                1 * self.scale, (255,255,255), 2 * self.scale)
    return

  def display(self, cameraOrigin=None, regionOfView=None, scale=None, overlay=None):
    dimg = overlay
    if dimg is None:
      dimg = self.image.copy()

    print("CAMERA ORIGIN", cameraOrigin)
    print("REGION OF VIEW", regionOfView)

    size = Size(dimg.shape[1::-1])

    if self.rcoords is not None:
      for idx, coord in enumerate(self.rcoords):
        idxn = (idx + 1) % len(self.rcoords)
        coordn = self.rcoords[idxn]
        scl_line(dimg, coord.cv, coordn.cv, (0,0,128+64), 3)

    self.drawPoints(dimg, 5, 1)
    self.drawName(dimg)
    if self.scale > 1:
      nsize = (size.asNumpy / self.scale).astype(int)
      dimg = cv2.resize(dimg, nsize)

    if cameraOrigin is not None:
      scl_circle(dimg, cameraOrigin.cv, 5, (128,128,128), -1)
      scl_circle(dimg, cameraOrigin.cv, 5, (64,64,64), 1)
    if regionOfView is not None:
      cv2.polylines(dimg, [np.array(regionOfView)], True, (0,255,0), 5)

    cv2.imshow(self.windowName, dimg)
    return

  def findCoord(self, x, y, scale, dotScale, points):
    xs = x * scale
    ys = y * scale
    for idx in range(len(points)):
      c = points[idx]
      if isinstance(c, Point):
        c = c.asNumpyCartesian
      if abs(c[0] - xs) <= 5 * dotScale and abs(c[1] - ys) <= 5 * dotScale:
        return idx
    return None

  def coordInFrame(self, coord):
    nx, ny = coord
    if nx < 0 or nx >= self.image.shape[1] or ny < 0 or ny >= self.image.shape[0]:
      return False
    return True

  def normalizeCoord(self, coord):
    nx, ny = coord
    if nx < 0:
      nx = 0
    if nx >= self.image.shape[1]:
      nx = self.image.shape[1] - 1
    if ny < 0:
      ny = 0
    if ny >= self.image.shape[0]:
      ny = self.image.shape[0] - 1
    return [nx, ny]

  def handleEvent(self, event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
      self.moving = self.findCoord(x, y, self.scale, self.dotScale, self.coords)
      if self.moving is not None:
        self.offset = (self.coords[self.moving][0] - x * self.scale,
                       self.coords[self.moving][1] - y * self.scale)
      elif self.rcoords is not None:
        rpoint = self.findCoord(x, y, self.scale, self.dotScale, self.rcoords)
        print("REGION POINT", rpoint)
    elif event == cv2.EVENT_LBUTTONUP:
      self.moving = None
      param.map.display(cameraOrigin=param.cameraOrigin, regionOfView=param.regionOfView)
      param.frame.display(overlay=param.overlayMap())
    elif event == cv2.EVENT_MOUSEMOVE:
      if self.moving is not None:
        nc = (x * self.scale + self.offset[0], y * self.scale + self.offset[1])
        self.coords[self.moving] = self.normalizeCoord(nc)
        param.map.display(cameraOrigin=param.cameraOrigin, regionOfView=param.regionOfView)
        param.frame.display(overlay=param.overlayMap())
    return

class Autobot:
  def __init__(self, number, image, fcoords, mapImage, mcoords, intrinsics, mapScale, rcoords):
    self.number = number
    #self.windowPrefix = "pos" + str(self.number) + "-"
    self.windowPrefix = ""
    self.warpName = self.windowPrefix + "warp"
    self.mapName = self.windowPrefix + "map"
    self.rcoords = rcoords
    self.mapScale = mapScale
    self.opacity = 0.5
    self.intrinsics = intrinsics

    self.doOverlay = True
    self.live = False

    self.frame = Cybertronium(self.number, self.warpName, image, fcoords, self.intrinsics)
    self.map = Cybertronium(self.number, self.mapName, mapImage, mcoords, rcoords=rcoords)

    pts_src = np.array(self.frame.coords)
    pts_dst = np.array(self.map.coords)
    pose = {
      'camera homography': pts_src,
      'map homography': pts_dst,
      'resolution': self.frame.image.shape[1::-1],
    }
    xform = HomographyTransform(pose, intrinsics)
    self.scaleFieldOfView(xform.regionOfView.points, self.mapScale)

    self.overlayMap()

    return

  def scaleFieldOfView(self, coords, scale):
    self.regionOfView = [tuple(c * scale for c in x.as2Dxy.cv) for x in coords]
    print("FIELD OF VIEW", self.regionOfView)
    return

  def initWindows(self):
    cv2.namedWindow(self.warpName, cv2.WINDOW_NORMAL)
    cv2.namedWindow(self.mapName, cv2.WINDOW_NORMAL)

    cv2.setMouseCallback(self.warpName, self.frame.handleEvent, self)
    cv2.setMouseCallback(self.mapName, self.map.handleEvent, self)

    self.frame.display(overlay=self.overlayMap())
    self.map.display(self.cameraOrigin, self.regionOfView)
    return

  def setFrame(self, frame, pose):
    self.frame.setImage(frame)
    self.frame.unwarp(self.intrinsics)
    self.frame.display()
    self.displayOverlay()
    return

  def transformPoint(self, point, transform):
    fpoint = np.float32([point]).reshape(-1,1,2)
    npoint = cv2.perspectiveTransform(fpoint, transform)
    tpoint = Point(npoint[0][0][0].item(), npoint[0][0][1].item())
    return tpoint

  def createOverlay(self, image1, image2, transform, asMap=False):
    if asMap:
      #image1 = 255 - image1
      mask = np.uint8(cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY))
      mask = np.where(mask == 255, 0, mask)
      mask = np.where(mask > 0, 1, mask)
    else:
      mask = np.uint8(np.full(image1.shape[:2], 1))
    print("TRANSFORM", transform)
    warp = cv2.warpPerspective(image1, transform,
                               (image2.shape[1], image2.shape[0]))
    mask = cv2.warpPerspective(mask, transform,
                               (image2.shape[1], image2.shape[0]))
    mask = np.dstack((mask, mask, mask))
    foreground = warp * mask
    #background = image2 * (1 - mask)
    #overlay = cv2.bitwise_xor(foreground, background)
    overlay = cv2.addWeighted(foreground, self.opacity, image2, 1.0, 0)
    return overlay

  def overlayMap(self):
    pts_src = np.array(self.frame.coords)
    pts_dst = np.array(self.map.coords)
    pose = {
      'camera homography': pts_src,
      'map homography': pts_dst,
      'resolution': self.frame.image.shape[1::-1],
    }
    xform = HomographyTransform(pose, self.intrinsics)
    self.scaleFieldOfView(xform.regionOfView.points, self.mapScale)
    pts_src = np.array(xform.camCoords)
    pts_dst = np.array(xform.mapCoords)
    transformFrame, status = cv2.findHomography(pts_src, pts_dst)
    transformMap = np.linalg.inv(transformFrame)

    if self.doOverlay:
      overlay = self.createOverlay(self.map.image, self.frame.image, transformMap, asMap=True)

      if self.rcoords is not None:
        for idx, coord in enumerate(self.rcoords):
          idxn = (idx + 1) % len(self.rcoords)
          coordn = self.rcoords[idxn]
          wcoord = self.transformPoint(coord.asNumpyCartesian, transformMap)
          wcoordn = self.transformPoint(coordn.asNumpyCartesian, transformMap)
          scl_line(overlay, wcoord.cv, wcoordn.cv, (0,0,128+64), 3)
    else:
      overlay = self.createOverlay(self.frame.image, self.map.image, transformFrame)

      if self.rcoords is not None:
        for idx, coord in enumerate(self.rcoords):
          idxn = (idx + 1) % len(self.rcoords)
          coordn = self.rcoords[idxn]
          scl_line(overlay, coord.cv, coordn.cv, (0,0,128+64), 3)

    self.cameraOrigin = xform.translation.as2Dxy
    self.cameraOrigin = Point(self.cameraOrigin.x * xform.scale[0],
                                         self.cameraOrigin.y * xform.scale[1])
    log.info("CAMERA ORIGIN", self.cameraOrigin)

    scl_line(overlay, (0, 0), self.cameraOrigin.cv, (0,255,0), 4)
    scl_line(overlay, (overlay.shape[1] - 1, 0), self.cameraOrigin.cv, (0,255,0), 4)

    return overlay

  def displayOverlay(self):
    overlay = self.overlayMap()
    cv2.imshow(self.warpName, overlay)
    return

  def handleEvent(self, event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
      clicked = None
      if self.doOverlay and self.rcoords is not None:
        pts_src = np.array(self.frame.coords)
        pts_dst = np.array(self.map.coords)
        transformMap, status = cv2.findHomography(pts_dst, pts_src)

        wcoords = []
        for coord in self.rcoords:
          wcoords.append(self.transformPoint(coord.point, transformMap).point)
        self.rmoving = self.frame.findCoord(x, y, self.frame.scale, self.frame.dotScale,
                                            wcoords)

        if self.rmoving is not None:
          self.offset = (wcoords[self.rmoving][0] - x * self.frame.scale,
                         wcoords[self.rmoving][1] - y * self.frame.scale)
          return

      self.doOverlay = not self.doOverlay
      self.displayOverlay()
    elif event == cv2.EVENT_LBUTTONUP:
      self.rmoving = None
    elif event == cv2.EVENT_MOUSEMOVE:
      if self.rmoving is not None:
        pts_src = np.array(self.frame.coords)
        pts_dst = np.array(self.map.coords)
        transformFrame, status = cv2.findHomography(pts_src, pts_dst)

        nc = (x * self.frame.scale + self.offset[0], y * self.frame.scale + self.offset[1])
        dewarp = self.transformPoint(nc, transformFrame)
        self.rcoords[self.rmoving] = dewarp
        self.displayOverlay()
    return

  def zoom(self, offset):
    self.intrinsics.intrinsics[0, 0] += offset
    self.intrinsics.intrinsics[1, 1] += offset
    print("Focal length %0.3f %0.3f" % (self.intrinsics.intrinsics[0, 0],
                                        self.intrinsics.intrinsics[1, 1]))
    self.frame.image = self.intrinsics.unwarp(self.frame.originalImage)
    self.frame.display(overlay=self.overlayMap())
    self.map.display(self.cameraOrigin, self.regionOfView, self.mapScale)
    return

  def moveCenter(self, xOffset, yOffset):
    self.intrinsics.intrinsics[0, 2] += xOffset
    self.intrinsics.intrinsics[1, 2] += yOffset
    self.frame.image = self.intrinsics.unwarp(self.frame.originalImage)
    self.frame.display(overlay=self.overlayMap())
    self.map.display(self.cameraOrigin, self.regionOfView, self.mapScale)
    return

  def setOpacity(self, value):
    self.opacity = value
    self.frame.display(overlay=self.overlayMap())
    return

def main():
  args = build_argparser().parse_args()

  with open(args.config) as f:
    config = json.load(f)
  camCoords = mapCoords = []
  if 'camera homography' in config['sensors'][args.camera]:
    camCoords = config['sensors'][args.camera]['camera homography']
  if 'map homography' in config['sensors'][args.camera]:
    mapCoords = config['sensors'][args.camera]['map homography']

  map_img = cv2.imread(args.map)
  video = cv2.VideoCapture(args.video)
  ret, frame = video.read()

  scene = scenescape(args.config).scene
  sensor = scene.sensors[args.camera]
  intrinsics = sensor.pose.intrinsics

  region = None
  if args.region:
    region = scene.regions[args.region].points

  doLive = 0
  #padding = 1000
  padding = 0
  mapCoords = [[x + padding for x in y] for y in mapCoords]
  map_img = cv2.copyMakeBorder(map_img, padding, padding, padding, padding,
                               cv2.BORDER_CONSTANT, value=(255,255,255))
  pos1 = Autobot(1, frame, camCoords, map_img, mapCoords, intrinsics, scene.scale, region)

  pos1.initWindows()

  try:
    while True:
      key = cv2.waitKey(0)

      if key == 27:
        break
      elif key == ord('+'):
        pos1.zoom(100)
      elif key == ord('-'):
        pos1.zoom(-100)
      elif key >= ord('0') and key <= ord('9'):
        val = key - ord('0')
        val = val / 9
        pos1.setOpacity(val)
      elif key == 83: # Right arrow
        pos1.moveCenter(100, 0)
      elif key == 81: # Left arrow
        pos1.moveCenter(-100, 0)
      elif key == 82: # Up arrow
        pos1.moveCenter(0, -100)
      elif key == 84: # Down arrow
        pos1.moveCenter(0, 100)
      elif key > 0:
        log.info("KEY", key)
  except:
    traceback.print_exc()

  cv2.destroyAllWindows()

  print('"camera homography": %s,' % (json.dumps(pos1.frame.coords)))
  print('"map homography": %s,'
        % (json.dumps([[x - padding for x in y] for y in pos1.map.coords])))

  if hasattr(pos1, 'registeredPose'):
    print('"slam pose": %s,' % (json.dumps(pos1.registeredPose.tolist())))
  if hasattr(pos1, 'slamScale'):
    print('"slam scale": %s,' % (pos1.slamScale))

  intrinsics = [pos1.intrinsics.intrinsics[0, 0], pos1.intrinsics.intrinsics[1, 1],
                pos1.intrinsics.intrinsics[0, 2], pos1.intrinsics.intrinsics[1, 2]]
  print('"intrinsics": %s,' % (json.dumps(pos1.intrinsics.intrinsics.tolist())))

  print('"width": %s,' % (pos1.frame.image.shape[1]))
  print('"height": %s,' % (pos1.frame.image.shape[0]))

  if args.region:
    coords = [(int(pt.x), int(pt.y)) for pt in pos1.rcoords]
    print('"%s": %s,' % (args.region, json.dumps(coords)))

  return

if __name__ == '__main__':
  exit(main() or 0)
