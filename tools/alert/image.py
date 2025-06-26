# SPDX-FileCopyrightText: (C) 2020 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import base64
import os
import subprocess
import tempfile
from urllib.parse import unquote, urlparse

import cv2
import numpy as np
import requests
import urllib3

from scene_common import log
from scene_common.geometry import Rectangle
from scene_common.rest_client import RESTClient


class Image:
  def __init__(self, url, cameraID, timestamp=None, rootCert=None, auth=None):
    self.url = url
    self.cameraID = cameraID
    self.timestamp = timestamp
    self.rootCert = rootCert
    self.auth = auth
    if self.timestamp is not None:
      self.getREST()
    else:
      self.getImage()
    return

  def getREST(self):
    rest = RESTClient(self.url, self.rootCert, self.auth)

    data = rest.frame(self.cameraID, self.timestamp)
    log.debug("FRAME RESULT", data.statusCode, data.keys())
    if data.statusCode == 200:
      image_array = np.frombuffer(base64.b64decode(data['image']), dtype=np.uint8)
      self.image = cv2.imdecode(image_array, flags=1)
    return

  def getImage(self):
    parsed = urlparse(self.url)
    if parsed.scheme == "rtsp":
      return self.getRTSP()

    response = None
    try:
      log.debug("Fetch try 1", self.url)
      response = requests.get(self.url, verify=False) # nosec B501 - bandit scan ignore
    except (urllib3.exceptions.MaxRetryError, requests.exceptions.SSLError):
      log.debug("Failed to fetch image try 1", self.url)
      pass

    if not response:
      parsed = {'user': unquote(parsed.username), 'password': unquote(parsed.password)}
      try:
        log.debug("Fetch try 2", self.url)
        response = requests.get(self.url,
                                auth=requests.auth.HTTPDigestAuth(parsed['user'],
                                                                  parsed['password']),
                                verify=False) # nosec B501 - bandit scan ignore
      except (urllib3.exceptions.MaxRetryError, requests.exceptions.SSLError):
        log.debug("Failed to fetch image try 2", self.url)
        pass

    if not response:
      log.error("NO IMAGE", self.url)
      return

    log.debug("Got image")
    image = np.asarray(bytearray(response.content), dtype="uint8")
    self.image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    return

  def getRTSP(self):
    tf, path = tempfile.mkstemp(suffix=".png")
    os.close(tf)
    cmd = ["ffmpeg", "-y", "-i", self.url, "-vframes", "1", path]
    ffmpeg = subprocess.run(cmd)
    self.image = cv2.imread(path)
    os.unlink(path)
    return

  def drawTextBelow(self, label, point, font, fscale, fthick, tcolor, bgcolor=None):
    lsize = cv2.getTextSize(label, font, fscale, fthick)[0]
    if bgcolor:
      lpoint = point + lsize
      cv2.rectangle(self.image, point.cv, lpoint.cv, bgcolor, cv2.FILLED)
    lpoint = point + (0, lsize[1])
    cv2.putText(self.image, label, lpoint.cv, font, fscale, tcolor, fthick)
    return lsize

  def labelDimensions(self, obj, bgcolor, font, font_size):
    bbMeters = Rectangle(obj['bb_meters'])
    bbox = Rectangle(obj['camera_bounds'][self.cameraID])
    log.debug("BOUNDING BOX", bbox)
    label = "%0.1fm x %0.1fm" % (bbMeters.width, bbMeters.height)
    lsize = self.drawTextBelow(label, bbox.bottomLeft, font, font_size, 1,
                               (0,0,0), bgcolor)

    # label = "%ipx x %ipx" % (bbox.width, bbox.height)
    # lpoint = bbox.bottomLeft + (0, lsize[1] + 2)
    # lsize = self.drawTextBelow(label, lpoint, font, font_size, 1, (0,0,0), bgcolor)

    # label = "%0.2f deg" % (obj.baseAngle)
    # lpoint = bbox.bottomLeft + (0, lsize[1] + 2)
    # lsize = self.drawTextBelow(label, lpoint, font, font_size, 1, (0,0,0), bgcolor)

    label = "%0.3f" % (obj['confidence'])
    lpoint = bbox.bottomLeft + (0, lsize[1] + 2)
    lsize = self.drawTextBelow(label, lpoint, font, font_size, 1, (0,0,0), bgcolor)
    return

  def markObjects(self, cam, event):
    for obj in event.objects:
      bbox = Rectangle(obj['camera_bounds'][self.cameraID])
      color = (0, 0, 255)
      if obj['type'] == "vehicle":
        color = (255, 128, 128)
      cv2.rectangle(self.image, *bbox.cv, color, 4)
      self.labelDimensions(obj, color, cv2.FONT_HERSHEY_SIMPLEX, 1.5)
    return

  @staticmethod
  def largest(images):
    size = [0, 0]
    for img in images:
      h, w, _ = img.image.shape
      if h > size[1]:
        size[1] = h
      if w > size[0]:
        size[0] = w
    return size

  @staticmethod
  def scaleImages(size, images):
    nimages = []
    for img in images:
      h, w, _ = img.image.shape
      nh = int((size[0] / w) * h)
      log.debug(nh)
      if nh == h:
        nimages.append(img.image)
      else:
        nimages.append(cv2.resize(img.image, (size[0], nh)))
    return nimages
