# SPDX-FileCopyrightText: (C) 2020 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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

