#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Automatic re-calibration fallback for PTZ cameras.

Some ONVIF PTZ cameras only advertise a generic, normalized
``AbsolutePanTiltPositionSpace`` (conventionally ``[-1, 1]``) with no way to
reliably derive degrees-per-unit without knowing the camera's physical
field of view (see ``pan_degrees``/``tilt_degrees`` in the README). For
those cameras, instead of guessing a linear pan/tilt -> rotation
approximation, this module grabs a fresh frame from the camera (the same
MQTT ``getcalibrationimage`` mechanism the manual calibration UI uses) and
asks the autocalibration service to compute a brand new AprilTag-based pose
from it, then converts the result into Scenescape's ``rotation``/
``translation`` camera fields.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

import requests

from scene_common import log
from scene_common.mqtt import PubSub

from pose_math import quaternion_to_euler_xyz_degrees

CALIBRATION_IMAGE_TIMEOUT_S = 10.0
CALIBRATION_POLL_INTERVAL_S = 2.0
CALIBRATION_POLL_TIMEOUT_S = 60.0


class AutoRecalibrator:
  """Requests a fresh AprilTag-based pose for a single camera on demand."""

  def __init__(self, autocalibration_url, autocalibration_rootcert,
               broker, brokerauth, brokerrootcert):
    self.autocalibration_url = autocalibration_url.rstrip('/')
    self.verify = autocalibration_rootcert if autocalibration_rootcert else False
    self.session = requests.Session()
    self.pubsub = PubSub(brokerauth, None, brokerrootcert, broker)
    self.pubsub.loopStart()
    return

  def _waitForCalibrationImage(self, camera_id, timeout):
    """Publishes ``getcalibrationimage`` for ``camera_id`` and waits for the
    camera's response on its ``IMAGE_CALIBRATE`` topic.

    @return     base64-encoded JPEG string, or None on timeout/error
    """
    topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera_id)
    cond = threading.Condition()
    received = {}

    def _onImage(client, userdata, message):
      try:
        payload = json.loads(message.payload.decode('utf-8'))
      except Exception as err:
        log.error(f"Failed to decode calibration image for {camera_id}: {err}")
        return
      if 'image' not in payload:
        return
      with cond:
        received['image'] = payload['image']
        cond.notify_all()
      return

    self.pubsub.addCallback(topic, _onImage, qos=2)
    try:
      cmd_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera_id)
      self.pubsub.publish(cmd_topic, "getcalibrationimage", qos=2)
      with cond:
        if 'image' not in received:
          cond.wait(timeout=timeout)
      return received.get('image')
    finally:
      self.pubsub.removeCallback(topic)

  def _startCalibration(self, camera_id, image_b64):
    url = f"{self.autocalibration_url}/cameras/{camera_id}/calibration"
    try:
      reply = self.session.post(url, json={"image": image_b64},
                                verify=self.verify, timeout=15)
    except requests.exceptions.RequestException as err:
      log.error(f"Failed to start auto-recalibration for {camera_id}: {err}")
      return False
    if reply.status_code not in (200, 202):
      log.error(
          f"Auto-recalibration request for {camera_id} failed: "
          f"{reply.status_code} {reply.text}")
      return False
    return True

  def _pollCalibrationResult(self, camera_id, timeout):
    url = f"{self.autocalibration_url}/cameras/{camera_id}/calibration"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      try:
        reply = self.session.get(url, verify=self.verify, timeout=10)
        result = reply.json()
      except requests.exceptions.RequestException as err:
        log.error(f"Failed to poll auto-recalibration status for {camera_id}: {err}")
        return None
      status = result.get('status')
      if status == 'success':
        return result
      if status == 'error':
        log.error(f"Auto-recalibration failed for {camera_id}: {result.get('message')}")
        return None
      time.sleep(CALIBRATION_POLL_INTERVAL_S)
    log.error(f"Timed out waiting for auto-recalibration of {camera_id}")
    return None

  def recalibrate(self, camera_id,
                  image_timeout=CALIBRATION_IMAGE_TIMEOUT_S,
                  poll_timeout=CALIBRATION_POLL_TIMEOUT_S) -> Optional[dict]:
    """Grabs a fresh frame from ``camera_id`` and asks the autocalibration
    service to compute a brand new pose from it.

    @return     {'rotation': [roll, pitch, yaw], 'translation': [x, y, z]}
                on success, else None
    """
    image = self._waitForCalibrationImage(camera_id, image_timeout)
    if not image:
      log.warning(
          f"No calibration image received for {camera_id}; is it actively streaming?")
      return None
    if not self._startCalibration(camera_id, image):
      return None
    result = self._pollCalibrationResult(camera_id, poll_timeout)
    if result is None:
      return None
    quat = result.get('quaternion')
    trans = result.get('translation')
    if not quat or not trans or len(quat) != 4 or len(trans) != 3:
      log.error(f"Auto-recalibration result for {camera_id} missing quaternion/translation")
      return None
    spread_ratio = result.get('spread_ratio')
    if spread_ratio is not None:
      log.info(f"Auto-recalibration for {camera_id} used a point spread ratio of {spread_ratio:.3f}")
    rotation = quaternion_to_euler_xyz_degrees(*[float(v) for v in quat])
    return {'rotation': rotation, 'translation': [float(v) for v in trans]}
