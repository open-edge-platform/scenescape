#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import threading
from argparse import ArgumentParser

import cv2
import numpy as np

from scene_common.scenescape import scenescape
from scene_common.timestamp import get_epoch_time


def build_argparser():
  parser = ArgumentParser(description="Generate camera calibration parameters"
                          " from video of a checkerboard.")
  parser.add_argument("cam", help="device or URL for camera")
  parser.add_argument("--fisheye", action="store_true", help="use routines for fisheye lenses")
  parser.add_argument("-m", "--max_frames", type=int, default=2,
                      help="Maximum number of frames to use"
                      " (more is slower but usually better)")
  parser.add_argument("-g", "--grid", help="Grid size of checkerboard", default="8x7")
  return parser

WHITE = (255,255,255)
YELLOW = (0,255,255)
GREEN = (0,255,0)

criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

class CBFinder(threading.Thread):
  def __init__(self, psize):
    super(CBFinder, self).__init__()
    self.psize = psize
    self.done = False
    self.frame = self.results = None
    self.lock = threading.Lock()
    return

  def run(self):
    while not self.done:
      img = None
      self.lock.acquire()
      if self.results is None and self.frame is not None:
        img = self.frame
      self.lock.release()
      if img is not None:
        res = self.findCB(img)
        self.lock.acquire()
        self.frame = None
        self.results = res
        self.lock.release()
    return

  def setFrame(self, frame):
    didSet = False
    self.lock.acquire()
    if self.results is None and self.frame is None:
      self.frame = frame
      didSet = True
    self.lock.release()
    if didSet:
      frame = cv2.flip(self.frame, 1)
      cv2.imshow("Processing", frame)
    return didSet

  def getResults(self):
    res = None
    self.lock.acquire()
    if self.results is not None:
      res = self.results
      self.results = None
    self.lock.release()
    return res

  def findCB(self, img):
    ret, corners = cv2.findChessboardCorners(img, self.psize)
    if not ret:
      SCALE = 2
      small = cv2.resize(img, None, fx=1 / SCALE, fy=1 / SCALE,
                         interpolation=cv2.INTER_CUBIC)
      ret, corners = cv2.findChessboardCorners(small, self.psize)
      if ret:
        corners = corners * SCALE
      else:
        small = 255 - small
        ret, corners = cv2.findChessboardCorners(small, self.psize)
        if ret:
          corners = corners * SCALE
    if not ret:
      return None
    return corners

def calibrate(cam, grid, max_frames, fisheye_flag):
  imgpoints = [] # 2d points in image plane.
  objpoints = [] # 3d points
  objp = np.zeros((grid[0] * grid[1], 3), np.float32)
  objp[:,:2] = np.mgrid[0:grid[0], 0:grid[1]].T.reshape(-1, 2)
  font = cv2.FONT_HERSHEY_SIMPLEX

  cv2.namedWindow("Distorted", cv2.WINDOW_NORMAL)
  cv2.namedWindow("Processing", cv2.WINDOW_NORMAL)
  cv2.namedWindow("Heatmap", cv2.WINDOW_NORMAL)
  cbThread = CBFinder(grid)
  cbThread.start()

  lastResults = 0
  calibrated_frame = None
  heatmap = None
  color = WHITE
  coverage = 0

  while True:
    frame = cam.capture()

    now = get_epoch_time()
    if now - lastResults > 0.1:
      if cbThread.setFrame(frame):
        color = YELLOW

    frame = cv2.flip(frame, 1)

    label = str(len(imgpoints))
    point = (10, frame.shape[0] - 10)
    size = int((frame.shape[0] + 479) / 480)
    cv2.putText(frame, label, point, font, size, (0,0,0), 5 * size)
    cv2.putText(frame, label, point, font, size, color, 2 * size)
    cv2.imshow("Distorted", frame)

    if coverage > 0.80 or cv2.waitKey(1) & 0xFF == 27:
      cv2.destroyAllWindows()
      cbThread.done = True
      cbThread.join()
      break

    calibrated_frame = cbThread.getResults()
    if calibrated_frame is not None:
      color = GREEN
      lastResults = get_epoch_time()

      p1 = tuple(calibrated_frame[0][0])
      p2 = tuple(calibrated_frame[grid[0] - 1][0])
      p3 = tuple(calibrated_frame[-1][0])
      p4 = tuple(calibrated_frame[-grid[0]][0])
      pts = np.array([p1, p2, p3, p4], dtype='int32')
      if heatmap is None:
        heatmap = np.zeros(frame.shape[:2], np.float32)
      mask = np.zeros(frame.shape[:2], np.float32)
      cv2.fillPoly(mask, [pts], 1)
      heatmap += mask
      heatmap[np.where(heatmap > max_frames)] = max_frames
      density = np.average(heatmap[np.where(mask == 1)] / max_frames)
      if density < 0.99:
        imgpoints.append(calibrated_frame)
        objpoints.append(objp)
        graymap = heatmap / max_frames
        coverage = np.average(graymap)
        graymap = cv2.flip(graymap, 1)
        label = "%0.3f" % (coverage)
        point = (10, graymap.shape[0] - 10)
        size = int((graymap.shape[0] + 479) / 480)
        cv2.putText(graymap, label, point, font, size, 0, 5 * size)
        cv2.putText(graymap, label, point, font, size, 1, 2 * size)
        cv2.imshow("Heatmap", graymap)

  if len(imgpoints) > 0:
    h, w = frame.shape[:2]
    print("Running calibration with", len(imgpoints), "frames")
    if fisheye_flag:
      K = np.zeros((3, 3))
      D = np.zeros((4, 1))
      ret, mtx, dist, rvecs, tvecs = cv2.fisheye.calibrate(objpoints, imgpoints, (w, h), K, D)
    else:
      ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, (w, h),
                                                         cameraMatrix=None, distCoeffs=None)

    print('"size": [%i, %i],' % (w, h))
    print('"ppx": %s,' % (format(mtx[0][2], 'f')))
    print('"ppy": %s,' % (format(mtx[1][2], 'f')))
    print('"fx": %s,' % (format(mtx[0][0], 'f')))
    print('"fy": %s,' % (format(mtx[1][1], 'f')))
    print('"intrinsics": %s,' % (json.dumps([mtx[0][0], mtx[1][1], mtx[0][2], mtx[1][2]])))
    print('"distortion": %s' % (json.dumps(dist[0].tolist())))

def main():
  args = build_argparser().parse_args()

  src = args.cam
  if src.startswith("rtsp://"):
    src = "rtspsrc location=%s protocols=tcp ! rtph264depay ! avdec_h264 ! videoconvert" \
          " ! appsink max-buffers=1 drop=true" % (src)
  elif (src.startswith("http://") or src.startswith("https://")) \
       and src.endswith("/video.cgi"):
    src = "souphttpsrc location=%s ! decodebin ! videoconvert !" \
          " appsink max-buffers=1 drop=true" % (src)
  cam = scenescape.VideoSource(src)
  grid = args.grid.split("x")
  cbsize = (int(grid[0]) - 1, int(grid[1]) - 1)
  calibrate(cam, cbsize, args.max_frames, args.fisheye)
  cv2.destroyAllWindows()
  return 0

if __name__ == '__main__':
  main()
