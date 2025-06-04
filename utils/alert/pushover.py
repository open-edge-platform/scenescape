# Copyright (C) 2020-2023 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import cv2
import requests

from scene_common import log

PUSHOVER="https://api.pushover.net/1/messages.json"

class Pushover:
  def __init__(self, token, key):
    self.token = token
    self.key = key
    return

  def send(self, message, sound, image, priority):
    parms = {
      "token": self.token,
      "user": self.key,
      "message": message,
    }
    if sound:
      parms['sound'] = sound
    if priority:
      parms['priority'] = priority
    if image is not None:
      log.info("Sending image")
      ret, jpeg = cv2.imencode(".jpg", image)
      files = {
        "attachment": ("image.jpg", jpeg, "image/jpeg")
      }
    else:
      files = None

    r = requests.post(PUSHOVER, data=parms, files=files)
    log.info(r.text)
    return

